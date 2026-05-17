"""
train_ml_classifier.py — Train ML model on AI review verdict data.

Fetches training data (from prod API or local JSONL), trains a
LogisticRegression classifier on TF-IDF features using AI review
verdicts as labels, and saves the model + vectorizer for inference.

Usage:
  python train_ml_classifier.py                              # Use local training_data.jsonl
  python train_ml_classifier.py --fetch-from-prod            # Download from prod API
  python train_ml_classifier.py --data training_data.jsonl   # Custom file
  python train_ml_classifier.py --output models/ml_model.joblib  # Custom output path
  python train_ml_classifier.py --eval                        # Print detailed metrics
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

# Ensure backend directory is importable
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Default paths
DEFAULT_MODEL_DIR = Path(_BACKEND_DIR) / "ml_models"
DEFAULT_DATA_FILE = Path(_BACKEND_DIR) / "training_data.jsonl"
PROD_API_BASE = "https://upscdailyaffairs.onrender.com"

# ──────────────────────────────────────────────
#  Data Loading
# ──────────────────────────────────────────────


def load_training_data(path: str | Path) -> list[dict]:
    """Load training data from a JSONL file.

    Each line must be a JSON object with:
      - text: str (article text used for TF-IDF features)
      - ai_review: dict | None (must have 'verdict' field: PASS/FLAG/REJECT)
    """
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning(f"Skipping malformed JSON line: {line[:80]}")
    return records


def fetch_from_prod() -> list[dict]:
    """Download training data from the production /train-data/latest endpoint."""
    url = f"{PROD_API_BASE}/train-data/latest"
    logger.info(f"Fetching training data from {url}...")

    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read().decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to fetch from prod: {e}")
        return []

    # Parse JSONL from response body
    records = []
    for line in data.strip().split("\n"):
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    logger.info(f"Fetched {len(records)} records from prod")
    return records


def load_upsc_stories_from_prod() -> list[dict]:
    """Load UPSC stories from prod API as additional training signals.

    Stories with an exam_playbook are implicitly PASS — the AI deemed them
    relevant enough to generate a playbook. This gives us positive labels
    even for stories that didn't get an explicit review verdict.
    """
    url = f"{PROD_API_BASE}/upsc?limit=50"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Failed to fetch stories from prod: {e}")
        return []

    records = []
    for story in data.get("stories", []):
        title = story.get("title", "")
        summary = story.get("summary", story.get("why_it_matters", ""))
        gs_paper = story.get("gs_paper", "Unknown")
        text = f"{title}. {summary}"

        # Use ai_review if available, otherwise infer from exam_playbook
        ai_review = story.get("ai_review")
        exam_playbook = story.get("exam_playbook")

        if ai_review and ai_review.get("verdict"):
            verdict = ai_review["verdict"]
        elif exam_playbook:
            # Has a playbook → implicitly PASS
            verdict = "PASS"
        else:
            # No review, no playbook — might be below threshold
            # Skip unless we want it as unlabeled data
            continue

        records.append({
            "text": text,
            "ai_review": {"verdict": verdict},
            "title": title,
            "gs_paper": gs_paper,
        })

    logger.info(f"Loaded {len(records)} stories from prod (with inferred labels)")
    return records


def prepare_dataset(
    records: list[dict],
    min_samples_per_class: int = 2,
) -> tuple[list[str], list[str], dict[str, int]]:
    """Extract texts and labels from training records.

    Returns:
        (texts, labels, class_counts)
    """
    texts: list[str] = []
    labels: list[str] = []

    for rec in records:
        # Try multiple text fields in order of preference
        text = rec.get("text", "")
        if not text:
            text = f"{rec.get('title', '')} {rec.get('summary', '')}".strip()
        if not text:
            continue

        ai_review = rec.get("ai_review")
        if not ai_review or not isinstance(ai_review, dict):
            continue

        verdict = ai_review.get("verdict", "")
        if verdict not in ("PASS", "FLAG", "REJECT"):
            continue

        texts.append(text[:2000])  # Keep manageable
        labels.append(verdict)

    # Log class distribution
    class_counts: dict[str, int] = {}
    for label in labels:
        class_counts[label] = class_counts.get(label, 0) + 1

    # Warn about rare classes
    for cls, count in class_counts.items():
        if count < min_samples_per_class:
            logger.warning(
                f"Class '{cls}' has only {count} samples "
                f"(min recommended: {min_samples_per_class})"
            )

    logger.info(
        f"Dataset: {len(texts)} samples, "
        f"classes: {class_counts}"
    )

    return texts, labels, class_counts


# ──────────────────────────────────────────────
#  Model Training
# ──────────────────────────────────────────────


def train_model(
    texts: list[str],
    labels: list[str],
    use_pipeline: bool = True,
) -> Pipeline | tuple[Any, Any]:
    """Train a LogisticRegression classifier on TF-IDF features.

    Args:
        texts: List of article text strings
        labels: List of verdict strings (PASS/FLAG/REJECT)
        use_pipeline: If True, return a single Pipeline object

    Returns:
        Pipeline (if use_pipeline=True) or (vectorizer, classifier) tuple
    """
    logger.info(f"Training on {len(texts)} samples...")

    # TF-IDF vectorizer tuned for UPSC content
    vectorizer = TfidfVectorizer(
        max_features=2000,
        stop_words="english",
        sublinear_tf=True,
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.85,
    )

    # LogisticRegression with balanced class weights
    # lbfgs solver handles multinomial automatically in sklearn >= 1.6
    classifier = LogisticRegression(
        solver="lbfgs",
        max_iter=1000,
        class_weight="balanced",
        C=1.0,
        random_state=42,
    )

    if use_pipeline:
        pipeline = Pipeline([
            ("vectorizer", vectorizer),
            ("classifier", classifier),
        ])
        pipeline.fit(texts, labels)

        train_score = pipeline.score(texts, labels)
        logger.info(f"Training accuracy: {train_score:.4f}")
        return pipeline

    X = vectorizer.fit_transform(texts)
    classifier.fit(X, labels)
    train_score = classifier.score(X, labels)
    logger.info(f"Training accuracy: {train_score:.4f}")
    return vectorizer, classifier


def evaluate_model(
    model: Pipeline,
    texts: list[str],
    labels: list[str],
) -> dict[str, Any] | None:
    """Run train/test split evaluation and print metrics.

    Handles small/imbalanced datasets gracefully:
      - If a class has < 2 samples, skips stratified split
      - If total samples < 5, skips eval entirely
    """
    from collections import Counter

    if len(texts) < 5:
        logger.warning(f"Only {len(texts)} samples — skipping evaluation")
        return None

    # Check if stratification is possible (each class needs >= 2 samples)
    class_counts = Counter(labels)
    can_stratify = all(count >= 2 for count in class_counts.values())

    split_kwargs = {"test_size": 0.25, "random_state": 42}
    if can_stratify:
        split_kwargs["stratify"] = labels
    else:
        logger.warning(
            f"Some classes have < 2 samples ({dict(class_counts)}) — "
            "falling back to non-stratified split"
        )

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, **split_kwargs
    )

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    matrix = confusion_matrix(y_test, y_pred).tolist()

    classes = sorted(set(labels))
    logger.info("\n" + "=" * 60)
    logger.info("EVALUATION REPORT (25% test split)")
    logger.info("=" * 60)
    logger.info(f"Train samples: {len(X_train)}, Test samples: {len(X_test)}")
    logger.info(f"\n{classification_report(y_test, y_pred, zero_division=0)}")
    logger.info(f"Confusion matrix:\n{np.array2string(np.array(matrix))}")
    logger.info("=" * 60)

    return {
        "accuracy": report.get("accuracy", 0.0),
        "classification_report": report,
        "confusion_matrix": matrix,
        "classes": classes,
        "test_samples": len(X_test),
    }


# ──────────────────────────────────────────────
#  Save / Load
# ──────────────────────────────────────────────


def save_model(
    pipeline: Pipeline,
    output_path: str | Path,
) -> Path:
    """Save the trained pipeline (vectorizer + classifier) using joblib."""
    try:
        import joblib
    except ImportError:
        logger.error("joblib is required. Install: pip install joblib")
        sys.exit(1)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(pipeline, output)
    logger.info(f"Model saved to: {output.resolve()}")

    # Save a metadata JSON alongside
    metadata_path = output.with_suffix(".json")
    metadata = {
        "model_path": str(output),
        "classes": pipeline.classes_.tolist() if hasattr(pipeline, "classes_") else [],
        "features": (
            pipeline.named_steps["vectorizer"].get_feature_names_out().tolist()[:20]
            if "vectorizer" in pipeline.named_steps
            else []
        ),
    }
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Metadata saved to: {metadata_path.resolve()}")

    return output


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Train ML classifier on AI review verdict data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python train_ml_classifier.py
  python train_ml_classifier.py --fetch-from-prod
  python train_ml_classifier.py --data training_data.jsonl --eval
  python train_ml_classifier.py --output models/ml_model.joblib
  python train_ml_classifier.py --fetch-from-prod --eval --verbose
        """,
    )
    parser.add_argument(
        "--data", type=str,
        help=f"Path to training data JSONL (default: {DEFAULT_DATA_FILE})"
    )
    parser.add_argument(
        "--fetch-from-prod", action="store_true",
        help="Download training data from production /train-data/latest endpoint"
    )
    parser.add_argument(
        "--output", type=str,
        help=f"Output path for trained model (default: {DEFAULT_MODEL_DIR / 'ml_model.joblib'})"
    )
    parser.add_argument(
        "--eval", action="store_true",
        help="Run train/test split evaluation and print metrics"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else "INFO")

    # Step 1: Load training data
    records: list[dict] = []

    if args.fetch_from_prod:
        records = fetch_from_prod()
        # Also supplement with UPSC stories that have inferred labels
        story_records = load_upsc_stories_from_prod()
        existing_urls = {r.get("title", "") for r in records}
        for sr in story_records:
            if sr.get("title", "") not in existing_urls:
                records.append(sr)
        logger.info(f"Total records after supplementing: {len(records)}")
    elif args.data:
        path = Path(args.data)
        if not path.exists():
            logger.error(f"Training data not found: {path}")
            sys.exit(1)
        records = load_training_data(path)
    else:
        # Default: look for local training_data.jsonl
        path = DEFAULT_DATA_FILE
        if path.exists():
            records = load_training_data(path)
        else:
            logger.error(
                f"No training data found at {path}.\n"
                f"  Option 1: Run 'python generate_training_data.py' first\n"
                f"  Option 2: Use --fetch-from-prod to download from production\n"
                f"  Option 3: Specify --data <path_to_jsonl>"
            )
            sys.exit(1)

    if not records:
        logger.error("No training records loaded. Cannot train.")
        sys.exit(1)

    # Step 2: Prepare dataset
    texts, labels, class_counts = prepare_dataset(records)
    if len(texts) < 5:
        logger.error(
            f"Only {len(texts)} labeled samples. Need at least 5 for a meaningful model. "
            "Generate more training data first."
        )
        sys.exit(1)

    # Step 3: Train
    logger.info(f"Training model on {len(texts)} samples...")
    pipeline = train_model(texts, labels)
    logger.info("Training complete.")

    # Step 4: Evaluate (optional)
    if args.eval:
        evaluate_model(pipeline, texts, labels)

    # Step 5: Save model
    output_path = args.output or str(DEFAULT_MODEL_DIR / "ml_model.joblib")
    save_model(pipeline, output_path)

    logger.info("Done!")


if __name__ == "__main__":
    main()
