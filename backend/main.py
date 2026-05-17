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
from loguru import logger as loguru_logger

from models.database import (
    init_db, get_upsc_stories, last_updated
)
from scheduler import run_pipeline, start_scheduler

# ── Logging ──

os.makedirs("logs", exist_ok=True)
loguru_logger.remove()

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

loguru_logger.add(
    "logs/pipeline.log",
    rotation="10 MB",
    retention=3,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name} | {message}",
    level="DEBUG",
    enqueue=True,
)
logger = loguru_logger


# ── Rate Limiter ──

class RateLimiter:
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
        lock = self._lock_for(action)
        with lock:
            last = self._state.get(action, 0.0)
            elapsed = time.monotonic() - last
            if elapsed < cooldown:
                return round(cooldown - elapsed, 1)
            self._state[action] = time.monotonic()
            return 0.0

    def reset(self, action: str) -> None:
        lock = self._lock_for(action)
        with lock:
            self._state[action] = 0.0

_limiter = RateLimiter()


# ── Gemini Diagnostics ──

def _mask_key(key: str) -> str:
    """Mask an API key for safe display (show first 6 + last 4 chars)."""
    if len(key) < 12:
        return key[:4] + "..."
    return key[:6] + "..." + key[-4:]


def _probe_single_key(api_key: str, model: str) -> dict:
    """Test a single API key against a specific Gemini model."""
    import httpx
    from upsc_analyzer import _GEMINI_BASE_URL

    url = f"{_GEMINI_BASE_URL}/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [{"text": "Reply with one word: OK"}]
        }],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 10,
        },
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text = parts[0].get("text", "") if parts else ""
                return {"status": "ok", "response": text}
            return {"status": "error", "code": 200, "detail": "No candidates in response"}
        else:
            return {"status": "error", "code": resp.status_code, "detail": resp.text[:200]}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _probe_gemini_keys(env_var_names: list[str]) -> dict:
    """Probe Gemini models using a specific set of env var names."""
    from upsc_analyzer import _GEMINI_MODEL, _GEMINI_FALLBACK_MODELS

    models_to_try = [_GEMINI_MODEL] + _GEMINI_FALLBACK_MODELS
    results = []
    working_model = None
    working_response = None

    api_key = None
    for var_name in env_var_names:
        val = os.environ.get(var_name)
        if val:
            api_key = val
            break

    if not api_key:
        return {"status": "error", "message": "No API key found in environment"}

    for model in models_to_try:
        result = _probe_single_key(api_key, model)
        if result["status"] == "ok":
            working_model = model
            working_response = result["response"]
            results.append({"model": model, "status": "ok", "response": result["response"]})
            break
        else:
            results.append({"model": model, "status": "error", **{k: v for k, v in result.items() if k != "status"}})

    if working_model:
        return {
            "status": "ok",
            "model_used": working_model,
            "response": working_response,
            "api_key_set": True,
            "all_results": results,
        }
    else:
        return {
            "status": "error",
            "message": "No working model found",
            "all_results": results,
        }


def _probe_gemini_keys_all() -> dict:
    """Probe all detected Gemini API keys and report which ones work."""
    from upsc_analyzer import _load_api_keys, _GEMINI_MODEL, _GEMINI_FALLBACK_MODELS

    keys = _load_api_keys()
    if not keys:
        return {"status": "error", "message": "No GEMINI_API_KEY* variables found in environment"}

    models_to_try = [_GEMINI_MODEL] + _GEMINI_FALLBACK_MODELS
    keys_report = []
    any_working = False

    for i, key in enumerate(keys):
        env_var = f"GEMINI_API_KEY_{i + 1}" if i > 0 else "GEMINI_API_KEY"
        masked = _mask_key(key)

        model_results = []
        working_model = None
        working_response = None

        for model in models_to_try:
            result = _probe_single_key(key, model)
            if result["status"] == "ok":
                working_model = model
                working_response = result["response"]
                model_results.append({"model": model, "status": "ok", "response": result["response"]})
                any_working = True
                break
            else:
                model_results.append({"model": model, "status": "error", **{k: v for k, v in result.items() if k != "status"}})

        key_entry: dict = {
            "key_index": i,
            "env_var": env_var,
            "masked_key": masked,
            "results": model_results,
        }
        if working_model:
            key_entry["working_model"] = working_model
        keys_report.append(key_entry)

    return {
        "status": "ok" if any_working else "error",
        "total_keys": len(keys),
        "working_keys": sum(1 for k in keys_report if "working_model" in k),
        "keys": keys_report,
    }


# ── Lifespan ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized.")

    if not os.environ.get("_TESTING"):
        start_scheduler()
        threading.Thread(target=run_pipeline, daemon=True).start()
        logger.info("Startup pipeline triggered in background thread")
    yield


app = FastAPI(title="UPSC Daily Affairs", version="2.0.0", lifespan=lifespan)

# ── CORS ──

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

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


# ── API Key Auth ──

_API_KEY = os.environ.get("API_KEY")
_PUBLIC_POST_PATHS = {"/news/reviews"}

@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if _API_KEY and request.method == "POST" and request.url.path not in _PUBLIC_POST_PATHS:
        client_key = request.headers.get("X-API-Key", "")
        if client_key != _API_KEY:
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "message": "Missing or invalid API key."},
            )
    return await call_next(request)


# ── Health ──

@app.get("/")
def health():
    return {"status": "ok", "app": "UPSC Daily Affairs"}


@app.get("/version")
def version():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        commit = result.stdout.strip()
        return {"commit": commit, "deployed": True}
    except Exception as e:
        return {"commit": "unknown", "error": str(e), "deployed": True}


# ── UPSC Intelligence Endpoint ──

@app.get("/upsc")
def get_upsc(
    limit: int = Query(50, ge=1, le=200),
    min_relevance: float = Query(0.0, ge=0.0, le=1.0, description="Minimum relevance score filter")
):
    try:
        stories = get_upsc_stories(limit=limit, min_relevance=min_relevance)

        gs_groups: dict[str, list[dict]] = {}
        for s in stories:
            paper = s.get("gs_paper", "Unmapped")
            gs_groups.setdefault(paper, []).append(s)

        return {
            "stories": stories,
            "gs_groups": gs_groups,
            "total_count": len(stories),
            "has_exam_playbook": sum(1 for s in stories if s.get("exam_playbook")),
        }
    except Exception as e:
        logger.exception(f"Failed to fetch UPSC stories: {e}")
        return {"stories": [], "gs_groups": {}, "total_count": 0, "has_exam_playbook": 0}


# ── Story Reviews ──

@app.post("/news/reviews")
def submit_story_review(data: dict):
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
    try:
        from services.fetch_news import fetch_rss_feeds
        articles = fetch_rss_feeds()
        _limiter.reset("pipeline")
        return {
            "articles_fetched": len(articles),
            "sample_articles": [
                {"title": a["title"][:80], "source": a["source"]}
                for a in articles[:5]
            ],
        }
    except Exception as e:
        return {"error": str(e), "detail": "Fetch failed"}


@app.get("/pipeline/test-gemini")
def test_gemini():
    """Probe multiple Gemini models with the primary API key."""
    return _probe_gemini_keys(["GEMINI_API_KEY"])


@app.get("/pipeline/test-gemini-keys")
def test_gemini_keys():
    """List all detected Gemini API keys and test each one."""
    return _probe_gemini_keys_all()


@app.get("/pipeline/db-status")
def db_status():
    try:
        from models.database import SessionLocal
        from models.models import Article, Summary
        db = SessionLocal()
        try:
            article_count = db.query(Article).count()
            story_count = db.query(Summary).count()
            return {"articles": article_count, "stories": story_count}
        finally:
            db.close()
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
