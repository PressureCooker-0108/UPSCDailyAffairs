"""
News Dashboard - SQLite to Supabase PostgreSQL Migration Script

Usage:
    export DATABASE_URL="postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres?sslmode=require"
    python backend/migrate_to_postgres.py

Schema Differences Handled:
    SQLite 'stories' column   ->  Current Model column
    -----------------------------------------------
    headline                  ->  title
    sources                   ->  source
    (missing)                 ->  published_at       (filled from latest_at)
    (missing)                 ->  sectors            (filled as '["General"]')
    (missing)                 ->  sector_summary     (filled as NULL)
    (missing)                 ->  trending_score     (filled as 0.0)

    SQLite 'articles' column  ->  Current Model column
    cluster_id (INTEGER)      ->  cluster_id (String, nullable)
    (missing)                 ->  embedding          (filled as NULL)

    SQLite 'clusters' column  ->  Current Model column
    id (INTEGER)              ->  id (String)
"""

import os
import sys
import json
import logging
import sqlite3
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# --- Paths ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SQLITE_PATH = os.path.join(PROJECT_ROOT, "news.db")
POSTGRES_URL = os.environ.get("DATABASE_URL")


def check_prerequisites():
    """Validate that everything needed is in place before starting."""
    if not POSTGRES_URL:
        logger.error("ERROR: DATABASE_URL environment variable not set.")
        logger.info("")
        logger.info("  export DATABASE_URL=\"postgresql://postgres.[ref]:[password]@...:5432/postgres?sslmode=require\"")
        logger.info("")
        sys.exit(1)

    if not os.path.exists(SQLITE_PATH):
        logger.error(f"SQLite database not found at: {SQLITE_PATH}")
        logger.info("Make sure news.db exists in the project root.")
        sys.exit(1)

    # Add project root to Python path for imports
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)


def create_postgres_tables():
    """Create all tables in PostgreSQL matching current models."""
    from sqlalchemy import create_engine
    from models.database import Base

    engine = create_engine(POSTGRES_URL, pool_size=2, max_overflow=2)
    Base.metadata.create_all(bind=engine)
    logger.info("  Tables created.\n")
    return engine.connect()


def read_sqlite_data(conn):
    """Read all data from SQLite tables."""
    articles = conn.execute(
        "SELECT id, title, url, source, published_at, content_snippet, fetched_at, cluster_id "
        "FROM articles"
    ).fetchall()
    logger.info(f"  Articles: {len(articles)} rows")

    stories = conn.execute(
        "SELECT id, headline, summary, why_it_matters, url, score, "
        "       article_count, sources, latest_at, created_at "
        "FROM stories"
    ).fetchall()
    logger.info(f"  Stories:  {len(stories)} rows")

    clusters = conn.execute(
        "SELECT id, theme FROM clusters"
    ).fetchall()
    logger.info(f"  Clusters: {len(clusters)} rows")

    return articles, stories, clusters


def migrate_articles(pg_conn, sqlite_articles):
    """Migrate articles. cluster_id was INTEGER, now String. embedding will be NULL."""
    from sqlalchemy import text

    inserted = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    for row in sqlite_articles:
        a_id, title, url, source, published_at, content_snippet, fetched_at, cluster_id = row
        cluster_id_str = str(cluster_id) if cluster_id is not None else None

        try:
            pg_conn.execute(
                text("""
                    INSERT INTO articles (id, title, url, source, published_at,
                                          content_snippet, fetched_at, cluster_id, embedding)
                    VALUES (:id, :title, :url, :source, :published_at,
                            :content_snippet, :fetched_at, :cluster_id, NULL)
                    ON CONFLICT (url) DO NOTHING
                """),
                {
                    "id": a_id,
                    "title": title,
                    "url": url,
                    "source": source,
                    "published_at": published_at,
                    "content_snippet": content_snippet,
                    "fetched_at": fetched_at or now,
                    "cluster_id": cluster_id_str,
                }
            )
            inserted += 1
        except Exception as e:
            logger.warning(f"    Warning: skipped article {a_id}: {e}")
            skipped += 1

    pg_conn.commit()
    return inserted, skipped


def migrate_stories(pg_conn, sqlite_stories):
    """Migrate stories with column renames and defaults for missing columns."""
    from sqlalchemy import text

    inserted = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    for row in sqlite_stories:
        s_id, headline, summary, why_it_matters, url, score, article_count, sources, latest_at, created_at = row

        try:
            # Note: id is autoincrement in PostgreSQL, so we don't insert old IDs.
            # Old SQLite story IDs are discarded - stories get fresh sequential IDs.
            pg_conn.execute(
                text("""
                    INSERT INTO stories (title, summary, why_it_matters, url, score,
                                         article_count, source, published_at, latest_at,
                                         created_at, sectors, sector_summary, trending_score)
                    VALUES (:title, :summary, :why_it_matters, :url, :score,
                            :article_count, :source, :published_at, :latest_at,
                            :created_at, :sectors, NULL, 0.0)
                """),
                {
                    "title": headline,
                    "summary": summary,
                    "why_it_matters": why_it_matters,
                    "url": url,
                    "score": score,
                    "article_count": article_count,
                    "source": sources or "",
                    "published_at": latest_at or now,
                    "latest_at": latest_at or now,
                    "created_at": created_at or now,
                    "sectors": json.dumps(["General"]),
                }
            )
            inserted += 1
        except Exception as e:
            logger.warning(f"    Warning: skipped story {s_id}: {e}")
            skipped += 1

    pg_conn.commit()
    return inserted, skipped


def migrate_clusters(pg_conn, sqlite_clusters):
    """Migrate clusters. IDs were INTEGER in SQLite, now String."""
    from sqlalchemy import text

    inserted = 0
    skipped = 0

    for row in sqlite_clusters:
        c_id, theme = row
        try:
            pg_conn.execute(
                text("""
                    INSERT INTO clusters (id, theme)
                    VALUES (:id, :theme)
                    ON CONFLICT DO NOTHING
                """),
                {"id": str(c_id), "theme": theme},
            )
            inserted += 1
        except Exception as e:
            logger.warning(f"    Warning: skipped cluster {c_id}: {e}")
            skipped += 1

    pg_conn.commit()
    return inserted, skipped


def main():
    logger.info("=" * 60)
    logger.info("  SQLite -> PostgreSQL Migration")
    logger.info("=" * 60)
    logger.info("")

    # Step 1: Validate prerequisites
    check_prerequisites()

    # Step 2: Read from SQLite
    logger.info("Reading from SQLite...")
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    articles, stories, clusters = read_sqlite_data(sqlite_conn)
    sqlite_conn.close()

    if not articles and not stories:
        logger.warning("No data found in SQLite. Nothing to migrate.")
        sys.exit(0)

    logger.info("")
    logger.info("Connecting to PostgreSQL...")
    pg_conn = create_postgres_tables()

    # Step 3: Migrate data
    logger.info("")
    logger.info("Migrating data...")
    logger.info("")

    logger.info("  [1/3] Articles...")
    art_ok, art_skip = migrate_articles(pg_conn, articles)

    logger.info("  [2/3] Stories...")
    st_ok, st_skip = migrate_stories(pg_conn, stories)

    logger.info("  [3/3] Clusters...")
    cl_ok, cl_skip = migrate_clusters(pg_conn, clusters)

    # Step 4: Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("  Migration Complete")
    logger.info("=" * 60)
    logger.info("")
    logger.info(f"  Articles:   {art_ok} migrated, {art_skip} skipped")
    logger.info(f"  Stories:    {st_ok} migrated, {st_skip} skipped")
    logger.info(f"  Clusters:   {cl_ok} migrated, {cl_skip} skipped")

    total = art_ok + st_ok + cl_ok
    logger.info("")
    if total > 0:
        logger.info(f"  Successfully migrated {total} records to PostgreSQL!")
    else:
        logger.info("  No records were migrated. Check for errors above.")

    pg_conn.close()

    logger.info("")
    logger.info("Verify with:")
    logger.info("  python -c \"import os; from sqlalchemy import create_engine, text;"
                " e = create_engine(os.environ['DATABASE_URL']);"
                " c = e.connect();"
                " print(c.execute(text('SELECT COUNT(*) FROM articles')).scalar(), 'articles');"
                " print(c.execute(text('SELECT COUNT(*) FROM stories')).scalar(), 'stories');"
                " print(c.execute(text('SELECT COUNT(*) FROM clusters')).scalar(), 'clusters')\"")


if __name__ == "__main__":
    main()
