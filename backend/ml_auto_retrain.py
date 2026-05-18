"""
ml_auto_retrain.py — Continuous ML model improvement system.

Architecture:
  After each pipeline run, new AI reviews are available as ground truth.
  We compare ML predictions vs AI review verdicts → capture as feedback.
  When enough feedback accumulates, auto-retrain with better data.
  After retraining, auto-tune confidence threshold based on performance.
  Reload the model in-place so the scheduler picks it up immediately.

Feedback loop:
  Pipeline runs (6h)                             ← collect feedback data every run
    └─ Phase 0: ML review (free, instant)
    └─ Phase 1: AI review (costs budget) — ground truth
    └─ capture_feedback() — save ML vs AI comparison
  After pipeline:
    └─ check_should_retrain() — has enough data accumulated AND enough time passed?
    └─ auto_retrain() — train new model, tune threshold, reload

Retrain schedule progression:
  - Early (< 100 samples): every 6 hours (every pipeline run)
  - Growth (100–500 samples): every 24 hours (daily)
  - Mature (500+ samples): every 144 hours (every 6 days)

Active learning:
  When ML is confident (PASS ≥ threshold), there's a 5% chance we force
  an AI review anyway to get ground truth. This prevents confirmation bias
  where the model only learns from cases it was uncertain about.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Imports resolved at first retrain to avoid any ordering issues at server startup.
# ml_auto_retrain does NOT import from scheduler or main (no circular risk).
force_reload = None
get_model_info = None
prepare_dataset = None
train_model = None
evaluate_model = None
save_model = None
fetch_from_prod = None
load_upsc_stories_from_prod = None


def _resolve_imports() -> bool:
    """Resolve module-level imports lazily. Called at start of auto_retrain()."""
    global force_reload, get_model_info, prepare_dataset, train_model
    global evaluate_model, save_model, fetch_from_prod, load_upsc_stories_from_prod

    if force_reload is not None:
        return True  # Already resolved

    try:
        from ml_classifier import force_reload as _fr, get_model_info as _gmi
        from train_ml_classifier import (
            prepare_dataset as _pd, train_model as _tm,
            evaluate_model as _em, save_model as _sm,
            fetch_from_prod as _ffp, load_upsc_stories_from_prod as _ls,
        )
        force_reload = _fr
        get_model_info = _gmi
        prepare_dataset = _pd
        train_model = _tm
        evaluate_model = _em
        save_model = _sm
        fetch_from_prod = _ffp
        load_upsc_stories_from_prod = _ls
        return True
    except ImportError as e:
        logger.warning(f"[ML Auto-Retrain] Import resolution failed: {e}")
        return False

# ──────────────────────────────────────────────
#  State
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
#  Config helpers
# ──────────────────────────────────────────────

def _is_scheduled_mode() -> bool:
    """Check if ML_RETRAIN_MODE is set to 'scheduled' in config."""
    try:
        from config import ML_RETRAIN_MODE
        return ML_RETRAIN_MODE == "scheduled"
    except (ImportError, AttributeError):
        return False  # Safe default: continuous mode


_RETRAIN_STATE: dict[str, Any] = {
    "last_retrain_at": None,            # ISO timestamp
    "total_retrains": 0,
    "new_samples_since_last_retrain": 0,
    "confidence_threshold": 0.70,       # Dynamic — auto-tuned
    "accuracy": None,                   # Last evaluated accuracy
    "is_retraining": False,             # Guard against concurrent retrains
    "total_feedback_captured": 0,
    "total_mismatches": 0,              # ML verdict ≠ AI verdict
}

# Buffer of ML/AI comparison data for next retrain
_FEEDBACK_BUFFER: list[dict] = []


# ──────────────────────────────────────────────
#  Feedback Capture
# ──────────────────────────────────────────────

def capture_feedback(
    story_title: str,
    ml_verdict: str | None,
    ai_verdict: str | None,
    ml_confidence: float,
    text: str,
    gs_paper: str = "",
    subtopics: list | None = None,
) -> None:
    """Save ML vs AI comparison as training data for next retrain.

    Called from scheduler after each story gets an AI review.
    When ML and AI disagree, that's the most valuable training signal.
    Even when they agree, the confidence tells us about model calibration.

    Args:
        story_title: Story headline
        ml_verdict: ML classifier verdict (PASS/FLAG/REJECT or None)
        ai_verdict: AI review verdict (PASS/FLAG/REJECT)
        ml_confidence: ML confidence in its verdict (0.0–1.0)
        text: Article text (for TF-IDF features)
        gs_paper: GS paper mapping
        subtopics: Syllabus subtopics
    """
    global _RETRAIN_STATE, _FEEDBACK_BUFFER

    if not ai_verdict or not text:
        return

    entry = {
        "title": story_title,
        "text": text[:2000],
        "gs_paper": gs_paper,
        "subtopics": subtopics or [],
        "ai_review": {"verdict": ai_verdict},
        "ml_result": {
            "verdict": ml_verdict,
            "confidence": ml_confidence,
        },
        "ml_matched_ai": ml_verdict == ai_verdict,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    _FEEDBACK_BUFFER.append(entry)
    _RETRAIN_STATE["total_feedback_captured"] += 1

    if ml_verdict and ml_verdict != ai_verdict:
        _RETRAIN_STATE["total_mismatches"] += 1
        logger.debug(
            f"[ML Feedback] ML={ml_verdict} (conf={ml_confidence:.2f}) vs "
            f"AI={ai_verdict} — '{story_title[:50]}' "
            f"→ saved as training signal"
        )


# ──────────────────────────────────────────────
#  Retrain Decision
# ──────────────────────────────────────────────

def _compute_retrain_interval() -> float:
    """Compute optimal retrain interval based on model maturity and mode.

    Collection (feedback capture) happens every pipeline run — always.
    Retraining (compute-heavy) happens on this schedule:

    Mode="continuous" (default):
      - < 100 samples: every 6 hours (every pipeline run — fast iteration)
      - 100–500 samples: every 24 hours (daily)
      - 500+ samples: every 144 hours (every 6 days)

    Mode="scheduled":
      - Fixed 144 hours (6 days) regardless of sample count
      - check_should_retrain() also requires 72h (3 days) of collection
        between retrains — see 'MIN_FEEDBACK_HOURS' there
    """
    if _is_scheduled_mode():
        return 144.0  # Fixed 6-day retrain cycle

    total_samples = _RETRAIN_STATE["new_samples_since_last_retrain"]
    if total_samples < 100:
        return 6.0    # Every pipeline run — fast iteration while data is scarce
    elif total_samples < 500:
        return 24.0   # Daily — diminishing returns from more frequent retrains
    else:
        return 144.0  # Every 6 days — model is mature, only retrain on meaningful data shifts


def check_should_retrain(
    min_new_samples: int | None = None,
    min_interval_hours: float | None = None,
) -> bool:
    """Check if conditions are met for auto-retraining.

    Args:
        min_new_samples: Minimum new labeled samples needed (auto if None)
        min_interval_hours: Minimum hours since last retrain (auto if None)

    Returns:
        True if retraining should proceed
    """
    if _RETRAIN_STATE["is_retraining"]:
        logger.debug("[ML Auto-Retrain] Already retraining — skipping")
        return False

    # "scheduled" mode enforces a fixed 3d/6d rhythm
    _scheduled_mode = _is_scheduled_mode()

    # Auto-compute interval based on model maturity (or fixed in scheduled mode)
    if min_interval_hours is None:
        min_interval_hours = _compute_retrain_interval()

    if _RETRAIN_STATE["last_retrain_at"]:
        last = datetime.fromisoformat(_RETRAIN_STATE["last_retrain_at"])
        elapsed = datetime.now(timezone.utc) - last
        hours_since = elapsed.total_seconds() / 3600
        if hours_since < min_interval_hours:
            logger.debug(
                f"[ML Auto-Retrain] Only {hours_since:.1f}h since last retrain "
                f"(need {min_interval_hours}h) — skipping"
            )
            return False

    # Count available new data: feedback buffer + fresh prod data
    new_data = len(_FEEDBACK_BUFFER)

    # Also check fresh training data on prod
    try:
        prod_data = fetch_from_prod() if fetch_from_prod else []
        fresh_count = sum(1 for r in prod_data if r.get("ai_review"))
        # Subtract previously counted samples (approximate)
        repeat_count = _RETRAIN_STATE["total_retrains"] * 25
        new_data = max(new_data, fresh_count - repeat_count)
    except Exception:
        pass

    # In scheduled mode, also enforce a minimum 3-day (72h) collection window
    if _scheduled_mode and _RETRAIN_STATE["last_retrain_at"]:
        last = datetime.fromisoformat(_RETRAIN_STATE["last_retrain_at"])
        elapsed = datetime.now(timezone.utc) - last
        hours_since = elapsed.total_seconds() / 3600
        if hours_since < 72.0:
            logger.debug(
                f"[ML Auto-Retrain] Scheduled mode: only {hours_since:.1f}h since "
                f"last retrain (need 72h) — collecting more feedback"
            )
            return False

    if min_new_samples is None:
        # Scale min_new_samples with model maturity
        total = _RETRAIN_STATE["new_samples_since_last_retrain"]
        if _scheduled_mode:
            min_new_samples = 30  # Fixed minimum for 3d/6d schedule
        else:
            min_new_samples = 5 if total < 100 else 15 if total < 500 else 30

    if new_data >= min_new_samples:
        logger.info(
            f"[ML Auto-Retrain] {new_data} new samples available "
            f"(need {min_new_samples}) — retraining triggered"
        )
        return True

    logger.debug(
        f"[ML Auto-Retrain] {new_data} new samples available "
        f"(need {min_new_samples}) — not enough yet"
    )
    return False


# ──────────────────────────────────────────────
#  Threshold Auto-Tuning
# ──────────────────────────────────────────────

def auto_tune_threshold(
    pipeline,
    texts: list[str],
    labels: list[str],
    target_accuracy: float = 0.85,
) -> float:
    """Auto-tune the ML confidence threshold based on model performance.

    Strategy:
      Evaluate the model on held-out data and find the confidence level
      where accuracy reaches the target. Then set the threshold there.

      - High accuracy at low confidence → lower threshold (bypass more AI calls)
      - Low accuracy → raise threshold (be more conservative)

    Args:
        pipeline: Trained sklearn Pipeline
        texts: Full list of training texts
        labels: Full list of training labels
        target_accuracy: Minimum accuracy to accept (default 0.85)

    Returns:
        Optimal confidence threshold (0.50–0.95)
    """
    if len(texts) < 10:
        return _RETRAIN_STATE["confidence_threshold"]

    try:
        from sklearn.model_selection import train_test_split

        # Use train/test split
        can_stratify = all(labels.count(c) >= 2 for c in set(labels))
        split_kwargs = {"test_size": 0.3, "random_state": 42}
        if can_stratify:
            split_kwargs["stratify"] = labels
        X_train, X_test, y_train, y_test = train_test_split(
            texts, labels, **split_kwargs
        )

        pipeline.fit(X_train, y_train)

        # Get probabilities for test set
        proba = pipeline.predict_proba(X_test)
        classes = pipeline.classes_

        # For each test sample, extract confidence and correctness
        confidences = []
        correct = []
        for i, true_label in enumerate(y_test):
            pred_idx = list(classes).index(true_label) if true_label in classes else 0
            pred = classes[int(np.argmax(proba[i]))]
            conf = float(np.max(proba[i]))
            confidences.append(conf)
            correct.append(pred == true_label)

        # Sort by confidence
        pairs = sorted(zip(confidences, correct), key=lambda x: x[0])

        # Find threshold where accuracy >= target
        for threshold in [0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50]:
            above = [(c, r) for c, r in pairs if c >= threshold]
            if not above:
                continue
            acc = sum(1 for _, r in above if r) / len(above)
            if acc >= target_accuracy:
                logger.info(
                    f"[ML Auto-Tune] Threshold={threshold:.2f} gives "
                    f"accuracy={acc:.3f} on {len(above)} samples "
                    f"(target={target_accuracy})"
                )
                return threshold

        # Fallback: use median confidence of correct predictions
        correct_confs = [c for c, r in pairs if r]
        if correct_confs:
            fallback = float(np.median(correct_confs))
            logger.info(
                f"[ML Auto-Tune] No threshold hit target={target_accuracy}, "
                f"using median confidence of correct predictions: {fallback:.2f}"
            )
            return max(0.50, min(0.95, fallback))

    except Exception as e:
        logger.warning(f"[ML Auto-Tune] Failed: {e}")

    return 0.70  # Safe default


# ──────────────────────────────────────────────
#  Auto-Retrain
# ──────────────────────────────────────────────

def auto_retrain(
    output_dir: str | Path | None = None,
    tune_threshold: bool = True,
) -> dict[str, Any]:
    """Run the full auto-retrain cycle.

    Steps:
      1. Resolve imports (lazy, one-time)
      2. Fetch new training data from prod API
      3. Supplement with feedback buffer (ML/AI mismatches)
      4. Supplement with UPSC stories (playbook = implicit PASS)
      5. Prepare dataset (filter to PASS/FLAG/REJECT, check minimums)
      6. Train LogisticRegression on TF-IDF features
      7. Evaluate and auto-tune confidence threshold
      8. Save model + metadata
      9. Force-reload into inference module (zero-downtime)
      10. Update retrain state

    Always resets is_retraining = False via finally.

    Returns:
        Dict with retrain results
    """
    global _RETRAIN_STATE, _FEEDBACK_BUFFER

    if _RETRAIN_STATE["is_retraining"]:
        return {"success": False, "reason": "Already retraining in progress"}

    # Resolve imports lazily (one-time, survives server lifetime)
    if not _resolve_imports():
        return {"success": False, "reason": "Import resolution failed"}

    _RETRAIN_STATE["is_retraining"] = True
    start = time.time()

    try:
        # 1. Fetch training data from prod
        records = fetch_from_prod()
        logger.info(f"[ML Auto-Retrain] Fetched {len(records)} records from prod")

        # 2. Supplement with UPSC stories (playbook → implicit PASS)
        story_records = load_upsc_stories_from_prod()
        existing_titles = {r.get("title", "") for r in records}
        for sr in story_records:
            if sr.get("title", "") not in existing_titles:
                records.append(sr)

        # 3. Add feedback buffer
        fb_count = len(_FEEDBACK_BUFFER)
        if fb_count > 0:
            records.extend(_FEEDBACK_BUFFER)
            _FEEDBACK_BUFFER.clear()
            logger.info(f"[ML Auto-Retrain] Added {fb_count} feedback samples")

        # 4. Prepare dataset (binary by default — FLAG collapsed → PASS)
        texts, labels, class_counts = prepare_dataset(records, binary=True)

        if len(texts) < 10:
            logger.warning(
                f"[ML Auto-Retrain] Only {len(texts)} labeled samples "
                f"(need 10+) — skipping retrain"
            )
            return {
                "success": False,
                "reason": f"Only {len(texts)} samples, need 10+",
                "samples": len(texts),
                "class_counts": class_counts,
            }

        # 5. Train
        logger.info(
            f"[ML Auto-Retrain] Training on {len(texts)} samples "
            f"(classes: {class_counts})..."
        )
        pipeline = train_model(texts, labels)

        # 6. Evaluate
        try:
            eval_result = evaluate_model(pipeline, texts, labels)
            accuracy = eval_result.get("accuracy", 0.0) if eval_result else 0.0
            _RETRAIN_STATE["accuracy"] = accuracy
            logger.info(f"[ML Auto-Retrain] Evaluation accuracy: {accuracy:.4f}")
        except Exception as e:
            logger.warning(f"[ML Auto-Retrain] Evaluation failed: {e}")
            accuracy = 0.0

        # 7. Auto-tune threshold
        if tune_threshold:
            new_threshold = auto_tune_threshold(pipeline, texts, labels)
            # Also update the runtime classifier threshold
            _RETRAIN_STATE["confidence_threshold"] = new_threshold
            try:
                from ml_classifier import set_confidence_threshold
                set_confidence_threshold(new_threshold)
            except Exception:
                pass
            logger.info(
                f"[ML Auto-Retrain] Confidence threshold tuned to: {new_threshold:.2f}"
            )

        # 8. Save model
        output_path = Path(output_dir or _BACKEND_DIR) / "ml_models" / "ml_model.joblib"
        save_model(pipeline, output_path)

        # 9. Force-reload into inference
        loaded = force_reload(output_path)
        logger.info(
            f"[ML Auto-Retrain] Model reloaded: {'yes' if loaded else 'no'}"
        )

        # 10. Update state
        _RETRAIN_STATE["last_retrain_at"] = datetime.now(timezone.utc).isoformat()
        _RETRAIN_STATE["total_retrains"] += 1
        _RETRAIN_STATE["new_samples_since_last_retrain"] = len(texts)

        elapsed = time.time() - start
        logger.info(
            f"[ML Auto-Retrain] Complete in {elapsed:.1f}s: "
            f"{len(texts)} samples, accuracy={accuracy:.4f}, "
            f"threshold={_RETRAIN_STATE['confidence_threshold']:.2f}"
        )

        return {
            "success": True,
            "samples": len(texts),
            "class_counts": class_counts,
            "accuracy": accuracy,
            "threshold": _RETRAIN_STATE["confidence_threshold"],
            "elapsed_seconds": round(elapsed, 1),
            "total_retrains": _RETRAIN_STATE["total_retrains"],
            "feedback_consumed": fb_count,
            "model_reloaded": loaded,
        }

    except Exception as e:
        logger.exception(f"[ML Auto-Retrain] Failed: {e}")
        return {"success": False, "reason": str(e)}
    finally:
        _RETRAIN_STATE["is_retraining"] = False


# ──────────────────────────────────────────────
#  Diagnostics
# ──────────────────────────────────────────────

def get_retrain_state() -> dict[str, Any]:
    """Return current retrain state + model info for diagnostics."""
    info = dict(_RETRAIN_STATE)
    info["feedback_buffer_size"] = len(_FEEDBACK_BUFFER)
    info["recommended_interval_hours"] = _compute_retrain_interval()
    try:
        info["model_info"] = get_model_info() if get_model_info else None
    except Exception:
        info["model_info"] = None
    return info


def get_feedback_buffer() -> list[dict]:
    """Return the current feedback buffer (for debugging)."""
    return list(_FEEDBACK_BUFFER)


def clear_feedback_buffer() -> None:
    """Clear the feedback buffer (e.g., after manual retrain)."""
    global _FEEDBACK_BUFFER
    _FEEDBACK_BUFFER = []
    logger.info("[ML Auto-Retrain] Feedback buffer cleared")
