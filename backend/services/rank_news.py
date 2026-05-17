import logging
import numpy as np
from datetime import datetime, timezone
from dateutil import parser as dateutil_parser
from config import MAX_STORIES

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Source authority weights (legacy fallback)
# Kept for backward compatibility — new sources
# use SOURCE_WEIGHTS from config.py
# ──────────────────────────────────────────────
SOURCE_AUTHORITY = {
    "Reuters": 1.0,
    "Reuters Top News": 1.0,
    "Reuters Business": 1.0,
    "Associated Press": 1.0,
    "BBC": 0.95,
    "BBC World": 0.85,
    "BBC General": 0.95,
    "NYTimes": 0.9,
    "NYTimes World": 0.9,
    "NYTimes Home": 0.9,
    "The Guardian": 0.85,
    "The Guardian World": 0.82,
    "Wall Street Journal": 0.95,
    "WSJ": 0.95,
    "Financial Times": 0.95,
    "Economist": 0.9,
    "The Economist": 0.9,
    "Foreign Policy": 0.85,
    "Bloomberg": 0.9,
    "CNBC": 0.8,
    "CNBC Top News": 0.8,
    "NPR": 0.85,
    "Al Jazeera": 0.78,
    "DW": 0.8,
    "The Diplomat": 0.80,
    "SCMP": 0.7,
    "The Hindu": 0.90,
    "The Hindu Editorial": 0.92,
    "The Hindu International": 0.88,
    "Indian Express": 0.82,
    "Indian Express Explained": 0.92,
    "Times of India": 0.6,
    "Hindustan Times": 0.75,
    "LiveMint": 0.78,
    "Economic Times": 0.80,
    "Business Standard": 0.74,
    "Moneycontrol": 0.55,
    "NDTV": 0.6,
    "Down To Earth": 0.88,
    "PIB": 1.0,
}


def _get_source_authority(source_name: str) -> float:
    """Get authority weight for a source.

    Checks SOURCE_WEIGHTS from config first (UPSC sources),
    then legacy SOURCE_AUTHORITY dict.
    Defaults to 0.5 for unknown sources.
    """
    from config import SOURCE_WEIGHTS
    if source_name in SOURCE_WEIGHTS:
        return SOURCE_WEIGHTS[source_name]
    if source_name in SOURCE_AUTHORITY:
        return SOURCE_AUTHORITY[source_name]
    for key, weight in SOURCE_AUTHORITY.items():
        if key.lower() in source_name.lower():
            return weight
    return 0.5


def _latest_timestamp(cluster: list[dict]) -> datetime:
    """Return the most recent published_at in a cluster."""
    latest = datetime.min.replace(tzinfo=timezone.utc)
    for article in cluster:
        raw = article.get("published_at")
        if not raw:
            continue
        try:
            dt = dateutil_parser.parse(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt > latest:
                latest = dt
        except (ValueError, OverflowError):
            continue
    return latest


def _recency_score(latest: datetime) -> float:
    """
    Improved recency scoring.
    - 1.0 if < 2h old (breaking news)
    - Exponential decay from 2h to 48h
    - 0.0 after 48h
    """
    now = datetime.now(timezone.utc)
    age_hours = (now - latest).total_seconds() / 3600.0
    if age_hours <= 2:
        return 1.0
    if age_hours >= 48:
        return 0.0
    return float(max(0.0, np.exp(-0.1 * (age_hours - 2))))


def rank_clusters(clusters: list[list[dict]]) -> list[dict]:
    """
    Score each cluster using a multi-factor ranking:
    - Coverage (cluster size relative to max)
    - Recency: how recent the latest article is
    - Source authority: average credibility of covering sources (uses SOURCE_WEIGHTS)
    - Source diversity: number of unique authoritative sources

    Updated weights (from spec):
      relevance×0.35 + source_authority×0.20 + novelty×0.15 + policy_impact×0.15 + syllabus_overlap×0.15
    (Note: relevance, novelty, policy, and syllabus scores are computed later in the UPSC filter.
     This initial ranking uses coverage/recency as proxies, plus source authority.)

    Returns top MAX_STORIES stories sorted by score.
    """
    if not clusters:
        return []

    max_size = max(len(c) for c in clusters)
    scored: list[dict] = []

    for cluster in clusters:
        size = len(cluster)
        coverage = size / max_size if max_size > 0 else 0.0

        latest = _latest_timestamp(cluster)
        recency = _recency_score(latest)

        # Source authority: average authority of all sources covering this story
        sources_set = {a.get("source", "Unknown") for a in cluster}
        source_authorities = [_get_source_authority(s) for s in sources_set]
        avg_authority = sum(source_authorities) / len(source_authorities) if source_authorities else 0.5

        # Source diversity bonus: stories covered by multiple authoritative sources are more important
        unique_sources = len(sources_set)
        diversity_bonus = min(unique_sources / 5.0, 1.0)  # Cap at 5 sources

        # Updated formula: more weight on authority (0.20), less on coverage
        # Uses config constants if available, otherwise defaults
        try:
            from config import RANK_RELEVANCE_WEIGHT, RANK_AUTHORITY_WEIGHT, RANK_NOVELTY_WEIGHT, RANK_POLICY_WEIGHT, RANK_SYLLABUS_WEIGHT
            # At this stage we only have coverage + recency as relevance proxy,
            # and authority. Novelty/policy/syllabus come later.
            # Distribute the later-stage weights proportionally across available factors.
            avail = RANK_RELEVANCE_WEIGHT + RANK_NOVELTY_WEIGHT + RANK_POLICY_WEIGHT + RANK_SYLLABUS_WEIGHT  # = 0.80
            coverage_w = RANK_RELEVANCE_WEIGHT + (RANK_NOVELTY_WEIGHT * 0.5)  # 0.35 + 0.075 = 0.425
            recency_w = (RANK_NOVELTY_WEIGHT * 0.5) + (RANK_POLICY_WEIGHT * 0.5)  # 0.075 + 0.075 = 0.15
            authority_w = RANK_AUTHORITY_WEIGHT  # 0.20
            diversity_w = (RANK_POLICY_WEIGHT * 0.5) + RANK_SYLLABUS_WEIGHT  # 0.075 + 0.15 = 0.225
        except ImportError:
            coverage_w = 0.40
            recency_w = 0.25
            authority_w = 0.20
            diversity_w = 0.15

        final = (
            coverage_w * coverage
            + recency_w * recency
            + authority_w * avg_authority
            + diversity_w * diversity_bonus
        )

        sources = sorted(sources_set)

        scored.append({
            "cluster": cluster,
            "score": float(round(final, 4)),
            "article_count": size,
            "latest_at": latest.isoformat(),
            "sources": sources,
            "avg_authority": round(avg_authority, 4),
        })

    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored[:MAX_STORIES]
