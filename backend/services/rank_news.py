import logging
import numpy as np
from datetime import datetime, timezone
from dateutil import parser as dateutil_parser
from config import MAX_STORIES

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Source authority weights
# Higher weight = more credible / authoritative source
# Used to boost stories covered by reputable outlets.
# ──────────────────────────────────────────────
SOURCE_AUTHORITY = {
    "Reuters": 1.0,
    "Reuters Top News": 1.0,
    "Reuters Business": 1.0,
    "Associated Press": 1.0,
    "BBC": 0.95,
    "BBC World": 0.95,
    "BBC General": 0.95,
    "NYTimes": 0.9,
    "NYTimes World": 0.9,
    "NYTimes Home": 0.9,
    "The Guardian": 0.85,
    "The Guardian World": 0.85,
    "The Guardian Tech": 0.85,
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
    "Al Jazeera": 0.8,
    "DW": 0.8,
    "DW (Germany)": 0.8,
    "SCMP": 0.7,
    "SCMP (China)": 0.7,
    "Japan Times": 0.7,
    "The Verge": 0.7,
    "Ars Technica": 0.7,
    "TechCrunch": 0.65,
    "Wired": 0.7,
    "VentureBeat": 0.6,
    "MarketWatch": 0.65,
    "Investing.com": 0.55,
    "Yahoo Finance": 0.55,
    "Seeking Alpha": 0.5,
    "The Hindu": 0.75,
    "Times of India": 0.6,
    "Indian Express": 0.65,
    "LiveMint": 0.6,
    "Economic Times": 0.65,
    "Business Standard": 0.6,
    "Moneycontrol": 0.55,
    "NDTV": 0.6,
    "Hacker News": 0.6,
    "Y Combinator": 0.6,
    "Artificial Intelligence News": 0.45,
    "OilPrice": 0.4,
    "Energy Voice": 0.5,
}


def _get_source_authority(source_name: str) -> float:
    """Get authority weight for a source, defaulting to 0.5 for unknown sources."""
    # Check exact match first
    if source_name in SOURCE_AUTHORITY:
        return SOURCE_AUTHORITY[source_name]
    # Check if source name contains any known key
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
    # Exponential decay: score = e^(-0.1 * (age-2))
    # This gives: ~82% at 4h, ~67% at 6h, ~37% at 12h, ~14% at 24h
    return float(max(0.0, np.exp(-0.1 * (age_hours - 2))))



def rank_clusters(clusters: list[list[dict]]) -> list[dict]:
    """
    Score each cluster using a multi-factor ranking:
    - Coverage (cluster size relative to max): how many articles cover this
    - Recency: how recent the latest article is
    - Source authority: average credibility of covering sources
    - Source diversity: number of unique authoritative sources
    
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

        # Final score: weighted multi-factor combination
        # Normalized to sum to 1.0: 50% coverage, 30% recency, 10% authority, 10% diversity
        final = (
            0.50 * coverage
            + 0.30 * recency
            + 0.10 * avg_authority
            + 0.10 * diversity_bonus
        )

        sources = sorted(sources_set)

        scored.append({
            "cluster": cluster,
            "score": float(round(final, 4)),
            "article_count": size,
            "latest_at": latest.isoformat(),
            "sources": sources,
        })

    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored[:MAX_STORIES]
