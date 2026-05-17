import os
import subprocess
import threading
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Query, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from loguru import logger as loguru_logger

from models.database import (
    init_db, get_top_stories,
    get_stories_by_sector, get_market_data, get_latest_briefing,
    get_source_diversity, get_trending_topics, get_sector_summaries,
    last_updated
)
from scheduler import run_pipeline, start_scheduler
from services.market_data import fetch_and_store_market_data, get_big_market_movers
from services.briefing import generate_briefing
from services.pdf_briefing import generate_pdf_briefing

# ── Logging ──
# Structured JSON logging with loguru. Logs go to stdout (captured by Docker/Render)
# and to a rotating file for local debugging.
#
# When LOG_FORMAT=json, logs are emitted as single-line JSON objects suitable for
# Datadog, CloudWatch, Logstash, and other log aggregators.
# When LOG_FORMAT=text (default), human-readable format is used.
os.makedirs("logs", exist_ok=True)
loguru_logger.remove()  # Remove default handler

_log_format = os.environ.get("LOG_FORMAT", "text").lower()
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

if _log_format == "json":
    import json as _json
    loguru_logger.add(
        sink=lambda msg: print(msg, end=""),
        format=lambda record: _json.dumps({
            "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record["level"].name,
            "logger": record["name"],
            "module": record["module"],
            "function": record["function"],
            "line": record["line"],
            "message": record["message"],
        }, default=str),
        colorize=False,
        level=_log_level,
    )
else:
    loguru_logger.add(
        sink=lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan> | <level>{message}</level>",
        colorize=True,
        level=_log_level,
    )

# Also write to rotating file (10 MB per file, keep 3) — always human-readable for local debugging
loguru_logger.add(
    "logs/pipeline.log",
    rotation="10 MB",
    retention=3,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name} | {message}",
    level="DEBUG",
    enqueue=True,
)
logger = loguru_logger

# ── Cache ──
_news_cache: dict = {}
_news_cache_ts: float = 0
_CACHE_TTL = 300  # seconds (data refreshes every 6 hours)

_SECTORS = ["All", "Markets", "Tech", "Geopolitics", "Energy", "India", "Sports", "General"]


# ── Rate Limiter ──
# Global in-memory rate limiter — no Redis needed. Uses wall-clock time and
# a thread lock. Each action is keyed by name and has its own cooldown.
# This defends against rapid-fire requests from any source (multiple tabs,
# scripts, bots) since it's server-side and global.

class RateLimiter:
    """Simple in-memory rate limiter with per-action cooldowns.

    Thread-safe: uses a lock for all reads/writes to the state dict.
    Returns seconds remaining until the action is allowed again.
    """
    def __init__(self):
        self._locks: dict[str, threading.Lock] = {}
        self._state: dict[str, float] = {}
        self._global_lock = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._global_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def check(self, action: str, cooldown: float) -> float:
        """Check if *action* is allowed. Returns 0 if allowed, or seconds
        remaining until the cooldown expires.

        Uses time.monotonic() to prevent NTP clock corrections from
        bypassing the cooldown.
        """
        lock = self._lock_for(action)
        with lock:
            last = self._state.get(action, 0.0)
            elapsed = time.monotonic() - last
            if elapsed < cooldown:
                return round(cooldown - elapsed, 1)
            self._state[action] = time.monotonic()
            return 0.0

    def reset(self, action: str) -> None:
        """Manually reset the cooldown (e.g. when the action is triggered
        by the scheduler rather than by a user request)."""
        lock = self._lock_for(action)
        with lock:
            self._state[action] = 0.0


_limiter = RateLimiter()


# ── Lifespan ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized.")

    # Skip scheduler in test mode
    if not os.environ.get("_TESTING"):
        # Start APScheduler (pipeline runs every 6 hours)
        start_scheduler()

        # Run the pipeline once on startup so data is ready immediately.
        # Runs in a background thread so the server starts up without delay.
        # The MAX_ARTICLES=250 limit prevents OOM on Render's free tier (512 MB).
        threading.Thread(target=run_pipeline, daemon=True).start()
        logger.info("Startup pipeline triggered in background thread")

    yield


app = FastAPI(title="Serious Operator News Dashboard", version="2.0.0", lifespan=lifespan)

# ── CORS ──
# In production, restrict to your frontend domain via the CORS_ORIGINS env var.
# Format: comma-separated list (e.g. "https://app.example.com,https://admin.example.com")
# Default: allow all origins (safe for dev, but lock down before deploying publicly).
_allowed_origins = os.environ.get("CORS_ORIGINS", "*")
if _allowed_origins == "*":
    cors_origins = ["*"]
else:
    cors_origins = [o.strip() for o in _allowed_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Security Headers ──
# Adds security-related HTTP headers to all responses to harden against XSS,
# clickjacking, MIME sniffing, and other common web attacks.
# In production, set CORS_ORIGINS to your frontend domain.

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to every response."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


# ── API Key Auth ──
# Set API_KEY in your environment to require authentication on write endpoints
# (POST /pipeline/run, /markets/refresh, /briefing/generate).
# The key must be sent as the X-API-Key header.
# If API_KEY is not set, all endpoints are open (dev mode).
_API_KEY = os.environ.get("API_KEY")


_PUBLIC_POST_PATHS = {"/news/reviews"}


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Require X-API-Key header on POST endpoints when API_KEY is configured.
    Public POST paths in _PUBLIC_POST_PATHS are exempt from auth.
    """
    if _API_KEY and request.method == "POST" and request.url.path not in _PUBLIC_POST_PATHS:
        client_key = request.headers.get("X-API-Key", "")
        if client_key != _API_KEY:
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "message": "Missing or invalid API key. Provide it as the X-API-Key header."},
            )
    return await call_next(request)


# ── Health ──

@app.get("/")
def health():
    """Health check for Render. NEVER touches the database — must always return 200
    even if the DB is down, otherwise Render marks the deploy as failed and restarts."""
    return {"status": "seriously operational"}


@app.get("/version")
def version():
    """Return the current git commit hash for deployment verification."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        commit = result.stdout.strip()
        return {"commit": commit, "deployed": True}
    except Exception as e:
        return {"commit": "unknown", "error": str(e), "deployed": True}


# ── News Endpoints ──

@app.get("/news")
def get_news(force_refresh: bool = Query(False, description="Bypass cache")):
    global _news_cache, _news_cache_ts
    now = datetime.now(timezone.utc).timestamp()

    if not force_refresh and _news_cache and (now - _news_cache_ts) < _CACHE_TTL:
        return _news_cache

    try:
        stories = get_top_stories(limit=20)

        # Group stories by sector
        sector_stories: dict[str, list[dict]] = {}
        for s in stories:
            for sector in s.get("sectors", ["General"]):
                sector_stories.setdefault(sector, []).append(s)

        # Order sectors
        sectors_in_order = [s for s in _SECTORS if s != "All" and s in sector_stories]

        result = {
            "top_stories": stories,
            "sector_stories": sector_stories,
            "sectors": sectors_in_order,
            "last_updated": last_updated(),
        }

        _news_cache = result
        _news_cache_ts = now
        return result

    except Exception as e:
        logger.exception(f"Failed to fetch news: {e}")
        if _news_cache:
            return _news_cache
        return {"top_stories": [], "sector_stories": {}, "sectors": [], "last_updated": None}


@app.get("/news/stories")
def get_all_stories(limit: int = Query(20, ge=1, le=100)):
    """Get all top stories raw."""
    return {"stories": get_top_stories(limit=limit)}


@app.get("/news/sectors")
def get_sectors():
    """Get list of active sectors with story counts."""
    stories = get_top_stories(limit=100)
    sector_counts: dict[str, int] = {}
    for s in stories:
        for sector in s.get("sectors", ["General"]):
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
    return {"sectors": [{"name": k, "count": v} for k, v in sorted(sector_counts.items(), key=lambda x: -x[1])]}


@app.get("/news/sector/{sector}")
def get_sector_news(sector: str, limit: int = Query(20, ge=1, le=50)):
    """Get top stories for a specific sector."""
    stories = get_stories_by_sector(sector, limit=limit)
    return {
        "sector": sector,
        "stories": stories,
        "count": len(stories),
    }


@app.get("/news/sector-summaries")
def sector_summaries():
    """Get summary descriptions for each sector."""
    return {"summaries": get_sector_summaries()}


# ── Market Data ──

@app.get("/markets")
def markets():
    """Get current market data for all tracked tickers."""
    try:
        data = get_market_data()
        if not data:
            # Fetch fresh data
            data = fetch_and_store_market_data()
        movers = get_big_market_movers()
        return {
            "all": data,
            "gainers": movers["gainers"],
            "losers": movers["losers"],
            "indices": movers["indices"],
        }
    except Exception as e:
        logger.exception(f"Market data error: {e}")
        return {"all": [], "gainers": [], "losers": [], "indices": []}


@app.post("/markets/refresh")
def refresh_markets():
    """Force refresh market data.

    Rate-limited: max 1 refresh per 60 seconds to prevent abuse.
    """
    remaining = _limiter.check("markets", 60)
    if remaining > 0:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limited",
                "message": f"Market data was just refreshed. Try again in {remaining:.0f} seconds.",
                "retry_after": remaining,
            },
        )
    data = fetch_and_store_market_data()
    return {"status": "refreshed", "count": len(data)}


# ── Briefing & Export ──

@app.get("/briefing")
def get_briefing():
    """Get the latest executive briefing."""
    briefing = get_latest_briefing()
    if briefing:
        return briefing
    # Generate on demand
    content = generate_briefing()
    return {"content": content, "created_at": datetime.now(timezone.utc).isoformat()}


@app.post("/briefing/generate")
def generate_new_briefing():
    """Generate a fresh executive briefing.

    Rate-limited: max 1 generation per 60 seconds.
    """
    remaining = _limiter.check("briefing", 60)
    if remaining > 0:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limited",
                "message": f"Briefing was just generated. Try again in {remaining:.0f} seconds.",
                "retry_after": remaining,
            },
        )
    content = generate_briefing()
    return {"content": content, "created_at": datetime.now(timezone.utc).isoformat()}


@app.get("/export/markdown")
def export_markdown():
    """Export the full briefing as markdown."""
    briefing = get_latest_briefing()
    content = briefing["content"] if briefing else generate_briefing()
    filename = f"operator-brief-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    return PlainTextResponse(
        content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/export/json")
def export_json():
    """Export all data as JSON."""
    stories = get_top_stories(limit=50)
    market = get_market_data()
    diversity = get_source_diversity()
    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "stories": stories,
        "markets": market,
        "source_diversity": diversity,
    }
    filename = f"operator-brief-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/export/pdf")
def export_pdf():
    """Export the full briefing as a structured PDF."""
    try:
        pdf_bytes = generate_pdf_briefing()
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=operator-brief-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.pdf",
            "Content-Type": "application/pdf",
        },
        )
    except Exception as e:
        logger.exception(f"PDF generation failed: {e}")
        return PlainTextResponse("Failed to generate PDF", status_code=500)


# ── Source Diversity ──

@app.get("/sources")
def source_diversity():
    """Get source diversity information."""
    return {"sources": get_source_diversity()}


# ── Trending ──

@app.get("/trending")
def trending(hours: int = Query(48, ge=1, le=168)):
    """Get trending topics over the specified time period."""
    return {"trending": get_trending_topics(hours=hours)}


# ── Story Reviews ──

@app.post("/news/reviews")
def submit_story_review(data: dict):
    """Submit a user review for a story.

    Public endpoint — no API key required. Collects feedback on:
    - Section correctness
    - Summary quality
    - Image availability
    """
    required = ["story_title", "correct_section", "summary_concise", "picture_available"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    valid_values = ["yes", "no"]
    for field in ["correct_section", "summary_concise", "picture_available"]:
        if data.get(field, "").lower() not in valid_values:
            raise HTTPException(status_code=400, detail=f"{field} must be 'yes' or 'no'")

    try:
        from models.database import save_review
        review = save_review({
            "story_title": data["story_title"],
            "story_url": data.get("story_url"),
            "correct_section": data["correct_section"],
            "suggested_section": data.get("suggested_section"),
            "summary_concise": data["summary_concise"],
            "picture_available": data["picture_available"],
            "comment": data.get("comment"),
        })
        return {"status": "ok", "review": review}
    except Exception as e:
        logger.exception(f"Failed to save review: {e}")
        raise HTTPException(status_code=500, detail="Failed to save review")


@app.get("/news/reviews")
def get_story_reviews(limit: int = Query(100, ge=1, le=1000)):
    """Get all submitted story reviews, most recent first.

    Note: POST endpoints are behind API key auth when API_KEY is set.
    GET endpoints are public (consistent with the rest of the API).
    """
    try:
        from models.database import get_reviews
        reviews = get_reviews(limit=limit)
        return {"reviews": reviews, "count": len(reviews)}
    except Exception as e:
        logger.exception(f"Failed to fetch reviews: {e}")
        return {"reviews": [], "count": 0}


# ── Pipeline Control ──

@app.post("/pipeline/run")
def trigger_pipeline():
    """Manually trigger the news pipeline.

    Rate-limited: max 1 run per 10 minutes (600 seconds) to prevent
    abuse via the Refresh button or automated scripts.
    """
    remaining = _limiter.check("pipeline", 600)
    if remaining > 0:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limited",
                "message": f"Pipeline was just run. Try again in {remaining:.0f} seconds.",
                "retry_after": remaining,
            },
        )
    try:
        run_pipeline()
        return {"status": "pipeline completed"}
    except Exception as e:
        logger.exception("Pipeline run failed")
        return {"status": "error", "detail": str(e)}


@app.get("/pipeline/test-fetch")
def test_fetch():
    """Diagnostic: test RSS feed fetching without running the full pipeline.
    Resets the pipeline rate limiter so you can trigger it after."""
    try:
        from services.fetch_news import fetch_rss_feeds, RSS_SOURCES
        articles = fetch_rss_feeds()
        # Reset pipeline rate limiter so we can trigger a fresh run
        _limiter.reset("pipeline")
        return {
            "feeds_configured": len(RSS_SOURCES),
            "articles_fetched": len(articles),
            "sample_articles": [
                {"title": a["title"][:80], "source": a["source"]}
                for a in articles[:5]
            ],
        }
    except Exception as e:
        return {"error": str(e), "detail": "Fetch failed"}



@app.get("/pipeline/db-status")
def db_status():
    """Diagnostic: check database article and story counts."""
    try:
        from models.database import SessionLocal
        from models.models import Article, Summary
        db = SessionLocal()
        try:
            article_count = db.query(Article).count()
            story_count = db.query(Summary).count()
            return {
                "articles": article_count,
                "stories": story_count,
            }
        finally:
            db.close()
    except Exception as e:
        return {"error": str(e)}

# ── Main ──

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
