import time
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from loguru import logger

from services.fetch_news import fetch_rss_feeds
from services.clean_news import clean_articles
from services.cluster_news import cluster_articles
from services.summarize_news import summarize_stories
from services.rank_news import rank_clusters
from upsc_filter import generate_why_it_matters, score_relevance, score_novelty, record_story
from upsc_analyzer import (
    AI_RELEVANCE_THRESHOLD,
    generate_exam_playbook,
    get_ai_runtime_status,
    prepare_ai_run,
    probe_openrouter,
)
from models.database import (
    save_articles, save_stories,
    get_existing_playbooks,
    init_db, SessionLocal
)

# ── Pipeline Status ──
_pipeline_status: dict = {
    "is_running": False,
    "last_run_start": None,
    "last_run_end": None,
    "last_run_duration": None,
    "last_run_success": None,
    "total_stories_processed": 0,
    "total_ai_success": 0,
    "total_ai_failures": 0,
}


def get_pipeline_status() -> dict:
    """Return current pipeline status with timing and stats."""
    return dict(_pipeline_status)


_scheduler = BackgroundScheduler()


def _build_cluster_text(cluster: list[dict]) -> str:
    """Build a combined text snippet from a cluster."""
    parts = []
    for a in cluster[:5]:
        title = a.get("title", "")
        snippet = a.get("content_snippet", "")[:150]
        parts.append(f"{title}. {snippet}" if snippet else title)
    return " ".join(parts)


def run_pipeline() -> None:
    """Run the UPSC-focused news pipeline."""
    start = time.time()
    _pipeline_status["is_running"] = True
    _pipeline_status["last_run_start"] = datetime.now(timezone.utc).isoformat()
    logger.info("=== Pipeline start ===")

    ai_success = 0
    ai_failures = 0
    ai_eligible = 0
    ai_skipped_cached = 0
    ai_skipped_budget = 0

    ai_status = prepare_ai_run()
    logger.info(
        "[AI] Run prepared "
        f"(model={ai_status['model']}, free_tier={ai_status['is_free_tier']}, "
        f"run_cap={ai_status['run_cap']}, has_key_info={ai_status['has_key_info']})"
    )

    # Health-check OpenRouter before processing
    health = probe_openrouter()
    if health["status"] != "ok":
        logger.warning(f"[AI Health Check] OpenRouter may be unreachable: {health}")
    else:
        logger.info("[AI Health Check] OpenRouter is reachable")

    try:
        # 1. Fetch
        logger.info("Fetching articles...")
        articles = fetch_rss_feeds()
        logger.info(f"Fetched {len(articles)} articles")

        # 2. Clean
        articles = clean_articles(articles)
        logger.info(f"Cleaned {len(articles)} articles")

        db: Session = SessionLocal()
        try:
            # 3. Persist articles
            inserted = save_articles(articles, db=db)
            logger.info(f"Inserted {inserted} new articles")
            db.commit()
            db.close()
            db = SessionLocal()

            recent = articles
            logger.info(f"Processing {len(recent)} articles for clustering")

            MAX_ARTICLES = 1000
            if len(recent) > MAX_ARTICLES:
                logger.info(f"Limiting to {MAX_ARTICLES} articles for clustering (had {len(recent)})")
                recent = recent[:MAX_ARTICLES]

            if not recent:
                logger.warning("No recent articles to process")
                _pipeline_status["is_running"] = False
                _pipeline_status["last_run_end"] = datetime.now(timezone.utc).isoformat()
                elapsed = time.time() - start
                _pipeline_status["last_run_duration"] = round(elapsed, 1)
                _pipeline_status["last_run_success"] = True
                return

            # 4. Cluster
            clusters = cluster_articles(recent)
            logger.info(f"Created {len(clusters)} clusters")
            cluster_sizes = [len(c) for c in clusters]
            if cluster_sizes:
                logger.info(
                    f"Cluster sizes: min={min(cluster_sizes)} max={max(cluster_sizes)} "
                    f"avg={sum(cluster_sizes)/len(cluster_sizes):.1f}"
                )

            # 5. Rank clusters
            ranked = rank_clusters(clusters)
            logger.info(f"Ranked {len(ranked)} stories")

            # 6. UPSC syllabus-aware relevance scoring (local TF-IDF, no API calls)
            for i, story in enumerate(ranked):
                cluster = story["cluster"]
                text = _build_cluster_text(cluster)
                upsc_result = score_relevance(text)
                novelty = score_novelty(text)
                story["is_relevant"] = upsc_result["is_relevant"]
                story["relevance_score"] = upsc_result["relevance_score"]
                story["priority_score"] = upsc_result["priority_score"]
                story["novelty_score"] = novelty["novelty_score"]
                story["gs_paper"] = upsc_result["gs_paper"]
                story["subtopics"] = upsc_result["subtopics"]
                story["matched_criteria"] = upsc_result["matched_criteria"]
                story["why_it_matters"] = generate_why_it_matters(
                    relevance=upsc_result,
                    matched_criteria=upsc_result.get("matched_criteria", []),
                )
                record_story(text)
                logger.info(f"[UPSC] Story {i}: relevance={upsc_result['relevance_score']:.2f}, "
                    f"priority={upsc_result['priority_score']:.2f}, gs_paper={upsc_result['gs_paper']}")

            # 7. Filter low-relevance stories
            UPSC_RELEVANCE_THRESHOLD = 0.30
            filtered_stories = [s for s in ranked if s.get("relevance_score", 0) >= UPSC_RELEVANCE_THRESHOLD]
            filtered_out = len(ranked) - len(filtered_stories)
            logger.info(f"UPSC filter: kept {len(filtered_stories)} stories, filtered out {filtered_out}")

            if not filtered_stories:
                logger.warning("No stories passed UPSC relevance filter — skipping summarization")
                save_stories([], db=db)
                db.commit()
                stories = []
            else:
                # 8. Summarize (only UPSC-relevant stories)
                stories = summarize_stories(filtered_stories)

            # 9. AI-powered exam intelligence (for high-priority stories)
            # OpenRouter pacing and retry behavior is enforced inside
            # upsc_analyzer.generate_exam_playbook(), including free-tier
            # budgeting, Retry-After handling, and run-level exhaustion.
            existing_playbooks = get_existing_playbooks()
            for story in stories:
                rel_score = story.get("relevance_score", 0)
                if rel_score >= AI_RELEVANCE_THRESHOLD:
                    ai_eligible += 1
                    existing = existing_playbooks.get(story["title"])
                    if existing is not None:
                        story["exam_playbook"] = existing
                        ai_skipped_cached += 1
                        logger.info(f"[AI] Reused existing playbook for: {story['title'][:60]}")
                        continue

                    runtime_status = get_ai_runtime_status()
                    if runtime_status.get("budget_exhausted"):
                        ai_skipped_budget += 1
                        story["exam_playbook"] = None
                        logger.warning(
                            f"[AI] Budget exhausted earlier in this run; "
                            f"skipping: {story['title'][:60]}"
                        )
                        continue

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
                        if playbook:
                            ai_success += 1
                            logger.info(f"[AI] Generated exam playbook for: {story['title'][:60]}")
                        else:
                            runtime_status = get_ai_runtime_status()
                            last_result = runtime_status.get("last_result")
                            if last_result in {"skipped_budget", "rate_limited"}:
                                ai_skipped_budget += 1
                                logger.warning(
                                    f"[AI] Skipped playbook for rate-limit budget reasons: "
                                    f"{story['title'][:60]}"
                                )
                            else:
                                ai_failures += 1
                                logger.warning(
                                    f"[AI] Failed to generate playbook for: "
                                    f"{story['title'][:60]} (reason={last_result})"
                                )
                    except Exception as e:
                        ai_failures += 1
                        logger.warning(f"[AI] Analysis failed for '{story['title'][:60]}': {e}")
                        story["exam_playbook"] = None
                else:
                    story["exam_playbook"] = None

            if not filtered_stories:
                db.close()
                elapsed = time.time() - start
                _pipeline_status["is_running"] = False
                _pipeline_status["last_run_end"] = datetime.now(timezone.utc).isoformat()
                _pipeline_status["last_run_duration"] = round(elapsed, 1)
                _pipeline_status["last_run_success"] = True
                logger.info(f"=== Pipeline complete in {elapsed:.1f}s (no UPSC stories) ===")
                return

            # 10. Save stories
            logger.info(f"Saving {len(stories)} stories...")
            save_stories(stories, db=db)
            logger.info(f"Saved {len(stories)} stories")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        elapsed = time.time() - start
        _pipeline_status["is_running"] = False
        _pipeline_status["last_run_end"] = datetime.now(timezone.utc).isoformat()
        _pipeline_status["last_run_duration"] = round(elapsed, 1)
        _pipeline_status["last_run_success"] = True
        _pipeline_status["total_stories_processed"] = len(filtered_stories)
        _pipeline_status["total_ai_success"] += ai_success
        _pipeline_status["total_ai_failures"] += ai_failures
        logger.info(
            "[AI] Run summary "
            f"(eligible={ai_eligible}, cached={ai_skipped_cached}, "
            f"budget_skipped={ai_skipped_budget}, success={ai_success}, "
            f"failures={ai_failures}, used={get_ai_runtime_status()['ai_calls_used']})"
        )
        logger.info(f"=== Pipeline complete in {elapsed:.1f}s ===")

    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        elapsed = time.time() - start
        _pipeline_status["is_running"] = False
        _pipeline_status["last_run_end"] = datetime.now(timezone.utc).isoformat()
        _pipeline_status["last_run_duration"] = round(elapsed, 1)
        _pipeline_status["last_run_success"] = False
        logger.info(f"=== Pipeline failed after {elapsed:.1f}s ===")


def start_scheduler():
    """Start the APScheduler to run pipeline every 6 hours."""
    if _scheduler.get_jobs():
        return

    _scheduler.add_job(
        run_pipeline,
        "interval",
        hours=6,
        id="news_pipeline",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started — pipeline runs every 6 hours")
