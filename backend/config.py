"""
Configuration for UPSC Daily Affairs.
RSS feeds, source metadata, and pipeline constants for UPSC-relevant news processing.
"""

import re

# ──────────────────────────────────────────────
# RSS Feed Sources (UPSC-focused)
# ──────────────────────────────────────────────
# Each entry: name, rss_url (or None for custom scrapers), sectors (GS paper mapping)
# PIB, DTE, PRS, etc. are high-priority UPSC sources.
# Generic/Tabloid sources removed.
# ──────────────────────────────────────────────

RSS_SOURCES = [
    # ══════ TIER 1 — Highest Priority ══════

    # ── PIB (Government Releases) ──
    {"name": "PIB", "url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1", "sectors": ["India", "Governance"]},

    # ── Indian Express — Explained (Policy Explainers) ──
    {"name": "Indian Express Explained", "url": "https://indianexpress.com/section/explained/feed/", "sectors": ["India", "Governance"]},

    # ── The Hindu Editorials ──
    {"name": "The Hindu Editorial", "url": "https://www.thehindu.com/opinion/editorial/?service=rss", "sectors": ["India", "Governance"]},

    # ── The Hindu (National) ──
    {"name": "The Hindu", "url": "https://www.thehindu.com/news/national/?service=rss", "sectors": ["India"]},

    # ─️─ The Hindu International ──
    {"name": "The Hindu International", "url": "https://www.thehindu.com/news/international/?service=rss", "sectors": ["Geopolitics", "India"]},

    # ── Down To Earth (Environment) ──
    {"name": "Down To Earth", "url": "https://www.downtoearth.org.in/rss/all.xml", "sectors": ["India", "Environment"]},

    # ══════ TIER 2 — Core UPSC Coverage ══════

    # ── Indian Express (India) ──
    {"name": "Indian Express", "url": "https://indianexpress.com/section/india/feed/", "sectors": ["India"]},

    # ── Hindustan Times ──
    {"name": "Hindustan Times", "url": "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", "sectors": ["India"]},

    # ── Economic Times (Economy) ──
    {"name": "Economic Times", "url": "https://economictimes.indiatimes.com/rssfeedstopstories.cms", "sectors": ["India"]},

    # ── LiveMint (Economy/Policy) ──
    {"name": "LiveMint", "url": "https://www.livemint.com/rss/news", "sectors": ["India"]},

    # ── Business Standard ──
    {"name": "Business Standard", "url": "https://www.business-standard.com/rss/home_page_top_stories.rss", "sectors": ["India"]},

    # ══════ TIER 3 — Geopolitics / International Relations ══════

    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "sectors": ["Geopolitics"]},
    {"name": "The Guardian World", "url": "https://www.theguardian.com/world/rss", "sectors": ["Geopolitics"]},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "sectors": ["Geopolitics"]},
    {"name": "The Diplomat", "url": "https://thediplomat.com/feed/", "sectors": ["Geopolitics"]},

    # ══════ TIER 4 — Context / Reports ══════

    # ── ET EnergyWorld (Environment/Energy) ──
    {"name": "ET EnergyWorld", "url": "https://energy.economictimes.indiatimes.com/rss/topstories", "sectors": ["India", "Environment"]},
]

# ──────────────────────────────────────────────
# PRS Legislative Research — Custom Scraper Config
# ──────────────────────────────────────────────
# PRS India does not provide RSS feeds.
# It is fetched via a lightweight HTML scraper defined in fetch_news.py
# that targets key pages (bills, acts, policy explainers, parliament summaries).
# ──────────────────────────────────────────────

PRS_SCRAPER_CONFIG = {
    "enabled": True,
    "base_url": "https://prsindia.org",
    "pages": [
        "/blog",              # Policy explainers & analysis
        "/theprsblog",        # Parliament summaries
        "/bill-tracker",      # Bills tracking
    ],
    "max_articles": 20,
}

# ──────────────────────────────────────────────
# Source Metadata
# ──────────────────────────────────────────────
# Maps source name → type, authority_score, upsc_priority
# Used for ranking, filtering, and Gemini eligibility.
# ──────────────────────────────────────────────

SOURCE_METADATA = {
    "PIB": {"type": "government", "authority_score": 1.0, "upsc_priority": "very_high"},
    "PRS": {"type": "legislative", "authority_score": 0.98, "upsc_priority": "very_high"},
    "Indian Express Explained": {"type": "explainer", "authority_score": 0.92, "upsc_priority": "very_high"},
    "The Hindu Editorial": {"type": "editorial", "authority_score": 0.92, "upsc_priority": "very_high"},
    "The Hindu": {"type": "editorial", "authority_score": 0.90, "upsc_priority": "high"},
    "The Hindu International": {"type": "editorial", "authority_score": 0.88, "upsc_priority": "high"},
    "Down To Earth": {"type": "environment", "authority_score": 0.88, "upsc_priority": "high"},
    "Indian Express": {"type": "news", "authority_score": 0.82, "upsc_priority": "high"},
    "Hindustan Times": {"type": "news", "authority_score": 0.75, "upsc_priority": "medium"},
    "Economic Times": {"type": "news", "authority_score": 0.80, "upsc_priority": "high"},
    "LiveMint": {"type": "news", "authority_score": 0.78, "upsc_priority": "medium"},
    "Business Standard": {"type": "news", "authority_score": 0.74, "upsc_priority": "medium"},
    "ET EnergyWorld": {"type": "news", "authority_score": 0.72, "upsc_priority": "medium"},
    "BBC World": {"type": "news", "authority_score": 0.85, "upsc_priority": "medium"},
    "The Guardian World": {"type": "news", "authority_score": 0.82, "upsc_priority": "medium"},
    "Al Jazeera": {"type": "news", "authority_score": 0.78, "upsc_priority": "medium"},
    "The Diplomat": {"type": "news", "authority_score": 0.80, "upsc_priority": "medium"},
}

# ──────────────────────────────────────────────
# Source Weights (for ranking formula)
# ──────────────────────────────────────────────
# Used in rank_news.py to boost stories from authoritative UPSC sources.
# Higher weight = more influence on final ranking score.
# ──────────────────────────────────────────────

SOURCE_WEIGHTS = {
    "PIB": 1.0,
    "PRS": 0.98,
    "Indian Express Explained": 0.92,
    "The Hindu Editorial": 0.92,
    "The Hindu": 0.90,
    "The Hindu International": 0.88,
    "Down To Earth": 0.88,
    "Indian Express": 0.82,
    "BBC World": 0.85,
    "The Guardian World": 0.82,
    "Economic Times": 0.80,
    "The Diplomat": 0.80,
    "Al Jazeera": 0.78,
    "LiveMint": 0.78,
    "Hindustan Times": 0.75,
    "Business Standard": 0.74,
    "ET EnergyWorld": 0.72,
}


def get_source_metadata(source_name: str) -> dict:
    """Get metadata for a source, returning defaults if not found."""
    return SOURCE_METADATA.get(source_name, {
        "type": "news",
        "authority_score": 0.5,
        "upsc_priority": "low",
    })


def get_source_weight(source_name: str) -> float:
    """Get ranking weight for a source, defaulting to 0.5."""
    return SOURCE_WEIGHTS.get(source_name, 0.5)


# ──────────────────────────────────────────────
# Content-Type Detection Keywords
# ──────────────────────────────────────────────
# Used in upsc_filter.py to detect and boost
# high-value content types (explainers, policy analysis, etc.).
# ──────────────────────────────────────────────

CONTENT_TYPE_PATTERNS = {
    "editorial": [
        r"\b(editorial|opinion|viewpoint|op-ed|commentary)\b",
    ],
    "explainer": [
        r"\b(explained|explainer|what is|what are|how does|why is|understanding|in focus)\b",
    ],
    "policy_release": [
        r"\b(cabinet approves|cabinet decisions|government notifies|policy announced|new policy|\bguidelines issued|scheme launched|mission launched)\b",
    ],
    "bill": [
        r"\b(bill passed|bill introduced|parliament bill|legislative bill|new bill|\bamendment bill|finance bill|bill tabled)\b",
    ],
    "report": [
        r"\b(report says|committee report|survey finds|annual report|\bstats released|data shows|economic survey)\b",
    ],
    "speech": [
        r"\b(address to|speech at|remarks at|inaugural address|budget speech|president address|pm addresses)\b",
    ],
    "committee_report": [
        r"\b(standing committee|select committee|parliamentary committee|committee recommends|panel suggests)\b",
    ],
    "environment_update": [
        r"\b(climate change|global warming|biodiversity|conservation|wetland|pollution|emissions|renewable energy|\bsustainable|greenhouse gas|endangered species|deforestation)\b",
    ],
    "economic_policy": [
        r"\b(fiscal policy|monetary policy|rbi policy|interest rate|\bgdp growth|inflation|budget|fiscal deficit|current account)\b",
    ],
    "governance": [
        r"\b(governance|e-governance|transparency|accountability|right to information|public service|administrative reform)\b",
    ],
    "constitutional": [
        r"\b(supreme court|high court|constitution|fundamental rights|directive principles|writ petition|judicial review|constitutional amendment)\b",
    ],
    "international_relations": [
        r"\b(diplomatic|bilateral|multilateral|treaty|summit|foreign minister|external affairs|strategic partnership|memorandum of understanding)\b",
    ],
}

CONTENT_TYPE_BOOST = {
    "explainer": 0.10,
    "editorial": 0.08,
    "policy_release": 0.10,
    "bill": 0.12,
    "committee_report": 0.10,
    "report": 0.06,
    "economic_policy": 0.08,
    "governance": 0.06,
    "constitutional": 0.08,
    "international_relations": 0.06,
    "environment_update": 0.06,
    "speech": 0.04,
}


def detect_content_type(text: str) -> tuple[str, float]:
    """Detect content type from text and return (type, boost).

    Checks patterns in priority order, returning the highest-boost match.
    """
    text_lower = text.lower()
    best_type = "general"
    best_boost = 0.0

    for content_type, patterns in CONTENT_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                boost = CONTENT_TYPE_BOOST.get(content_type, 0.0)
                if boost > best_boost:
                    best_boost = boost
                    best_type = content_type
                break  # One match per type is enough

    return best_type, best_boost


# ──────────────────────────────────────────────
# Pipeline Constants
# ──────────────────────────────────────────────
MAX_STORIES = 60
CLUSTER_THRESHOLD = 0.45
RECENCY_WEIGHT = 0.4
COVERAGE_WEIGHT = 0.6

# Ranking formula weights (must sum to 1.0)
RANK_RELEVANCE_WEIGHT = 0.35
RANK_AUTHORITY_WEIGHT = 0.20
RANK_NOVELTY_WEIGHT = 0.15
RANK_POLICY_WEIGHT = 0.15
RANK_SYLLABUS_WEIGHT = 0.15


# ──────────────────────────────────────────────
# Why-It-Matters Topic Templates
# Used by summarize_news.py for context enrichment.
# ──────────────────────────────────────────────
TOPIC_TEMPLATES = {
    "default": (
        "This development is significant for UPSC preparation as it reflects "
        "ongoing trends in governance, policy, and national priorities."
    ),
    "election": (
        "Elections and political transitions shape policy direction, "
        "governance priorities, and India's democratic processes. "
        "Understanding electoral dynamics is crucial for GS2 (Polity & Governance)."
    ),
    "war": (
        "Conflicts and geopolitical tensions have wide-ranging implications "
        "for international relations, security, and global governance. "
        "Relevant for GS2 (International Relations) and GS3 (Security)."
    ),
    "economy": (
        "Economic developments directly impact India's growth trajectory, "
        "fiscal policy, and reform agenda. Essential for GS3 (Economic Development)."
    ),
    "fed": (
        "Central bank policy decisions influence capital flows, inflation, "
        "and monetary conditions globally. Important for GS3 (Economy)."
    ),
    "rate": (
        "Interest rate changes affect borrowing costs, investment, "
        "and financial sector stability. Relevant for GS3 (Economic Development)."
    ),
    "climate": (
        "Climate change and environmental developments are critical for "
        "sustainable development, disaster management, and environmental governance. "
        "Relevant for GS3 (Environment & Ecology) and GS2 (Governance)."
    ),
    "health": (
        "Public health developments impact human capital, welfare schemes, "
        "and healthcare governance. Relevant for GS2 (Social Justice) and GS3 (Health)."
    ),
    "trade": (
        "Trade policy and international economic relations shape India's "
        "external sector, manufacturing competitiveness, and foreign policy. "
        "Relevant for GS2 (International Relations) and GS3 (Economy)."
    ),
    "governance": (
        "Governance and administrative reforms are central to UPSC GS2 (Polity & Governance). "
        "Understanding policy implementation and institutional mechanisms is essential."
    ),
    "corruption": (
        "Anti-corruption measures, transparency initiatives, and accountability "
        "mechanisms are critical for good governance. Relevant for GS2 (Governance) and GS4 (Ethics)."
    ),
    "infrastructure": (
        "Infrastructure development drives economic growth and regional connectivity. "
        "Important for GS3 (Infrastructure & Economic Development)."
    ),
    "education": (
        "Education policy and reforms shape human capital development. "
        "Relevant for GS2 (Social Justice & Education)."
    ),
    "agriculture": (
        "Agricultural developments affect food security, farmer welfare, "
        "and rural economy. Important for GS3 (Agriculture & Food Security)."
    ),
}
