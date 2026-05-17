import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from loguru import logger

from services.fetch_news import fetch_rss_feeds
from services.clean_news import clean_articles
from services.cluster_news import cluster_articles
from services.classify_news import classify_sectors
from services.summarize_news import summarize_stories
from services.rank_news import rank_clusters
from services.market_data import fetch_and_store_market_data
from services.briefing import generate_briefing
from upsc_filter import score_relevance, score_novelty, record_story
from upsc_analyzer import generate_exam_playbook
from models.database import (
    save_articles, save_stories,
    init_db, save_sector_summary, SessionLocal
)

_scheduler = BackgroundScheduler()


def _build_cluster_text(cluster: list[dict]) -> tuple[str, list[str]]:
    """Build a combined text snippet from a cluster for classification.

    Also collects all source-assigned sector tags from the articles in the
    cluster. The most common source sectors are returned alongside the text
    so the classifier can use them as high-confidence primary tags.

    Returns:
        (combined_text, source_sectors)  — e.g. ("text...", ["India", "Tech"])
    """
    parts = []
    sector_counts: dict[str, int] = {}
    for a in cluster[:5]:
        title = a.get("title", "")
        snippet = a.get("content_snippet", "")[:150]
        parts.append(f"{title}. {snippet}" if snippet else title)
        # Collect source-assigned sectors from each article
        for sec in a.get("source_sectors", []):
            sector_counts[sec] = sector_counts.get(sec, 0) + 1

    # Return all source sectors from the cluster — source tags are high-confidence
    # (they come from RSS feed config, not ML). Even 1 article's tag is reliable.
    source_sectors = list(sector_counts.keys()) if sector_counts else []

    return " ".join(parts), source_sectors


def run_pipeline() -> None:
    """Run the full news processing pipeline.

    Pipeline steps 11 (market data) and 12 (briefing) are I/O-bound and
    independent of each other, so they run in parallel via ThreadPoolExecutor.
    Database writes (steps 3, 9, 10) share a single session for batching.
    """
    start = time.time()
    logger.info("=== Pipeline start ===")

    # ── Post-pipeline already runs from _run_post_pipeline() ──

    try:
        # ── Phase 1: Core pipeline (sequential) ──

        # 1. Fetch
        logger.info("Fetching articles...")
        articles = fetch_rss_feeds()
        logger.info(f"Fetched {len(articles)} articles")

        # 2. Clean
        articles = clean_articles(articles)
        logger.info(f"Cleaned {len(articles)} articles")

        # 3-10 use a single DB session for batched writes
        db: Session = SessionLocal()
        try:
            # 3. Persist (batched)
            inserted = save_articles(articles, db=db)
            logger.info(f"Inserted {inserted} new articles")

            # Commit articles so they're persisted
            db.commit()

            # 4. Use freshly fetched articles for clustering (they have correct source_sectors
            # from the current config. Re-reading from DB via get_recent_articles can return
            # empty source_sectors for articles whose source name doesn't match current config.)
            db.close()
            recent = articles
            db = SessionLocal()
            logger.info(f"Processing {len(recent)} articles for clustering")

            # Limit articles to prevent OOM on Render's free tier (512 MB RAM)
            # Now that classification uses source-assigned sectors, we can increase
            # the limit — more articles means better sector coverage per source.
            MAX_ARTICLES = 1000
            if len(recent) > MAX_ARTICLES:
                logger.info(f"Limiting to {MAX_ARTICLES} articles for clustering (had {len(recent)})")
                recent = recent[:MAX_ARTICLES]

            if not recent:
                logger.warning("No recent articles to process")
                return

            # 5. Cluster using HDBSCAN with topic modeling
            clusters = cluster_articles(recent)
            logger.info(f"Created {len(clusters)} clusters")
            cluster_sizes = [len(c) for c in clusters]
            if cluster_sizes:
                logger.info(
                    f"Cluster sizes: min={min(cluster_sizes)} max={max(cluster_sizes)} "
                    f"avg={sum(cluster_sizes)/len(cluster_sizes):.1f}"
                )

            # 6. Rank clusters
            ranked = rank_clusters(clusters)
            logger.info(f"Ranked {len(ranked)} stories")

            # 7. UPSC syllabus-aware relevance scoring
            # This runs locally using TF-IDF + cosine similarity — NO Gemini calls.
            for i, story in enumerate(ranked):
                cluster = story["cluster"]
                text, source_sectors = _build_cluster_text(cluster)
                # Classify sectors (original)
                sectors = classify_sectors(text, source_sectors=source_sectors)
                story["sectors"] = sectors
                # UPSC relevance scoring (local ML, no API call)
                upsc_result = score_relevance(text)
                novelty = score_novelty(text)
                story["is_relevant"] = upsc_result["is_relevant"]
                story["relevance_score"] = upsc_result["relevance_score"]
                story["priority_score"] = upsc_result["priority_score"]
                story["novelty_score"] = novelty["novelty_score"]
                story["gs_paper"] = upsc_result["gs_paper"]
                story["subtopics"] = upsc_result["subtopics"]
                story["matched_criteria"] = upsc_result["matched_criteria"]
                # Record for future novelty comparison
                record_story(text)
                logger.info(f"[UPSC] Story {i}: relevance={upsc_result['relevance_score']:.2f}, "
                    f"priority={upsc_result['priority_score']:.2f}, gs_paper={upsc_result['gs_paper']}")

            # 8. Filter out low-relevance stories before summarization
            # This aggressively reduces work for Gemini later.
            UPSC_RELEVANCE_THRESHOLD = 0.30
            filtered_stories = [s for s in ranked if s.get("relevance_score", 0) >= UPSC_RELEVANCE_THRESHOLD]
            filtered_out = len(ranked) - len(filtered_stories)
            logger.info(f"UPSC filter: kept {len(filtered_stories)} stories, filtered out {filtered_out} low-relevance stories")

            if not filtered_stories:
                logger.warning("No stories passed UPSC relevance filter — skipping summarization")
                # Still need to save an empty story list so DB resets properly
                save_stories([], db=db)
                db.commit()
                stories = []
            else:
                # 9. Summarize (only UPSC-relevant stories)
                stories = summarize_stories(filtered_stories)

            # 10. Gemini-powered exam intelligence (only for high-priority stories)
            # Only call Gemini if relevance_score >= 0.72.
            GEMINI_RELEVANCE_THRESHOLD = 0.72
            for story in stories:
                rel_score = story.get("relevance_score", 0)
                if rel_score >= GEMINI_RELEVANCE_THRESHOLD:
                    try:
                        playbook = generate_exam_playbook(
                            headline=story["title"],
                            summary=story.get("summary", ""),
                            why_it_matters=story.get("why_it_matters", ""),
                            gs_paper=story.get("gs_paper", "GS Paper II"),
                            subtopics=story.get("subtopics", []),
                            matched_criteria=len(story.get("matched_criteria", [])),
                            relevance_score=rel_score,
                        )
                        story["exam_playbook"] = playbook
                        logger.info(f"[GEMINI] Generated exam playbook for: {story['title'][:60]}")
                    except Exception as e:
                        logger.warning(f"[GEMINI] Analysis failed for '{story['title'][:60]}': {e}")
                        story["exam_playbook"] = None
                else:
                    story["exam_playbook"] = None

            if not filtered_stories:
                db.close()
                _run_post_pipeline()
                elapsed = time.time() - start
                logger.info(f"=== Pipeline complete in {elapsed:.1f}s (no UPSC stories) ===")
                return

            # 11. Generate & save sector summaries (batched)
            sector_groups: dict[str, list[dict]] = {}
            for s in stories:
                for sector in s.get("sectors", ["General"]):
                    sector_groups.setdefault(sector, []).append(s)

            for sector, sector_stories in sector_groups.items():
                headlines = [s["title"] for s in sector_stories[:5]]
                summary = f"{len(sector_stories)} stories in {sector}. " + " ".join(
                    f"'{h}'" for h in headlines[:3]
                )
                try:
                    save_sector_summary(sector, summary, len(sector_stories), db=db)
                except Exception as e:
                    logger.warning(f"Failed to save sector summary for {sector}: {e}")

            # 12. Save stories (batched)
            logger.info(f"Saving {len(stories)} stories...")
            save_stories(stories, db=db)
            logger.info(f"Saved {len(stories)} stories")

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # ── Phase 2: I/O parallel (market data + briefing run concurrently) ──
        _run_post_pipeline()

        elapsed = time.time() - start
        logger.info(f"=== Pipeline complete in {elapsed:.1f}s ===")

    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        elapsed = time.time() - start
        logger.info(f"=== Pipeline failed after {elapsed:.1f}s ===")


def _run_post_pipeline() -> None:
    """Run market data and briefing in parallel (both are I/O-bound)."""
    def _market():
        md = fetch_and_store_market_data()
        logger.info(f"Fetched {len(md)} market data points")

    def _briefing():
        generate_briefing()
        logger.info("Briefing generated")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_market): "market data",
            executor.submit(_briefing): "briefing",
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.warning(f"{name} failed: {e}")


def start_scheduler():
    """Start the APScheduler to run pipeline daily."""
    if _scheduler.get_jobs():
        return  # Already started

    _scheduler.add_job(
        run_pipeline,
        "interval",
        hours=6,
        id="news_pipeline",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started — pipeline runs every 6 hours")
