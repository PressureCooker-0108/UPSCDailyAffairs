import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    generate_review_verdict,
    get_ai_runtime_status,
    prepare_ai_run,
    probe_openrouter,
)
from ml_classifier import ml_review_verdict, is_model_loaded as ml_model_loaded

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
    "total_ml_predictions": 0,
    "total_ai_reviews": 0,
}

# ── Scheduled Job Status ──
_training_data_status: dict = {
    "is_running": False,
    "last_run_start": None,
    "last_run_end": None,
    "last_run_duration": None,
    "last_run_success": None,
    "total_collections": 0,
}

_retrain_status: dict = {
    "is_running": False,
    "last_run_start": None,
    "last_run_end": None,
    "last_run_duration": None,
    "last_run_success": None,
    "total_retrains": 0,
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
    ml_predictions = 0  # Silent ML predictions (training data collection)
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

            # 9. AI review verdicts + exam playbooks + silent ML predictions
            # Two-phase processing:
            #   Phase 0 — ML classifier (silent, collects training data)
            #   Phase 1 — AI review verdict (PASS/REJECT)
            #   Phase 2 — Full exam playbook (for PASS stories)
            #
            # ML runs SILENTLY to collect predictions alongside AI ground truth.
            # These ML + AI pairs are used to retrain and improve the model over time.
            # The ML model does NOT gate what goes through — AI reviews always run.
            # Eventually, accumulated training data will let the ML model fine-tune
            # the TF-IDF filtering itself.
            ml_available = ml_model_loaded()
            if ml_available:
                logger.info("[ML] ML classifier loaded — running silently for training data collection")
            else:
                logger.info("[ML] ML classifier not loaded — skipping ML predictions")

            existing_playbooks = get_existing_playbooks()
            for story in stories:
                rel_score = story.get("relevance_score", 0)
                if rel_score >= AI_RELEVANCE_THRESHOLD:
                    ai_eligible += 1

                    # Build text for ML + AI review
                    cluster_text = story.get("cluster", [])
                    full_text = ""
                    if cluster_text:
                        articles_text = []
                        for a in cluster_text[:3]:
                            articles_text.append(
                                a.get("content_snippet", a.get("title", ""))
                            )
                        full_text = " ".join(articles_text)
                    if not full_text:
                        full_text = story.get("summary", story.get("title", ""))

                    # ── Phase 0: Silent ML Prediction (training data collection) ──
                    # ML verdict is stored alongside AI verdict for future retraining.
                    # Does NOT affect whether AI review runs.
                    ml_result = None
                    if ml_available:
                        try:
                            ml_result = ml_review_verdict(
                                text=full_text,
                                title=story.get("title", ""),
                            )
                            if ml_result:
                                ml_predictions += 1
                                story["ml_prediction"] = {
                                    "verdict": ml_result.get("verdict"),
                                    "confidence": ml_result.get("confidence"),
                                    "probabilities": ml_result.get("probabilities"),
                                }
                                logger.debug(
                                    f"[ML] Silently predicted {ml_result['verdict']} "
                                    f"(conf={ml_result['confidence']:.2f}) for "
                                    f"'{story['title'][:60]}'"
                                )
                        except Exception as e:
                            logger.warning(f"[ML] Prediction failed for '{story['title'][:60]}': {e}")

                    # ── Phase 1: AI Review (always runs) ──
                    existing = existing_playbooks.get(story["title"])
                    if existing is not None:
                        story["exam_playbook"] = existing
                        story["ai_review"] = {"verdict": "PASS", "reasoning": "Cached from previous run"}
                        ai_skipped_cached += 1
                        logger.info(f"[AI] Reused existing playbook for: {story['title'][:60]}")
                        continue

                    review = None
                    try:
                        review = generate_review_verdict(
                            headline=story["title"],
                            full_text=full_text,
                            gs_paper=story.get("gs_paper", ""),
                            subtopics=story.get("subtopics", []),
                            why_it_matters=story.get("why_it_matters", ""),
                        )
                    except Exception as e:
                        logger.warning(f"[AI Review] Failed for '{story['title'][:60]}': {e}")
                        review = None

                    story["ai_review"] = review

                    if review and review.get("verdict") == "REJECT":
                        story["exam_playbook"] = None
                        logger.info(
                            f"[AI Review] REJECTED '{story['title'][:60]}' — skipping playbook "
                            f"(reason: {review.get('reasoning', 'N/A')[:80]})"
                        )
                        continue

                    # ── Exam Playbook (for PASS stories) ──
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
                    story["ai_review"] = None

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
        _pipeline_status["total_ml_predictions"] += ml_predictions
        _pipeline_status["total_ai_reviews"] += ai_success

        logger.info(
            "[AI] Run summary "
            f"(eligible={ai_eligible}, cached={ai_skipped_cached}, "
            f"budget_skipped={ai_skipped_budget}, success={ai_success}, "
            f"failures={ai_failures}, used={get_ai_runtime_status()['ai_calls_used']})"
        )
        logger.info(f"[ML] Run summary: {ml_predictions} silent predictions made")
        if ml_predictions > 0:
            logger.info("[ML] Predictions stored alongside AI ground truth for future retraining")

        logger.info(f"=== Pipeline complete in {elapsed:.1f}s ===")

    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        elapsed = time.time() - start
        _pipeline_status["is_running"] = False
        _pipeline_status["last_run_end"] = datetime.now(timezone.utc).isoformat()
        _pipeline_status["last_run_duration"] = round(elapsed, 1)
        _pipeline_status["last_run_success"] = False
        logger.info(f"=== Pipeline failed after {elapsed:.1f}s ===")



def collect_training_data() -> None:
    """Scheduled job: generate training data from pipeline-saved stories.

    Runs every 2 days. Reads saved stories from the Summary table
    (which have both ML predictions and AI review verdicts from the
    pipeline), and packages them as training_data.jsonl for model
    retraining. No fresh RSS fetches or OpenRouter calls — avoids
    race conditions with the main pipeline.
    """
    start = time.time()
    _training_data_status["is_running"] = True
    _training_data_status["last_run_start"] = datetime.now(timezone.utc).isoformat()
    logger.info("=== Training Data Collection (scheduled every 2 days) ===")

    try:
        from generate_training_data import (
            fetch_from_db_with_ml, fetch_user_reviews, save_training_data
        )

        # Step 1a: Read pipeline-saved stories from DB (ML predictions + AI reviews)
        stories = fetch_from_db_with_ml()
        logger.info(f"[Train-Data] Loaded {len(stories)} pipeline stories from DB")
        with_ml = sum(1 for s in stories if s.get("ml_prediction"))
        with_ai = sum(1 for s in stories if s.get("ai_review"))
        logger.info(f"[Train-Data] {with_ml} with ML predictions, {with_ai} with AI reviews")

        # Step 1b: Read user reviews from DB (human ground truth)
        user_reviews = fetch_user_reviews()
        logger.info(f"[Train-Data] Loaded {len(user_reviews)} user reviews from DB")
        with_verdict = sum(1 for r in user_reviews if r.get("ai_review"))
        logger.info(f"[Train-Data] {with_verdict} user reviews with PASS/REJECT signal")

        # Combine both sources into one dataset
        all_data = stories + user_reviews

        if not all_data:
            logger.warning("[Train-Data] No data found in DB — skipping")
            _training_data_status["last_run_success"] = False
            return

        # Step 2: Save combined data to a dated file + update latest
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dated_path = f"/tmp/training_data_{today}.jsonl"
        save_training_data(all_data, dated_path)

        latest_path = Path("/tmp/training_data.jsonl")
        if latest_path.exists():
            latest_path.unlink()
        shutil.copy2(dated_path, latest_path)
        logger.info(f"[Train-Data] Updated /tmp/training_data.jsonl ({len(all_data)} records: {len(stories)} pipeline + {len(user_reviews)} user reviews)")

        _training_data_status["last_run_success"] = True
        _training_data_status["total_collections"] += 1

    except Exception as e:
        logger.exception(f"[Train-Data] Scheduled collection failed: {e}")
        _training_data_status["last_run_success"] = False
    finally:
        elapsed = time.time() - start
        _training_data_status["is_running"] = False
        _training_data_status["last_run_end"] = datetime.now(timezone.utc).isoformat()
        _training_data_status["last_run_duration"] = round(elapsed, 1)
        logger.info(f"=== Training data collection finished in {elapsed:.1f}s ===")


def retrain_ml_model() -> None:
    """Scheduled job: retrain the ML model on accumulated training data.

    Runs every 4 days. Uses the latest training_data.jsonl (which contains
    fresh AI review labels collected by the 2-day scheduled collection)
    and re-trains + re-tunes the ML classifier.

    After retraining, the new model is hot-reloaded into the running
    pipeline via force_reload() — no restart needed.
    """
    start = time.time()
    _retrain_status["is_running"] = True
    _retrain_status["last_run_start"] = datetime.now(timezone.utc).isoformat()
    logger.info("=== ML Model Retrain (scheduled every 4 days) ===")

    try:
        from train_ml_classifier import (
            prepare_dataset, train_model, evaluate_model, save_model
        )
        from ml_classifier import force_reload, set_confidence_threshold

        # Read the latest training_data.jsonl directly (no API round-trip)
        latest_path = Path("/tmp/training_data.jsonl")
        if not latest_path.exists():
            logger.warning("[ML Retrain] No training_data.jsonl found — skipping")
            _retrain_status["last_run_success"] = False
            return

        with open(latest_path, encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        logger.info(f"[ML Retrain] Loaded {len(records)} records from {latest_path}")

        # Filter to records with AI reviews (ground truth)
        labeled = [r for r in records if r.get("ai_review")]
        logger.info(f"[ML Retrain] {len(labeled)} records with AI reviews")

        if len(labeled) < 10:
            logger.warning(f"[ML Retrain] Only {len(labeled)} labeled records — need 10+ to retrain")
            _retrain_status["last_run_success"] = False
            return

        texts, labels, class_counts = prepare_dataset(labeled, binary=True)
        logger.info(f"[ML Retrain] Prepared {len(texts)} samples (classes: {class_counts})")

        if len(texts) < 10:
            logger.warning(f"[ML Retrain] Only {len(texts)} usable samples — need 10+")
            _retrain_status["last_run_success"] = False
            return

        pipeline = train_model(texts, labels)
        eval_result = evaluate_model(pipeline, texts, labels)
        accuracy = eval_result.get("accuracy", 0.0) if eval_result else 0.0
        logger.info(f"[ML Retrain] Accuracy: {accuracy:.4f}")

        output_path = os.path.join(os.path.dirname(__file__), "ml_models", "ml_model.joblib")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        save_model(pipeline, output_path)

        loaded = force_reload(output_path)
        logger.info(f"[ML Retrain] Model saved and reloaded: {loaded}")

        # Auto-tune threshold down to 0.50, step 0.05
        new_threshold = 0.60  # default
        try:
            from ml_auto_retrain import auto_tune_threshold
            new_threshold = auto_tune_threshold(pipeline, texts, labels)
        except Exception:
            pass
        set_confidence_threshold(new_threshold)
        logger.info(f"[ML Retrain] Threshold set to: {new_threshold:.2f}")

        _retrain_status["last_run_success"] = True
        _retrain_status["total_retrains"] += 1

    except Exception as e:
        logger.exception(f"[ML Retrain] Scheduled retrain failed: {e}")
        _retrain_status["last_run_success"] = False
    finally:
        elapsed = time.time() - start
        _retrain_status["is_running"] = False
        _retrain_status["last_run_end"] = datetime.now(timezone.utc).isoformat()
        _retrain_status["last_run_duration"] = round(elapsed, 1)
        logger.info(f"=== ML retrain finished in {elapsed:.1f}s ===")


# ── Helper: expose status via API endpoints ──

def get_training_data_status() -> dict:
    """Return current training data collection status."""
    return dict(_training_data_status)


def get_retrain_status() -> dict:
    """Return current retrain job status."""
    return dict(_retrain_status)


def start_scheduler():
    """Start the APScheduler with all periodic jobs:
      - Pipeline: every 6 hours (fetch, analyze, serve stories)
      - Training data collection: every 2 days (AI review labels)
      - ML model retrain: every 4 days (retrain on accumulated labels)

    Staggered so data is collected before retrain uses it.
    """
    if _scheduler.get_jobs():
        return

    # Main pipeline — every 6 hours
    _scheduler.add_job(
        run_pipeline,
        "interval",
        hours=6,
        id="news_pipeline",
        replace_existing=True,
    )
    logger.info("Scheduled: pipeline every 6 hours")

    # Training data collection — every 2 days
    # Offset by 2 hours from startup to let the first pipeline run finish
    _scheduler.add_job(
        collect_training_data,
        "interval",
        hours=48,
        start_date=datetime.now(timezone.utc) + timedelta(hours=2),
        id="collect_training_data",
        replace_existing=True,
    )
    logger.info("Scheduled: training data collection every 2 days (first run in 2h)")

    # ML retrain — every 4 days, 12h after collection
    # (collection at day 0, retrain at day 0+12h — data is ready)
    _scheduler.add_job(
        retrain_ml_model,
        "interval",
        hours=96,
        start_date=datetime.now(timezone.utc) + timedelta(hours=12),
        id="retrain_ml_model",
        replace_existing=True,
    )
    logger.info("Scheduled: ML model retrain every 4 days (first run in 12h)")

    _scheduler.start()
    logger.info("Scheduler started with all 3 jobs")