import os
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, desc, inspect, text
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # sslmode=require is needed for remote Postgres (Supabase, external hosts),
    # but NOT for local Docker/Dev (no SSL) or Render internal PostgreSQL
    # (connections stay within Render's network and don't use SSL).
    # Skip for SQLite (doesn't support sslmode) and if the URL already specifies it.
    _is_sqlite = DATABASE_URL.startswith("sqlite")
    _has_sslmode = "sslmode" in DATABASE_URL
    _is_local = any(h in DATABASE_URL for h in ["localhost", "127.0.0.1"])
    _is_render_internal = "dpg-" in DATABASE_URL.split("@")[-1].split("/")[0] if "@" in DATABASE_URL else False

    if not _is_sqlite and not _has_sslmode and not _is_local and not _is_render_internal:
        engine = create_engine(
            DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            connect_args={"sslmode": "require"},
        )
    else:
        engine = create_engine(
            DATABASE_URL,
            pool_size=5,
            max_overflow=10,
        )
else:
    engine = create_engine(
        "sqlite:///news.db",
        connect_args={"check_same_thread": False},
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
from .models import Base


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from .models import Article, Cluster, Summary, MarketData, Briefing, SectorSummary, StoryReview
    from loguru import logger
    
    # Create tables that don't exist yet
    Base.metadata.create_all(bind=engine)
    
    # Auto-migrate: add missing columns to existing tables
    # create_all only CREATES new tables, it doesn't add columns to existing ones.
    # This handles the case where new columns were added to models after the
    # production database was already created (e.g., image_url, sectors).
    inspector = inspect(engine)
    for table_name, model_class in [
        ("articles", Article),
        ("stories", Summary),
        ("market_data", MarketData),
        ("briefings", Briefing),
        ("sector_summaries", SectorSummary),
    ]:
        try:
            existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
        except Exception:
            continue  # Table might not exist yet
        model_cols = {c.name for c in model_class.__table__.columns if c.nullable is not False}
        missing = model_cols - existing_cols
        for col_name in missing:
            col = next(c for c in model_class.__table__.columns if c.name == col_name)
            col_type_str = col.type.compile(engine.dialect)
            try:
                with engine.connect() as conn:
                    conn.execute(
                        text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col_name}" {col_type_str}')
                    )
                    conn.commit()
                logger.info(f"Added missing column '{col_name}' to '{table_name}'")
            except Exception as e:
                logger.warning(f"Could not add column '{col_name}' to '{table_name}': {e}")


# ──────────────────────────────────────────────
# Articles
# ──────────────────────────────────────────────

def save_articles(articles_data: list[dict], db: Session | None = None) -> int:
    """Save articles, optionally reusing an existing DB session for batching.

    Args:
        articles_data: List of article dicts to insert.
        db: Optional existing session. If provided, the caller owns commit/close.
            If None, a new session is created, committed, and closed.
    """
    from .models import Article
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True
    inserted = 0
    now = datetime.now(timezone.utc).isoformat()
    try:
        for a in articles_data:
            exists = db.query(Article).filter(Article.url == a["url"]).first()
            if not exists:
                new_article = Article(
                    id=a["id"],
                    title=a["title"],
                    url=a["url"],
                    source=a["source"],
                    published_at=a["published_at"],
                    content_snippet=a.get("content_snippet", ""),
                    fetched_at=now,
                    sectors=json.dumps(a.get("source_sectors", [])),
                    image_url=a.get("image_url")
                )
                db.add(new_article)
                inserted += 1
            else:
                # Article already exists — update fetched_at so the next
                # pipeline run's get_recent_articles(hours=24) can find it,
                # and backfill image_url if we now have one (feeds sometimes
                # add images after initial publication or we improved extraction).
                exists.fetched_at = now
                if a.get("image_url"):
                    exists.image_url = a["image_url"]
        if own_session:
            db.commit()
    except Exception as e:
        if own_session:
            db.rollback()
        raise e
    finally:
        if own_session:
            db.close()
    return inserted


def get_recent_articles(hours: int = 24) -> list[dict]:
    from config import RSS_SOURCES
    from .models import Article
    # Build a name→sectors lookup from current config — this way old articles
    # get the correct source sectors even if the DB has stale TF-IDF data.
    source_map = {s["name"]: s.get("sectors", []) for s in RSS_SOURCES}
    db = SessionLocal()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        articles = db.query(Article).filter(Article.fetched_at >= cutoff).all()
        results = [
            {
                "id": a.id,
                "title": a.title,
                "url": a.url,
                "source": a.source,
                "published_at": a.published_at,
                "content_snippet": a.content_snippet,
                "fetched_at": a.fetched_at,
                "cluster_id": a.cluster_id,
                "source_sectors": source_map.get(a.source, []),
                "image_url": a.image_url,
            }
            for a in articles
        ]
        return results
    finally:
        db.close()


# ──────────────────────────────────────────────
# Stories / Summaries
# ──────────────────────────────────────────────

def save_stories(stories_data: list[dict], db: Session | None = None) -> None:
    """Save stories, optionally reusing an existing DB session for batching."""
    from .models import Summary
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True
    try:
        db.query(Summary).delete()
        now = datetime.now(timezone.utc).isoformat()
        for s in stories_data:
            sectors = s.get("sectors", ["General"])
            if isinstance(sectors, list):
                sectors_str = json.dumps(sectors)
            else:
                sectors_str = json.dumps([sectors])

            new_story = Summary(
                title=s["title"],
                summary=s["summary"],
                why_it_matters=s["why_it_matters"],
                url=s.get("url"),
                score=s["score"],
                article_count=s["article_count"],
                source=",".join(s.get("source", [])),
                published_at=s.get("published_at", now),
                latest_at=s.get("latest_at", now),
                created_at=now,
                sectors=sectors_str,
                sector_summary=s.get("sector_summary"),
                trending_score=s.get("trending_score"),
                image_url=s.get("image_url"),
            )
            db.add(new_story)
        if own_session:
            db.commit()
    except Exception as e:
        if own_session:
            db.rollback()
        raise e
    finally:
        if own_session:
            db.close()


def get_top_stories(limit: int = 10) -> list[dict]:
    from .models import Summary
    db = SessionLocal()
    try:
        stories = db.query(Summary).order_by(desc(Summary.score)).limit(limit).all()
        results = []
        for s in stories:
            try:
                sectors = json.loads(s.sectors) if s.sectors else ["General"]
            except (json.JSONDecodeError, TypeError):
                sectors = ["General"]

            results.append({
                "title": s.title,
                "summary": s.summary,
                "why_it_matters": s.why_it_matters,
                "url": s.url,
                "score": s.score,
                "article_count": s.article_count,
                "source": s.source.split(",") if s.source else [],
                "published_at": s.published_at,
                "latest_at": s.latest_at,
                "created_at": s.created_at,
                "sectors": sectors,
                "sector_summary": s.sector_summary,
                "trending_score": s.trending_score,
                "image_url": s.image_url,
            })
        return results
    finally:
        db.close()


def get_stories_by_sector(sector: str, limit: int = 20) -> list[dict]:
    """Get top stories filtered by a specific sector.

    Uses SQL LIKE on the JSON-encoded sectors column to push filtering
    down to the database rather than fetching all rows and filtering in Python.
    Case-insensitive via SQL lower() since sectors are stored with capital
    first letters (e.g. '["Markets", "Tech"]').
    """
    from .models import Summary
    from sqlalchemy import func
    db = SessionLocal()
    try:
        pattern = f"%{sector}%"
        stories = (
            db.query(Summary)
            .filter(func.lower(Summary.sectors).like(func.lower(pattern)))
            .order_by(desc(Summary.score))
            .limit(limit)
            .all()
        )
        results = []
        for s in stories:
            try:
                sectors = json.loads(s.sectors) if s.sectors else ["General"]
            except (json.JSONDecodeError, TypeError):
                sectors = ["General"]

            results.append({
                "title": s.title,
                "summary": s.summary,
                "why_it_matters": s.why_it_matters,
                "url": s.url,
                "score": s.score,
                "article_count": s.article_count,
                "source": s.source.split(",") if s.source else [],
                "published_at": s.published_at,
                "latest_at": s.latest_at,
                "created_at": s.created_at,
                "sectors": sectors,
                "sector_summary": s.sector_summary,
                "trending_score": s.trending_score,
                "image_url": s.image_url,
            })
        return results
    finally:
        db.close()


def story_count() -> int:
    from .models import Summary
    db = SessionLocal()
    try:
        return db.query(Summary).count()
    finally:
        db.close()


def last_updated() -> str | None:
    from .models import Summary
    db = SessionLocal()
    try:
        res = db.query(Summary.created_at).order_by(desc(Summary.created_at)).first()
        return res[0] if res else None
    finally:
        db.close()


# ──────────────────────────────────────────────
# Market Data
# ──────────────────────────────────────────────

def save_market_data(data: list[dict]) -> None:
    from .models import MarketData
    db = SessionLocal()
    now = datetime.now(timezone.utc).isoformat()
    try:
        # Clear old data
        db.query(MarketData).delete()
        for d in data:
            md = MarketData(
                ticker=d["ticker"],
                name=d.get("name", ""),
                price=d.get("price", 0),
                change=d.get("change", 0),
                change_pct=d.get("change_pct", 0),
                market_cap=d.get("market_cap"),
                sector=d.get("sector", "General"),
                recorded_at=now,
            )
            db.add(md)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_market_data() -> list[dict]:
    from .models import MarketData
    db = SessionLocal()
    try:
        records = db.query(MarketData).all()
        return [
            {
                "ticker": r.ticker,
                "name": r.name,
                "price": r.price,
                "change": r.change,
                "change_pct": r.change_pct,
                "market_cap": r.market_cap,
                "sector": r.sector,
            }
            for r in records
        ]
    finally:
        db.close()


# ──────────────────────────────────────────────
# Briefings
# ──────────────────────────────────────────────

def save_briefing(content: str) -> None:
    from .models import Briefing
    db = SessionLocal()
    now = datetime.now(timezone.utc).isoformat()
    try:
        db.query(Briefing).delete()
        b = Briefing(content=content, created_at=now)
        db.add(b)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_latest_briefing() -> dict | None:
    from .models import Briefing
    db = SessionLocal()
    try:
        b = db.query(Briefing).order_by(desc(Briefing.created_at)).first()
        if b:
            return {"content": b.content, "created_at": b.created_at}
        return None
    finally:
        db.close()


# ──────────────────────────────────────────────
# Sector Summaries
# ──────────────────────────────────────────────

def save_sector_summary(sector: str, summary: str, headline_count: int, db: Session | None = None) -> None:
    """Save a sector summary, optionally reusing an existing DB session for batching."""
    from .models import SectorSummary
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True
    now = datetime.now(timezone.utc).isoformat()
    try:
        existing = db.query(SectorSummary).filter(SectorSummary.sector == sector).first()
        if existing:
            existing.summary = summary
            existing.headline_count = headline_count
            existing.created_at = now
        else:
            ss = SectorSummary(sector=sector, summary=summary, headline_count=headline_count, created_at=now)
            db.add(ss)
        if own_session:
            db.commit()
    except Exception as e:
        if own_session:
            db.rollback()
        raise e
    finally:
        if own_session:
            db.close()


def get_sector_summaries() -> list[dict]:
    from .models import SectorSummary
    db = SessionLocal()
    try:
        records = db.query(SectorSummary).all()
        return [
            {
                "sector": r.sector,
                "summary": r.summary,
                "headline_count": r.headline_count,
                "created_at": r.created_at,
            }
            for r in records
        ]
    finally:
        db.close()


# ──────────────────────────────────────────────
# Source Diversity
# ──────────────────────────────────────────────

def get_source_diversity() -> list[dict]:
    """Get source diversity stats from recent articles."""
    from .models import Article
    db = SessionLocal()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        articles = db.query(Article).filter(Article.fetched_at >= cutoff).all()

        source_counts: dict[str, int] = {}
        for a in articles:
            source_counts[a.source] = source_counts.get(a.source, 0) + 1

        total = sum(source_counts.values()) or 1
        return [
            {"source": src, "count": cnt, "pct": round(cnt / total * 100, 1)}
            for src, cnt in sorted(source_counts.items(), key=lambda x: -x[1])
        ]
    finally:
        db.close()


def get_trending_topics(hours: int = 48) -> list[dict]:
    """Get trending topics based on story scores over time."""
    from .models import Summary
    db = SessionLocal()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        stories = db.query(Summary).filter(Summary.created_at >= cutoff).order_by(desc(Summary.score)).limit(20).all()
        return [
            {
                "title": s.title,
                "score": s.score,
                "article_count": s.article_count,
                "sectors": json.loads(s.sectors) if s.sectors else ["General"],
                "created_at": s.created_at,
            }
            for s in stories
        ]
    finally:
        db.close()


# ──────────────────────────────────────────────
# Story Reviews
# ──────────────────────────────────────────────

def save_review(review_data: dict) -> dict:
    """Save a user review of a story.

    Returns the saved review dict.
    """
    from .models import StoryReview
    from uuid import uuid4
    db = SessionLocal()
    now = datetime.now(timezone.utc).isoformat()
    try:
        review = StoryReview(
            id=str(uuid4()),
            story_title=review_data["story_title"],
            story_url=review_data.get("story_url"),
            correct_section=review_data["correct_section"],
            suggested_section=review_data.get("suggested_section"),
            summary_concise=review_data["summary_concise"],
            picture_available=review_data["picture_available"],
            comment=review_data.get("comment"),
            created_at=now,
        )
        db.add(review)
        db.commit()
        return {
            "id": review.id,
            "story_title": review.story_title,
            "correct_section": review.correct_section,
            "suggested_section": review.suggested_section,
            "summary_concise": review.summary_concise,
            "picture_available": review.picture_available,
            "comment": review.comment,
            "created_at": review.created_at,
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_reviews(limit: int = 100) -> list[dict]:
    """Get all story reviews ordered by most recent first."""
    from .models import StoryReview
    db = SessionLocal()
    try:
        reviews = db.query(StoryReview).order_by(desc(StoryReview.created_at)).limit(limit).all()
        return [
            {
                "id": r.id,
                "story_title": r.story_title,
                "story_url": r.story_url,
                "correct_section": r.correct_section,
                "suggested_section": r.suggested_section,
                "summary_concise": r.summary_concise,
                "picture_available": r.picture_available,
                "comment": r.comment,
                "created_at": r.created_at,
            }
            for r in reviews
        ]
    finally:
        db.close()
