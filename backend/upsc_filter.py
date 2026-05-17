"""
upsc_filter.py — Syllabus-Aware ML Filtering Engine

PRIMARY intelligence layer for the UPSC Current Affairs Platform.
ALL heavy filtering happens here, BEFORE Gemini is ever called.

Uses ONLY:
  - scikit-learn (TfidfVectorizer, cosine_similarity)
  - numpy
  - standard Python libraries

NO:
  - transformers, torch, sentence-transformers
  - heavy embeddings or vector databases

Responsibilities:
  - syllabus-aware classification (maps articles to Prelims / GS1–GS4 topics)
  - UPSC relevance scoring (TF-IDF + cosine similarity against syllabus nodes)
  - GS paper mapping & subtopic extraction
  - novelty scoring (against previously seen stories)
  - cluster prioritization & API budget optimization
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  Syllabus Loading & Index Building
# ──────────────────────────────────────────────

_SYLLABUS_PATH = Path(__file__).parent / "upsc_syllabus.json"

# Flattened syllabus index: list of dicts with topic metadata
_syllabus_topics: list[dict[str, Any]] = []
# TF-IDF vectorizer + vectors for syllabus topics (built at module load)
_syllabus_vectorizer: TfidfVectorizer | None = None
_syllabus_vectors: np.ndarray | None = None
_syllabus_topic_texts: list[str] = []

# UPSC high-current-affairs topics for priority boosting
_high_ca_topics: list[str] = []

# News relevance scoring criteria
_relevance_criteria: list[str] = []

# Keywords that indicate NON-relevant content (celebrity, entertainment, sports, gossip)
_IRRELEVANT_PATTERNS = re.compile(
    r"\b(celebrity|entertainment|gossip|movie|film|actor|actress|"
    r"singer|music album|reality show|bollywood|tollywood|"
    r"hollywood|fashion show|beauty pageant|sports league|"
    r"football match|cricket match|ipl|premier league|"
    r"match score|tournament final|championship game|"
    r"game highlights|player transfer|trade rumor)\b",
    re.IGNORECASE,
)


def load_syllabus(path: str | Path | None = None) -> dict:
    """Load the UPSC syllabus JSON file."""
    path = path or _SYLLABUS_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"UPSC syllabus not found at {path}. Using empty syllabus.")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid UPSC syllabus JSON: {e}")
        return {}


def _flatten_prelims(syllabus: dict) -> list[dict[str, Any]]:
    """Flatten Prelims GS Paper 1 topics into syllabus index entries."""
    topics = []
    prelims = syllabus.get("stages", {}).get("prelims", {}).get("papers", {}).get("GS_Paper1", {}).get("topics", {})
    for topic_name, subtopics in prelims.items():
        if isinstance(subtopics, list):
            text = f"{topic_name}: {'; '.join(subtopics)}"
            topics.append({
                "gs_paper": "Prelims",
                "topic": topic_name.replace("_", " "),
                "subtopic": "",
                "text": text,
                "weightage": "medium",
            })
        elif isinstance(subtopics, dict):
            for sub_name, sub_items in subtopics.items():
                if isinstance(sub_items, list):
                    text = f"{topic_name} - {sub_name}: {'; '.join(sub_items)}"
                else:
                    text = f"{topic_name} - {sub_name}: {sub_items}"
                topics.append({
                    "gs_paper": "Prelims",
                    "topic": topic_name.replace("_", " "),
                    "subtopic": sub_name.replace("_", " "),
                    "text": text,
                    "weightage": "medium",
                })
    return topics


def _flatten_mains(syllabus: dict) -> list[dict[str, Any]]:
    """Flatten Mains GS1–GS4 papers into syllabus index entries."""
    topics = []
    mains = syllabus.get("stages", {}).get("mains", {}).get("papers", {})
    gs_papers = {
        "GS1": "Indian Heritage and Culture, History and Geography of the World and Society",
        "GS2": "Governance, Constitution, Polity, Social Justice and International Relations",
        "GS3": "Technology, Economic Development, Bio-diversity, Environment, Security and Disaster Management",
        "GS4": "Ethics, Integrity and Aptitude",
    }

    for gs_key in ["GS1", "GS2", "GS3", "GS4"]:
        paper = mains.get(gs_key, {})
        paper_topics = paper.get("topics", {})
        for topic_name, topic_data in paper_topics.items():
            weightage = topic_data.get("weightage", "medium") if isinstance(topic_data, dict) else "medium"
            subtopics = topic_data.get("subtopics", []) if isinstance(topic_data, dict) else []

            if isinstance(subtopics, list):
                text = f"{topic_name.replace('_', ' ')}: {'; '.join(subtopics) if subtopics else topic_name.replace('_', ' ')}"
                topics.append({
                    "gs_paper": gs_key,
                    "topic": topic_name.replace("_", " "),
                    "subtopic": "",
                    "text": text,
                    "weightage": weightage,
                })
            elif isinstance(subtopics, dict):
                for sub_name, sub_items in subtopics.items():
                    items_text = "; ".join(sub_items) if isinstance(sub_items, list) else str(sub_items)
                    text = f"{topic_name.replace('_', ' ')} - {sub_name.replace('_', ' ')}: {items_text}"
                    topics.append({
                        "gs_paper": gs_key,
                        "topic": topic_name.replace("_", " "),
                        "subtopic": sub_name.replace("_", " "),
                        "text": text,
                        "weightage": weightage,
                    })

    return topics


def _extract_ca_topics_and_criteria(syllabus: dict) -> None:
    """Extract high-current-affairs topics and relevance criteria from syllabus."""
    global _high_ca_topics, _relevance_criteria

    ca_data = syllabus.get("high_current_affairs_topics", {})
    if isinstance(ca_data, dict):
        _high_ca_topics = ca_data.get("topics", [])
    elif isinstance(ca_data, list):
        _high_ca_topics = ca_data

    scoring = syllabus.get("news_relevance_scoring", {})
    if isinstance(scoring, dict):
        _relevance_criteria = scoring.get("criteria", [])
    elif isinstance(scoring, list):
        _relevance_criteria = scoring


def build_syllabus_index() -> list[dict[str, Any]]:
    """Build the full flattened syllabus topic index from the syllabus JSON.

    Returns a list of dicts with keys: gs_paper, topic, subtopic, text, weightage.
    """
    syllabus = load_syllabus()
    if not syllabus:
        logger.warning("Empty syllabus — syllabus index will be empty")
        return []

    _extract_ca_topics_and_criteria(syllabus)

    topics = []
    topics.extend(_flatten_prelims(syllabus))
    topics.extend(_flatten_mains(syllabus))

    logger.info(f"Built syllabus index with {len(topics)} topic entries "
                f"(Prelims + GS1–GS4), {len(_high_ca_topics)} CA topics, "
                f"{len(_relevance_criteria)} relevance criteria")
    return topics


def _init_syllabus_vectors() -> None:
    """Initialize or re-initialize the TF-IDF vectorizer + vectors for syllabus topics.
    Called once at module load and can be called again to refresh.
    """
    global _syllabus_topics, _syllabus_vectorizer, _syllabus_vectors, _syllabus_topic_texts

    _syllabus_topics = build_syllabus_index()
    if not _syllabus_topics:
        _syllabus_vectors = None
        _syllabus_vectorizer = None
        _syllabus_topic_texts = []
        logger.warning("No syllabus topics to vectorize")
        return

    _syllabus_topic_texts = [t["text"] for t in _syllabus_topics]

    _syllabus_vectorizer = TfidfVectorizer(
        max_features=1000,
        stop_words="english",
        sublinear_tf=True,
        ngram_range=(1, 2),
    )
    _syllabus_vectors = _syllabus_vectorizer.fit_transform(_syllabus_topic_texts).toarray()

    # Normalize
    norms = np.linalg.norm(_syllabus_vectors, axis=1, keepdims=True) + 1e-9
    _syllabus_vectors = _syllabus_vectors / norms

    logger.info(f"Initialized syllabus TF-IDF vectors: {_syllabus_vectors.shape[0]} topics, "
                f"{_syllabus_vectors.shape[1]} features")


# Initialize at module load
_init_syllabus_vectors()


# ──────────────────────────────────────────────
#  Classification: Map Article → Syllabus
# ──────────────────────────────────────────────

def _build_article_text(article: dict) -> str:
    """Build a combined text representation from an article for classification."""
    title = article.get("title", "")
    snippet = article.get("content_snippet", "")[:300]
    return f"{title}. {snippet}" if snippet else title


def _build_cluster_text(cluster: list[dict]) -> str:
    """Build a combined text representation from a cluster of articles."""
    parts = []
    for a in cluster[:5]:
        title = a.get("title", "")
        snippet = a.get("content_snippet", "")[:200]
        parts.append(f"{title}. {snippet}" if snippet else title)
    return " ".join(parts)


def classify_article(text: str) -> dict[str, Any]:
    """Classify a text against the UPSC syllabus.

    Returns:
      Classification dict with:
        - gs_paper: str (best matching GS paper)
        - subtopics: list[str] (best matching subtopics)
        - topic: str (best matching syllabus topic)
        - confidence: float (cosine similarity score)
        - all_scores: list[dict] (all topic scores for debugging)
    """
    if _syllabus_vectorizer is None or _syllabus_vectors is None:
        return {
            "gs_paper": "Unknown",
            "subtopics": [],
            "topic": "",
            "confidence": 0.0,
            "all_scores": [],
        }

    try:
        # Vectorize input text
        text_vec = _syllabus_vectorizer.transform([text]).toarray()[0]
        text_norm = np.linalg.norm(text_vec) + 1e-9
        text_vec = text_vec / text_norm

        # Compute similarity against all syllabus topics
        sims = _syllabus_vectors @ text_vec

        # Get top matches
        top_n = min(5, len(sims))
        top_indices = np.argsort(-sims)[:top_n]

        all_scores = []
        matched_gs = {}
        matched_subtopics = []
        best_topic = ""
        best_confidence = 0.0

        for idx in top_indices:
            score = float(sims[idx])
            topic_entry = _syllabus_topics[idx]
            gs_paper = topic_entry["gs_paper"]
            subtopic = topic_entry["subtopic"]
            topic_name = topic_entry["topic"]

            all_scores.append({
                "gs_paper": gs_paper,
                "topic": topic_name,
                "subtopic": subtopic,
                "score": round(score, 4),
            })

            # Track best match
            if score > best_confidence:
                best_confidence = score
                best_topic = topic_name

            # Aggregate GS paper scores (take max per paper)
            if gs_paper not in matched_gs or score > matched_gs[gs_paper]:
                matched_gs[gs_paper] = score

            # Collect unique subtopics with reasonable scores
            if subtopic and score > 0.15:
                matched_subtopics.append(subtopic)

        # Determine best GS paper
        best_gs = max(matched_gs, key=matched_gs.get) if matched_gs else "Unknown"

        # Deduplicate subtopics
        matched_subtopics = list(dict.fromkeys(matched_subtopics))

        return {
            "gs_paper": best_gs,
            "subtopics": matched_subtopics[:5],
            "topic": best_topic,
            "confidence": round(best_confidence, 4),
            "all_scores": all_scores,
        }
    except Exception as e:
        logger.error(f"Classification failed: {e}")
        return {
            "gs_paper": "Unknown",
            "subtopics": [],
            "topic": "",
            "confidence": 0.0,
            "all_scores": [],
        }


# ──────────────────────────────────────────────
#  Relevance Scoring
# ──────────────────────────────────────────────

def _check_irrelevant(text: str) -> bool:
    """Check if text is likely NOT UPSC-relevant (celebrity, entertainment, sports, gossip, etc.)."""
    return bool(_IRRELEVANT_PATTERNS.search(text.lower()))


def _count_matched_criteria(text: str) -> tuple[list[str], int]:
    """Count how many of the UPSC relevance criteria are matched by this text.

    Returns:
        (matched_criterion_texts, count) — list of matched criterion descriptions and count
    """
    if not _relevance_criteria:
        return [], 0

    text_lower = text.lower()
    matched_criteria = []
    for criterion in _relevance_criteria:
        # Extract keywords from criterion question
        keywords = re.findall(r"\b(indian|government|policy|legislation|foreign|"
                              r"economic|environment|climate|disaster|science|tech|"
                              r"social|justice|welfare|constitutional|legal|"
                              r"security|border|supreme court|parliament)\b",
                              criterion.lower())
        matched = sum(1 for kw in keywords if kw in text_lower)
        if matched >= 2 or any(kw in text_lower for kw in ["india", "indian"] if "india" in criterion.lower()):
            matched_criteria.append(criterion[:80])  # Truncate long criterion text
    return matched_criteria, len(matched_criteria)


def _high_ca_boost(text: str) -> float:
    """Compute a boost factor based on high-current-affairs topic overlap."""
    if not _high_ca_topics:
        return 0.0

    text_lower = text.lower()
    boost = 0.0
    for topic in _high_ca_topics:
        topic_keywords = re.findall(r"\b\w+\b", topic.lower())
        matched = sum(1 for kw in topic_keywords if len(kw) > 3 and kw in text_lower)
        if matched >= 2:
            boost += 0.1
    return min(boost, 0.5)  # Cap at 0.5


def score_relevance(
    text: str,
    classification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute UPSC relevance score for a text.

    Factors:
      1. Syllabus confidence (cosine similarity against syllabus topics)
      2. GS paper match quality
      3. Relevance criteria satisfaction
      4. High-CA topic boost
      5. Irrelevant content penalty

    Returns:
      Scoring dict with keys: is_relevant, relevance_score, priority_score,
      gs_paper, subtopics, matched_criteria, confidence
    """
    if not text.strip():
        return {
            "is_relevant": False,
            "relevance_score": 0.0,
            "priority_score": 0.0,
            "gs_paper": "Unknown",
            "subtopics": [],
            "matched_criteria": [],
            "confidence": 0.0,
        }

    # Hard rejection for clearly irrelevant content
    if _check_irrelevant(text):
        return {
            "is_relevant": False,
            "relevance_score": 0.0,
            "priority_score": 0.0,
            "gs_paper": "Unknown",
            "subtopics": [],
            "matched_criteria": [],
            "confidence": 0.0,
            "rejection_reason": "irrelevant_content",
        }

    # Classify if not provided
    if classification is None:
        classification = classify_article(text)

    confidence = classification["confidence"]
    gs_paper = classification["gs_paper"]
    subtopics = classification["subtopics"]

    # Base relevance: syllabus confidence
    relevance_score = confidence

    # Boost for concrete GS paper assignment
    if gs_paper != "Unknown":
        relevance_score += 0.15

    # Boost for matched criteria
    matched_criteria, criteria_count = _count_matched_criteria(text)
    relevance_score += criteria_count * 0.08

    # High-CA topic boost
    ca_boost = _high_ca_boost(text)
    relevance_score += ca_boost

    # Penalize unknown classifications
    if gs_paper == "Unknown" and confidence < 0.2:
        relevance_score *= 0.3

    # Clip to [0, 1]
    relevance_score = max(0.0, min(1.0, relevance_score))

    # Priority: relevance + CA boost + subtopic richness
    priority_score = relevance_score * 0.6 + ca_boost * 0.3 + min(len(subtopics) * 0.05, 0.1)

    # Is relevant threshold
    is_relevant = relevance_score >= 0.35

    return {
        "is_relevant": is_relevant,
        "relevance_score": round(relevance_score, 4),
        "priority_score": round(priority_score, 4),
        "gs_paper": gs_paper,
        "subtopics": subtopics,
        "matched_criteria": matched_criteria,
        "confidence": classification["confidence"],
    }


# ──────────────────────────────────────────────
#  Novelty Scoring
# ──────────────────────────────────────────────

_previous_story_texts: list[str] = []
_previous_vectors: np.ndarray | None = None
_previous_vectorizer: TfidfVectorizer | None = None
_MAX_PREVIOUS_STORIES = 200


def score_novelty(text: str) -> dict[str, Any]:
    """Score how novel a story is compared to previously seen stories.

    Uses cosine similarity against stored previous story vectors.
    Novelty = 1 - max_similarity (capped at returning at least 0.1)

    Returns:
      Dict with novelty_score and duplicate_of (if highly similar)
    """
    global _previous_story_texts, _previous_vectors, _previous_vectorizer

    if not _previous_story_texts:
        return {"novelty_score": 1.0, "duplicate_of": None}

    try:
        # Build vectorizer from previous stories if not yet initialized
        if _previous_vectorizer is None:
            _previous_vectorizer = TfidfVectorizer(
                max_features=500,
                stop_words="english",
                sublinear_tf=True,
            )
            _previous_vectors = _previous_vectorizer.fit_transform(_previous_story_texts).toarray()
            norms = np.linalg.norm(_previous_vectors, axis=1, keepdims=True) + 1e-9
            _previous_vectors = _previous_vectors / norms

        # Vectorize new text
        text_vec = _previous_vectorizer.transform([text]).toarray()[0]
        text_norm = np.linalg.norm(text_vec) + 1e-9
        text_vec = text_vec / text_norm

        # Compute similarity against all previous stories
        sims = _previous_vectors @ text_vec
        max_sim = float(sims.max()) if len(sims) > 0 else 0.0

        novelty = max(0.1, 1.0 - max_sim)

        # Check if it's a near-duplicate
        duplicate_idx = int(sims.argmax()) if max_sim > 0.85 else None

        return {
            "novelty_score": round(novelty, 4),
            "duplicate_of": _previous_story_texts[duplicate_idx] if duplicate_idx is not None else None,
            "max_similarity": round(max_sim, 4),
        }
    except Exception as e:
        logger.error(f"Novelty scoring failed: {e}")
        return {"novelty_score": 0.5, "duplicate_of": None, "max_similarity": 0.0}


def record_story(text: str) -> None:
    """Record a story text for future novelty scoring."""
    global _previous_story_texts, _previous_vectors, _previous_vectorizer

    _previous_story_texts.append(text)

    # Keep only the most recent stories
    if len(_previous_story_texts) > _MAX_PREVIOUS_STORIES:
        _previous_story_texts = _previous_story_texts[-_MAX_PREVIOUS_STORIES:]

    # Reset so vectors get rebuilt on next novelty call
    _previous_vectors = None
    _previous_vectorizer = None


def clear_novelty_memory() -> None:
    """Clear all previous story memory (e.g., for testing or new pipeline cycle)."""
    global _previous_story_texts, _previous_vectors, _previous_vectorizer
    _previous_story_texts = []
    _previous_vectors = None
    _previous_vectorizer = None


# ──────────────────────────────────────────────
#  Cluster Processing
# ──────────────────────────────────────────────

def process_cluster(
    cluster: list[dict],
    existing_stories: list[str] | None = None,
) -> dict[str, Any]:
    """Process a single cluster through the UPSC filter pipeline.

    Args:
      cluster: List of article dicts in the cluster
      existing_stories: Optional list of previously seen story texts for novelty

    Returns:
      Processing result with all scores, classification, and filter decision
    """
    cluster_text = _build_cluster_text(cluster)

    # 1. Syllabus classification
    classification = classify_article(cluster_text)

    # 2. Relevance scoring
    relevance = score_relevance(cluster_text, classification)

    if not relevance["is_relevant"]:
        return {
            "cluster": cluster,
            "is_filtered_out": True,
            "filter_reason": relevance.get("rejection_reason", "low_relevance"),
            **relevance,
        }

    # 3. Novelty scoring
    novelty = score_novelty(cluster_text)

    # 4. Final priority score
    cluster_size = len(cluster)
    size_factor = min(cluster_size / 5.0, 1.0)
    priority_score = (
        relevance["relevance_score"] * 0.4
        + relevance["priority_score"] * 0.3
        + novelty["novelty_score"] * 0.2
        + size_factor * 0.1
    )

    # 5. Gemini threshold check
    passes_gemini_threshold = relevance["relevance_score"] >= 0.72

    return {
        "cluster": cluster,
        "is_filtered_out": False,
        "relevance_score": relevance["relevance_score"],
        "priority_score": round(priority_score, 4),
        "novelty_score": novelty["novelty_score"],
        "gs_paper": relevance["gs_paper"],
        "subtopics": relevance["subtopics"],
        "matched_criteria": relevance["matched_criteria"],
        "confidence": relevance["confidence"],
        "passes_gemini_threshold": passes_gemini_threshold,
        "cluster_size": cluster_size,
        "novelty_details": novelty,
    }


def filter_and_rank_clusters(
    clusters: list[list[dict]],
    max_stories: int = 15,
    max_gemini_calls: int = 10,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter and rank clusters for UPSC relevance.

    Args:
      clusters: List of article clusters
      max_stories: Maximum stories to return
      max_gemini_calls: Maximum Gemini API calls to budget

    Returns:
      (filtered_results, gemini_candidates)
        - filtered_results: List of processing results for stories that pass filter
        - gemini_candidates: Subset of filtered results eligible for Gemini analysis
    """
    if not clusters:
        return [], []

    results = []
    for cluster in clusters:
        result = process_cluster(cluster)
        if not result["is_filtered_out"]:
            results.append(result)

    # Sort by priority score descending
    results.sort(key=lambda r: r["priority_score"], reverse=True)

    # Limit to max_stories
    results = results[:max_stories]

    # Gemini candidates: high-relevance stories, limited to budget
    gemini_candidates = [r for r in results if r.get("passes_gemini_threshold", False)]
    gemini_candidates = gemini_candidates[:max_gemini_calls]

    logger.info(
        f"UPSC filter: {len(clusters)} clusters → {len(results)} relevant → "
        f"{len(gemini_candidates)} Gemini candidates "
        f"(scores: {[r['relevance_score'] for r in results[:5]]})"
    )

    return results, gemini_candidates
