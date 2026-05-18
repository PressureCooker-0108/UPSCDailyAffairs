"""
generate_training_data.py — Batch AI training data generator.

Fetches articles from all RSS sources, runs them through the TF-IDF
syllabus classifier (free, no API cost), and then generates AI review
verdicts (PASS/FLAG/REJECT) using OpenRouter's multi-key round-robin.

Outputs a JSONL file where each line is one article with:
  - Raw article fields (title, source, text)
  - TF-IDF syllabus features (relevance_score, gs_paper, subtopics, etc.)
  - AI review verdict (verdict, confidence, reasoning)
  - ML prediction (if available from pipeline runs)

This data can be used to train an ML classifier that replaces or
augments the AI review step — making it free and instant.

Usage:
  python generate_training_data.py                          # Fresh RSS fetch + AI reviews
  python generate_training_data.py --from-db                # Use saved stories from DB (includes ML predictions)
  python generate_training_data.py --max-articles 500       # Fetch up to 500
  python generate_training_data.py --output train.jsonl
  python generate_training_data.py --skip-ai                # TF-IDF only, no AI calls
  python generate_training_data.py --no-fetch               # Use raw articles from DB (no ML predictions)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# Ensure backend directory is importable
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.fetch_news import fetch_rss_feeds
from upsc_filter import classify_article, score_relevance, _check_irrelevant
from upsc_analyzer import generate_review_verdict, prepare_ai_run, get_ai_runtime_status, probe_openrouter
from models.database import init_db, SessionLocal, get_upsc_stories, get_reviews
from models.models import Article


# ──────────────────────────────────────────────
#  Training Data Generator
# ──────────────────────────────────────────────

def build_article_text(article: dict) -> str:
    """Build the combined text for classification."""
    title = article.get("title", "")
    snippet = article.get("content_snippet", "")[:300]
    return f"{title}. {snippet}" if snippet else title


def run_tfidf_pipeline(articles: list[dict]) -> list[dict]:
    """Run TF-IDF syllabus classification on all articles (free, no API cost).

    For each article, computes:
      - relevance_score
      - gs_paper, subtopics
      - matched criteria count
      - irrelevant pattern detection
      - classification confidence

    Returns enriched articles list.
    """
    enriched = []
    skipped = 0
    for i, article in enumerate(articles):
        text = build_article_text(article)
        if not text.strip():
            skipped += 1
            continue

        # 1. Check for clearly irrelevant content
        is_irrelevant = _check_irrelevant(text)

        # 2. Syllabus classification
        classification = classify_article(text)

        # 3. Relevance scoring
        relevance = score_relevance(text, classification)

        enriched.append({
            "title": article.get("title", ""),
            "url": article.get("url", ""),
            "source": article.get("source", ""),
            "source_type": article.get("source_type", "news"),
            "authority_score": article.get("authority_score", 0.5),
            "text": text[:1000],  # Keep manageable
            "published_at": article.get("published_at", ""),
            "tfidf_features": {
                "relevance_score": relevance.get("relevance_score", 0.0),
                "gs_paper": relevance.get("gs_paper", "Unknown"),
                "subtopics": relevance.get("subtopics", []),
                "confidence": relevance.get("confidence", 0.0),
                "matched_criteria_count": len(relevance.get("matched_criteria", [])),
                "is_relevant": relevance.get("is_relevant", False),
                "is_irrelevant_content": is_irrelevant,
            },
        })

        if (i + 1) % 50 == 0:
            logger.info(f"[TF-IDF] Processed {i + 1}/{len(articles)} articles...")

    logger.info(
        f"[TF-IDF] Complete: {len(enriched)} enriched, {skipped} skipped, "
        f"{sum(1 for e in enriched if e['tfidf_features']['is_relevant'])} relevant"
    )
    return enriched


def _save_partial(results: list[dict], output_path: str) -> None:
    """Save partial results incrementally so nothing is lost if the process is interrupted."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in results:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def run_ai_reviews(enriched: list[dict], max_articles: int = 0, timeout_seconds: int = 600) -> list[dict]:
    """Generate AI review verdicts for enriched articles.

    Uses the round-robin multi-key system from upsc_analyzer.
    Only reviews articles that passed the TF-IDF filter (is_relevant=True).

    Features:
      - timeout_seconds: hard stop after this many seconds (default 10 min)
      - Incremental saving every 10 articles to a temp file
      - Graceful handling of API errors (logs and continues)
    """
    # Prepare AI budget
    status = prepare_ai_run()
    logger.info(f"[AI] Budget prepared: {status}")

    # Health check
    health = probe_openrouter()
    if health["status"] != "ok":
        logger.warning(f"[AI] OpenRouter health check failed: {health.get('message', 'unknown')}")
        logger.warning("[AI] Will try regardless — some keys may work.")

    # Filter to relevant articles only (saves budget)
    candidates = [e for e in enriched if e["tfidf_features"]["is_relevant"]]
    logger.info(f"[AI] {len(candidates)} articles eligible for review (passed TF-IDF filter)")

    if max_articles > 0:
        candidates = candidates[:max_articles]
        logger.info(f"[AI] Limited to {max_articles} articles for this run")

    start_time = time.time()
    results = []
    for i, article in enumerate(candidates):
        # Timeout guard
        elapsed = time.time() - start_time
        if elapsed >= timeout_seconds:
            logger.warning(f"[AI] Timeout reached ({elapsed:.0f}s ≥ {timeout_seconds}s) after {i} reviews — stopping")
            break

        # Budget guard
        runtime = get_ai_runtime_status()
        if runtime.get("budget_exhausted"):
            logger.warning(f"[AI] Budget exhausted after {i} reviews — stopping")
            break

        logger.info(f"[AI] Reviewing {i + 1}/{len(candidates)}: {article['title'][:60]}... (elapsed: {elapsed:.0f}s)")

        try:
            review = generate_review_verdict(
                headline=article["title"],
                full_text=article["text"],
                gs_paper=article["tfidf_features"]["gs_paper"],
                subtopics=article["tfidf_features"]["subtopics"],
            )
        except Exception as e:
            logger.error(f"[AI] Review failed for {article['title'][:60]}: {e}")
            review = None

        training_entry = {
            **article,
            "ai_review": review,
            "review_generated_at": datetime.now(timezone.utc).isoformat(),
        }
        results.append(training_entry)

        # Save incrementally every 10 articles
        if (i + 1) % 10 == 0:
            _save_partial(results, "/tmp/training_data_partial.jsonl")
            logger.info(f"[AI] {i + 1}/{len(candidates)} reviews complete — "
                        f"{sum(1 for r in results if r.get('ai_review'))} succeeded, "
                        f"{sum(1 for r in results if not r.get('ai_review'))} failed")

    # Add remaining enriched articles without review (as unlabeled data)
    reviewed_urls = {r["url"] for r in results}
    for article in enriched:
        if article["url"] not in reviewed_urls:
            results.append({
                **article,
                "ai_review": None,
                "review_generated_at": None,
            })

    elapsed = time.time() - start_time
    logger.info(
        f"[AI] Reviews complete in {elapsed:.0f}s: "
        f"{sum(1 for r in results if r.get('ai_review'))} reviews "
        f"generated, {sum(1 for r in results if not r.get('ai_review'))} unlabeled"
    )
    return results


def save_training_data(results: list[dict], output_path: str) -> Path:
    """Save training data as JSONL (one JSON object per line).

    Also saves a summary CSV for quick analysis.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        for entry in results:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    # Summary stats
    total = len(results)
    relevant = sum(1 for r in results if r["tfidf_features"]["is_relevant"])
    with_review = sum(1 for r in results if r.get("ai_review"))
    passes = sum(1 for r in results if r.get("ai_review") and r["ai_review"]["verdict"] == "PASS")
    flags = sum(1 for r in results if r.get("ai_review") and r["ai_review"]["verdict"] == "FLAG")
    rejects = sum(1 for r in results if r.get("ai_review") and r["ai_review"]["verdict"] == "REJECT")

    logger.info(f"\n{'='*60}")
    logger.info(f"Training data saved to: {output.resolve()}")
    logger.info(f"Total articles: {total}")
    logger.info(f"Passed TF-IDF filter (relevant): {relevant}")
    logger.info(f"With AI review: {with_review}")
    logger.info(f"  PASS: {passes} ({passes/with_review*100:.1f}% of reviewed)" if with_review else "  PASS: 0")
    logger.info(f"  FLAG: {flags} ({flags/with_review*100:.1f}% of reviewed)" if with_review else "  FLAG: 0")
    logger.info(f"  REJECT: {rejects} ({rejects/with_review*100:.1f}% of reviewed)" if with_review else "  REJECT: 0")
    logger.info(f"Unlabeled: {total - with_review}")
    logger.info(f"{'='*60}")

    # Also write a human-readable summary CSV
    summary_path = output.with_suffix(".csv")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("title,source,relevance_score,gs_paper,review_verdict,review_confidence\n")
        for r in results:
            review = r.get("ai_review") or {}
            f.write(
                f"{r['title'][:80].replace(',', ' ')},"
                f"{r['source']},"
                f"{r['tfidf_features']['relevance_score']:.3f},"
                f"{r['tfidf_features']['gs_paper']},"
                f"{review.get('verdict', 'UNLABELED')},"
                f"{review.get('confidence', 'N/A')}\n"
            )

    logger.info(f"Summary CSV saved to: {summary_path.resolve()}")
    return output


def fetch_from_db() -> list[dict]:
    """Pull existing articles from the local/production database."""
    init_db()
    db = SessionLocal()
    try:
        articles = db.query(Article).all()
        logger.info(f"Loaded {len(articles)} articles from DB")
        return [
            {
                "title": a.title,
                "url": a.url,
                "source": a.source,
                "content_snippet": a.content_snippet,
                "published_at": a.published_at,
                "source_type": "news",
                "authority_score": 0.5,
            }
            for a in articles
        ]
    finally:
        db.close()


def fetch_from_db_with_ml() -> list[dict]:
    """Pull saved stories from the Summary table with ML predictions + AI reviews.

    These are stories that went through the pipeline's full processing:
      - TF-IDF relevance scoring
      - AI review verdict (PASS/REJECT)
      - ML prediction (silent, collected alongside AI review)
      - Summary, playbook, etc.

    Each story becomes a training data entry with both ML prediction and AI
    ground truth — perfect for retraining the model on real pipeline data.
    """
    stories = get_upsc_stories(limit=500, min_relevance=0.0)
    logger.info(f"Loaded {len(stories)} stories from DB (with ML + AI data)")

    results = []
    for s in stories:
        # Build TF-IDF-like features from the story's saved UPSC data
        tfidf_features = {
            "relevance_score": s.get("relevance_score", 0.0),
            "gs_paper": s.get("gs_paper", "Unknown"),
            "subtopics": s.get("subtopics", []),
            "confidence": s.get("priority_score", 0.0),
            "matched_criteria_count": 0,
            "is_relevant": (s.get("relevance_score", 0) or 0) >= 0.30,
            "is_irrelevant_content": False,
        }

        ai_review = s.get("ai_review")

        entry = {
            "title": s.get("title", ""),
            "url": s.get("url", ""),
            "source": (s.get("source", "") or "").split(",")[0] if s.get("source") else "",
            "source_type": s.get("source_type", "news"),
            "authority_score": s.get("authority_score", 0.5),
            "text": (s.get("summary", "") or "")[:1000],
            "published_at": s.get("published_at", ""),
            "tfidf_features": tfidf_features,
            "ai_review": ai_review,
            "ml_prediction": s.get("ml_prediction"),
            "review_generated_at": s.get("created_at"),
            "source_db": "pipeline_stories",
        }
        results.append(entry)

    with_ml = sum(1 for r in results if r.get("ml_prediction"))
    with_ai = sum(1 for r in results if r.get("ai_review"))
    logger.info(
        f"DB stories: {len(results)} total, {with_ml} with ML predictions, "
        f"{with_ai} with AI reviews"
    )
    return results


def fetch_user_reviews() -> list[dict]:
    """Pull user reviews from the StoryReview table and format as training data.

    User reviews provide human ground truth on:
      - Whether a story is relevant to UPSC (is_relevant)
      - Whether the sector mapping is correct and what the correct sector should be
      - Whether the GS paper mapping is correct and what the correct paper should be
      - Free-text suggestions for improvement

    These are high-quality training signals because they come from human
    judgment rather than AI — perfect for fine-tuning the ML model.

    Each review becomes a training entry with:
      - tfidf_features inferred from the story (relevance signal)
      - user_review containing the structured feedback
      - source_db: "user_reviews"
    """
    reviews = get_reviews(limit=1000)
    logger.info(f"Loaded {len(reviews)} user reviews from DB")

    results = []
    for r in reviews:
        # Build a simplified training entry from user feedback
        # User reviews don't have TF-IDF features, but we include the
        # feedback as training signal for downstream processing
        is_relevant_raw = r.get("is_relevant", "")
        sector_correct_raw = r.get("sector_correct", "")
        gs_paper_correct_raw = r.get("gs_paper_correct", "")

        # Determine a PASS/REJECT label from the user's relevance feedback
        if is_relevant_raw == "yes":
            user_verdict = "PASS"
        elif is_relevant_raw == "no":
            user_verdict = "REJECT"
        else:
            user_verdict = None  # No clear signal

        entry = {
            "title": r.get("story_title", ""),
            "url": r.get("story_url", ""),
            "source": "user_review",
            "source_type": "user_feedback",
            "authority_score": 1.0,  # Human feedback is gold standard
            "text": r.get("story_title", "")[:1000],
            "published_at": r.get("created_at", ""),
            "tfidf_features": {
                "relevance_score": 0.5,  # Neutral — no TF-IDF available
                "gs_paper": r.get("suggested_gs_paper", "Unknown"),
                "subtopics": [],
                "confidence": 0.0,
                "matched_criteria_count": 0,
                "is_relevant": is_relevant_raw == "yes",
                "is_irrelevant_content": is_relevant_raw == "no",
            },
            "user_review": {
                "verdict": user_verdict,
                "is_relevant": is_relevant_raw,
                "sector_correct": sector_correct_raw,
                "suggested_sector": r.get("suggested_sector"),
                "gs_paper_correct": gs_paper_correct_raw,
                "suggested_gs_paper": r.get("suggested_gs_paper"),
                "suggestions": r.get("suggestions"),
            },
            "ai_review": {
                "verdict": user_verdict,
                "confidence": 1.0,
                "reasoning": "User feedback" if user_verdict else "No clear signal",
            } if user_verdict else None,
            "review_generated_at": r.get("created_at"),
            "source_db": "user_reviews",
        }
        results.append(entry)

    with_verdict = sum(1 for r in results if r.get("ai_review"))
    logger.info(
        f"User reviews formatted: {len(results)} total, "
        f"{with_verdict} with PASS/REJECT signal, "
        f"{sum(1 for r in results if r.get('user_review', {}).get('suggested_sector'))} with sector corrections, "
        f"{sum(1 for r in results if r.get('user_review', {}).get('suggested_gs_paper'))} with GS paper corrections"
    )
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Generate AI review training data from RSS feeds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_training_data.py                          # Full pipeline
  python generate_training_data.py --max-articles 100        # Limit to 100 AI reviews
  python generate_training_data.py --skip-ai                 # TF-IDF only, no API cost
  python generate_training_data.py --output /tmp/train.jsonl # Custom output path
  python generate_training_data.py --no-fetch                # Use existing DB articles
        """,
    )
    parser.add_argument(
        "--max-articles", type=int, default=0,
        help="Maximum articles to run AI reviews on (0 = all eligible)"
    )
    parser.add_argument(
        "--output", type=str, default="training_data.jsonl",
        help="Output JSONL file path (default: training_data.jsonl)"
    )
    parser.add_argument(
        "--skip-ai", action="store_true",
        help="Skip AI review generation — TF-IDF classification only"
    )
    parser.add_argument(
        "--no-fetch", action="store_true",
        help="Skip RSS fetching — use existing articles from database instead"
    )
    parser.add_argument(
        "--from-db", action="store_true",
        help="Load stories from Summary table (includes ML predictions + AI reviews from pipeline)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else "INFO")

    start = time.time()
    logger.info("=== Training Data Generator ===")
    logger.info(f"Args: {vars(args)}")

    # Step 1: Fetch articles
    if args.from_db:
        logger.info("Step 1: Loading stories from Summary table (with ML predictions + AI reviews)...")
        articles = fetch_from_db_with_ml()
    elif args.no_fetch:
        logger.info("Step 1: Loading articles from database...")
        articles = fetch_from_db()
    else:
        logger.info("Step 1: Fetching articles from RSS feeds...")
        articles = fetch_rss_feeds()

    if not articles:
        logger.error("No articles found. Cannot generate training data.")
        sys.exit(1)

    logger.info(f"Fetched {len(articles)} articles")

    # Step 2: Run TF-IDF pipeline
    logger.info("Step 2: Running TF-IDF syllabus classification...")
    enriched = run_tfidf_pipeline(articles)
    relevant = sum(1 for e in enriched if e["tfidf_features"]["is_relevant"])
    logger.info(f"Classification complete: {relevant}/{len(enriched)} articles relevant")

    # Step 3: Generate AI reviews (optional)
    if args.skip_ai:
        logger.info("Step 3: Skipping AI reviews (--skip-ai flag)")
        results = enriched
    else:
        logger.info("Step 3: Generating AI review verdicts...")
        results = run_ai_reviews(enriched, max_articles=args.max_articles)

    # Step 4: Save training data
    logger.info("Step 4: Saving training data...")
    output_path = save_training_data(results, args.output)

    elapsed = time.time() - start
    logger.info(f"=== Complete in {elapsed:.1f}s ===")
    logger.info(f"Output: {output_path.resolve()}")
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Copy training_data.jsonl to your ML training environment")
    logger.info("  2. Train a classifier using TF-IDF features as inputs, AI verdict as label")
    logger.info("  3. Deploy the trained model to replace/parallel the AI review step")
    logger.info("")
    logger.info("Example training command (scikit-learn):")
    logger.info("  python -c \"")
    logger.info("    import json")
    logger.info("    from sklearn.linear_model import LogisticRegression")
    logger.info("    from sklearn.feature_extraction.text import TfidfVectorizer")
    logger.info("    data = [json.loads(l) for l in open('training_data.jsonl')]")
    logger.info("    texts = [d['text'] for d in data if d.get('ai_review')]")
    logger.info("    labels = [d['ai_review']['verdict'] for d in data if d.get('ai_review')]")
    logger.info("    vec = TfidfVectorizer().fit_transform(texts)")
    logger.info("    clf = LogisticRegression().fit(vec, labels)")
    logger.info("    print(f'Trained on {len(texts)} samples')")
    logger.info("  \"")


if __name__ == "__main__":
    main()
