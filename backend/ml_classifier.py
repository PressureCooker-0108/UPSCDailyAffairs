"""
ml_classifier.py — ML-based UPSC review classifier (inference).

Loads a trained LogisticRegression pipeline (vectorizer + classifier)
and provides a single public function:

    ml_review_verdict(text, title="") -> dict | None

Returns a verdict dict with:
  - verdict: "PASS" | "FLAG" | "REJECT"
  - confidence: float (probability of predicted class, 0.0–1.0)
  - probabilities: dict {class: probability}
  - ml_score: float (numeric mapping: PASS=1.0, FLAG=0.5, REJECT=0.0)
  - model_loaded: bool

When no model is loaded (missing file, first call), returns None gracefully.
This allows the scheduler to fall back to AI review without crashing.

The model file is lazy-loaded on first call and then cached.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger

# Ensure backend directory is importable
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Default model path (relative to backend/)
DEFAULT_MODEL_PATH = Path(_BACKEND_DIR) / "ml_models" / "ml_model.joblib"

# Lazy-loaded model cache
_model_pipeline: Any = None
_model_path_attempted: str | None = None

# Dynamic confidence threshold — can be updated at runtime by auto_retrain
# Controls how confident the ML model must be to emit a verdict vs "FLAG" (unsure)
_CONFIDENCE_THRESHOLD: float = 0.60


def _load_model(model_path: str | Path | None = None) -> Any:
    """Load the trained pipeline from disk.

    Uses lazy loading — only loads on first call, then caches.
    Thread-safe enough for read-only inference (no writes to shared state).

    Returns the pipeline object or None if loading fails.
    """
    global _model_pipeline, _model_path_attempted

    if _model_pipeline is not None:
        return _model_pipeline

    path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
    _model_path_attempted = str(path)

    if not path.exists():
        logger.warning(f"[ML Classifier] Model not found at {path}")
        return None

    try:
        import joblib
        _model_pipeline = joblib.load(path)
        logger.info(f"[ML Classifier] Model loaded from {path}")

        # Log model metadata
        if hasattr(_model_pipeline, "classes_"):
            logger.info(
                f"[ML Classifier] Classes: {_model_pipeline.classes_.tolist()}, "
                f"type: {type(_model_pipeline).__name__}"
            )

        # Try loading metadata JSON for extra info
        metadata_path = path.with_suffix(".json")
        if metadata_path.exists():
            try:
                with open(metadata_path) as f:
                    metadata = json.load(f)
                logger.info(f"[ML Classifier] Metadata: {metadata.get('classes')}")
            except Exception:
                pass

        return _model_pipeline

    except Exception as e:
        logger.error(f"[ML Classifier] Failed to load model from {path}: {e}")
        return None


def _build_class_text(text: str, title: str = "") -> str:
    """Build the text representation for ML classification.

    Matches the training data format where text = title + snippet.
    """
    text = (text or "").strip()
    title = (title or "").strip()

    if title and text:
        return f"{title}. {text}"
    return title or text


def _verdict_from_probabilities(probs: dict[str, float]) -> tuple[str, float, dict[str, float]]:
    """Convert model probabilities to a verdict with confidence.

    Uses a dynamic confidence threshold (_CONFIDENCE_THRESHOLD module var):
      - If top class probability >= threshold → return that class
      - Otherwise → return "FLAG" (unsure)

    The threshold can be updated at runtime via set_confidence_threshold().
    This is auto-tuned by the ml_auto_retrain system based on model accuracy.

    Args:
        probs: Dict mapping class labels to probabilities (must sum to 1.0)

    Returns:
        (verdict, confidence, probabilities)
    """
    if not probs:
        return "FLAG", 0.0, {}

    # Normalize (should already be normalized from predict_proba)
    total = sum(probs.values())
    if total > 0 and total != 1.0:
        probs = {k: v / total for k, v in probs.items()}

    best_class = max(probs, key=probs.get)
    best_prob = probs[best_class]

    # Low confidence → return FLAG (let AI review decide)
    if best_prob < _CONFIDENCE_THRESHOLD:
        return "FLAG", best_prob, probs

    return best_class, best_prob, probs


def ml_review_verdict(
    text: str,
    title: str = "",
    model_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Run ML-based review on article text.

    This is the MAIN public API. Call it from the scheduler pipeline.

    Args:
        text: Article text (snippet, summary, or full text)
        title: Article headline (optional, appended to text)
        model_path: Custom model path (optional, uses default if None)

    Returns:
        Dict with verdict + confidence, or None if model isn't loaded.

    Example return:
        {
            "verdict": "PASS",
            "confidence": 0.87,
            "probabilities": {"PASS": 0.87, "FLAG": 0.10, "REJECT": 0.03},
            "ml_score": 1.0,
            "model_loaded": True,
        }
    """
    pipeline = _load_model(model_path)
    if pipeline is None:
        return None

    class_text = _build_class_text(text, title)
    if not class_text.strip():
        logger.warning("[ML Classifier] Empty text — cannot classify")
        return None

    try:
        # predict_proba returns array of shape (n_samples, n_classes)
        proba_array = pipeline.predict_proba([class_text])[0]
        classes = pipeline.classes_

        # Build probabilities dict
        probabilities: dict[str, float] = {}
        for i, cls in enumerate(classes):
            probabilities[str(cls)] = round(float(proba_array[i]), 4)

        # Determine verdict with confidence threshold
        verdict, confidence, _ = _verdict_from_probabilities(probabilities)

        # Numeric score for ordering/filtering
        ml_score_map = {"PASS": 1.0, "FLAG": 0.5, "REJECT": 0.0}
        ml_score = ml_score_map.get(verdict, 0.0)

        result = {
            "verdict": verdict,
            "confidence": round(confidence, 4),
            "probabilities": probabilities,
            "ml_score": ml_score,
            "model_loaded": True,
        }

        logger.debug(
            f"[ML Classifier] {verdict} (conf={confidence:.3f}) "
            f"for: {title[:60] if title else class_text[:60]}..."
        )
        return result

    except Exception as e:
        logger.error(f"[ML Classifier] Prediction failed: {e}")
        return None


def is_model_loaded() -> bool:
    """Check if the ML model is loaded and ready.

    Triggers a lazy load if not yet attempted.
    """
    return _load_model() is not None


def force_reload(model_path: str | Path | None = None) -> bool:
    """Force reload the model from disk.

    Useful after retraining — call this to pick up the new model
    without restarting the server.

    Returns True if the model loaded successfully.
    """
    global _model_pipeline, _model_path_attempted
    _model_pipeline = None
    _model_path_attempted = None
    return _load_model(model_path) is not None


def get_confidence_threshold() -> float:
    """Get the current dynamic confidence threshold."""
    return _CONFIDENCE_THRESHOLD


def set_confidence_threshold(threshold: float) -> None:
    """Update the confidence threshold at runtime.

    Called by ml_auto_retrain.auto_retrain() after threshold auto-tuning.
    Affects all subsequent ml_review_verdict() calls immediately.

    Args:
        threshold: New threshold value (0.0–1.0). Clamped to [0.50, 0.95].
    """
    global _CONFIDENCE_THRESHOLD
    threshold = max(0.50, min(0.95, threshold))
    old = _CONFIDENCE_THRESHOLD
    _CONFIDENCE_THRESHOLD = threshold
    logger.info(
        f"[ML Classifier] Confidence threshold: {old:.2f} → {threshold:.2f}"
    )


def get_model_info() -> dict[str, Any]:
    """Return diagnostic info about the loaded model."""
    pipeline = _load_model()
    if pipeline is None:
        return {
            "loaded": False,
            "path_attempted": str(_model_path_attempted) if _model_path_attempted else str(DEFAULT_MODEL_PATH),
            "confidence_threshold": _CONFIDENCE_THRESHOLD,
        }

    info: dict[str, Any] = {
        "loaded": True,
        "path": str(DEFAULT_MODEL_PATH),
        "type": type(pipeline).__name__,
        "confidence_threshold": _CONFIDENCE_THRESHOLD,
    }

    if hasattr(pipeline, "classes_"):
        info["classes"] = pipeline.classes_.tolist()
    if hasattr(pipeline, "named_steps"):
        info["steps"] = list(pipeline.named_steps.keys())
        vec = pipeline.named_steps.get("vectorizer")
        if vec and hasattr(vec, "get_feature_names_out"):
            info["feature_count"] = len(vec.get_feature_names_out())

    return info
