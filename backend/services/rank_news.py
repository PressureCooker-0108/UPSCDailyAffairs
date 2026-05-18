from loguru import logger
import numpy as np
from datetime import datetime, timezone
from dateutil import parser as dateutil_parser
from config import MAX_STORIES, get_source_weight


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
        source_authorities = [get_source_weight(s) for s in sources_set]
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
