"""
Sector classification using deterministic keyword matching.
Classifies news into: Markets, Tech, Geopolitics, Energy, India, General.

Uses carefully curated keyword lists per sector — no TF-IDF, no ML.
Keyword matching is:
- Deterministic: same input always produces same output
- Transparent: you can see exactly why an article was classified
- Fast: runs in microseconds with zero model downloads

Key design rules:
  1. Single-word keywords are ONLY used if they uniquely identify a sector
  2. Ambiguous words (e.g. "bond" → James Bond vs bond yields) use ONLY multi-word phrases
  3. Source-assigned sectors are validated against keyword matches before being kept
  4. Fallback to TF-IDF/ML classifiers removed entirely — this IS the classifier
"""
import re
import logging

logger = logging.getLogger(__name__)

# ── Valid sectors ────────────────────────────
VALID_SECTORS = ["Markets", "Tech", "Geopolitics", "Energy", "India", "Sports", "General"]

# ── In-memory classification cache ───────────
_classification_cache: dict[str, list[str]] = {}

# ── Sector keyword definitions ───────────────
# Each sector has a list of keywords and phrases.
# ONLY unambiguous keywords are used as single words.
# Ambiguous words (e.g. "bond" which could mean James Bond or bond yields)
# must use multi-word phrases ONLY.
#
# Scoring: each occurrence of a keyword in the text adds 1 point to that sector.
# Multiple occurrences of the same keyword add multiple points.
SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Markets": [
        # Stock market
        "stock market", "stock price", "stock index", "s&p 500", "s&p", "dow jones", "dow",
        "nasdaq", "nifty", "sensex",
        # Central banks & rates (no single-word "rate" — too ambiguous)
        "interest rate", "fed rate", "rate hike", "rate cut", "rate decision",
        "federal reserve", "central bank", "monetary policy",
        # Economic data (no single-word "growth" — too broad)
        "inflation", "gdp", "economic growth", "recession", "economic data",
        "unemployment", "jobless claim", "payroll",
        "cpi data", "consumer price",
        # Corporate (no single-word "profit" — too broad)
        "earnings report", "quarterly earnings", "quarterly result",
        "corporate earning", "revenue", "profit warning",
        "layoff", "hiring",
        # Bonds (NO single-word "bond" — catches James Bond)
        "bond yield", "treasury bond", "treasury yield", "corporate bond",
        "junk bond", "bond market", "yield curve",
        # Banking
        "banking sector", "bank", "commercial bank", "investment bank",
        "federal reserve chair", "fed chair", "jerome powell",
        "loan", "mortgage rate", "mortgage",
        # Markets
        "ipo", "merger", "acquisition", "spinoff", "stock buyback",
        "dividend", "shareholder return",
        "hedge fund", "private equity", "venture capital",
        "investor confidence", "market rally", "market crash", "bear market", "bull market",
        "market volatility", "market correction",
        # Trade (no single-word "trade" — too broad)
        "trade war", "tariff", "import tariff", "export", "trade deal",
        "trade deficit", "trade surplus",
        # Currency
        "dollar", "euro", "pound sterling", "yen", "currency market",
        "forex", "exchange rate", "rupee",
        # Commodity
        "commodity price", "gold price", "oil price", "copper",
        # Crypto (ambiguous with general "crypto" but crypto IS a market)
        "cryptocurrency", "bitcoin", "ethereum", "crypto market",
        # Fiscal
        "fiscal policy", "budget deficit", "debt ceiling", "government shutdown",
        "stimulus", "bailout", "tax cut", "tax hike",
        # Housing
        "housing market", "home price", "real estate market",
        # General business
        "corporate profit", "company earning", "ceo pay",
        "market analyst", "wall street",
        # Specific terms
        "downgrade", "upgrade", "credit rating",
        "securities", "exchange commission", "sec",
    ],
    "Tech": [
        # AI & ML
        "artificial intelligence", "machine learning", "deep learning",
        "large language model", "llm", "generative ai",
        "openai", "chatgpt", "gpt", "claude", "gemini", "copilot",
        "neural network", "ai model", "ai system",
        "ai",  # "ai" is safe — in news context it always means artificial intelligence
        # Software
        "software", "app", "mobile app", "application",
        "developer", "programming", "coding", "code",
        "operating system", "ios", "android", "windows", "linux",
        "update", "software update", "software release",
        # Cloud
        "cloud computing", "cloud service", "aws", "azure", "gcp",
        "server", "database",
        # Chips
        "semiconductor", "chipmaker", "chip manufacturer",
        "nvidia", "intel", "amd", "tsmc", "processor",
        "gpu", "cpu",
        # Big Tech
        "google", "apple", "microsoft", "amazon", "meta",
        "facebook", "instagram", "whatsapp", "twitter", "tiktok",
        "youtube", "netflix", "spotify",
        # Tech companies
        "tesla", "uber", "airbnb", "zoom", "salesforce",
        # Cybersecurity
        "cybersecurity", "cyber attack", "cyber threat",
        "data breach", "hacking", "hacker", "ransomware",
        "malware", "phishing",
        # Hardware
        "smartphone", "iphone", "samsung", "pixel phone",
        "tablet", "laptop",
        "hardware", "gadget",
        # Gaming
        "gaming", "video game", "playstation", "xbox", "nintendo",
        "console",
        # Startup
        "startup", "tech startup", "unicorn",
        "venture funding", "series a", "series b", "series c",
        "seed funding", "funding round",
        # Social media
        "social media", "social network", "platform",
        # Streaming
        "streaming service", "streaming platform",
        "subscription",
        # Science/tech
        "algorithm", "robot", "robotics", "automation",
        "self-driving", "autonomous vehicle",
        "quantum computing",
        "5g", "6g",
        "blockchain",
        # General tech
        "technology", "tech industry", "big tech", "silicon valley",
        "tech company", "recode", "tech news",
        # Biotech
        "biotech", "gene editing", "crispr",
    ],
    "Geopolitics": [
        # War & conflict
        "war", "conflict", "invasion", "military action",
        "attack", "airstrike", "drone strike", "missile strike",
        "bombing", "shelling",
        "ceasefire", "truce", "peace talk", "peace negotiation",
        # Military
        "military", "army", "navy", "air force", "marine corps",
        "troop", "soldier", "general", "admiral",
        "defense", "pentagon",
        "missile", "nuclear weapon", "nuclear test",
        "weapon", "arms", "arms control",
        # Alliances
        "nato", "european union", "united nations",
        "alliance", "treaty", "pact",
        # Diplomacy
        "sanction", "embargo", "trade restriction",
        "diplomat", "diplomacy", "diplomatic",
        "embassy", "ambassador", "consulate",
        "summit", "negotiation", "foreign minister",
        "secretary of state",
        # Politics & government
        "election", "vote", "ballot", "poll",
        "president", "prime minister", "chancellor",
        "government", "parliament", "congress", "senate",
        "legislation", "policy",
        "foreign policy", "foreign affair",
        "political party", "democrat", "republican",
        # Conflict zones
        "ukraine", "russia", "china", "taiwan",
        "iran", "israel", "palestine", "gaza",
        "north korea", "afghanistan",
        "syria", "yemen", "myanmar",
        # Crises
        "refugee", "migrant", "asylum",
        "border", "border control", "border security",
        "territorial dispute", "sovereignty",
        "protest", "riot", "demonstration",
        "coup", "rebellion", "revolution", "uprising",
        "civil war", "civil unrest",
        # Terrorism
        "terror", "terrorism", "terrorist",
        "isis", "al qaeda", "taliban", "hamas", "hezbollah",
        # Human rights
        "human right", "humanitarian",
        "sanction", "war crime",
        # Intelligence
        "intelligence", "spy", "espionage", "cia", "fbi",
        "secret service",
    ],
    "Energy": [
        # Oil & gas
        "crude oil", "brent crude", "wti oil",
        "oil price", "oil production", "oil output",
        "petroleum",
        "opec", "opec+",
        "barrel",
        "natural gas", "lng", "gas price", "gas supply",
        "pipeline",
        # Oil companies
        "exxon", "chevron", "shell", "bp", "totalenergies",
        # Refining
        "refinery", "refining",
        "drilling", "exploration",
        # Renewable
        "renewable energy", "clean energy",
        "solar", "solar panel", "solar farm",
        "wind turbine", "wind farm", "wind power",
        "hydroelectric", "hydro power",
        "geothermal",
        # Nuclear
        "nuclear power", "nuclear plant", "nuclear reactor",
        # Coal
        "coal", "coal plant", "coal power",
        # Emissions & climate
        "carbon emission", "carbon tax", "carbon credit",
        "emission reduction", "net zero",
        "climate change", "global warming",
        "climate policy", "climate deal",
        "epa", "environmental regulation",
        # Green energy
        "green energy", "green technology",
        "hydrogen", "fuel cell",
        "battery technology", "energy storage",
        # Grid
        "electric grid", "power grid", "grid",
        "power plant",
        "utility", "electric utility",
        # EVs (w/ context)
        "electric vehicle", "ev",
        "ev battery",
        # Energy companies
        "energy company", "energy sector",
        "energy security", "energy supply",
        # Specific
        "fossil fuel", "energy transition",
        "decarbonization", "sustainability",
        "offshore wind", "offshore drilling",
        "energy crisis", "energy price",
        "petrochemical",
    ],
    "India": [
        # Country names
        "india", "indian",
        # Politics
        "modi", "narendra modi",
        "bjp", "bharatiya janata party",
        "congress party", "indian national congress",
        "rahul gandhi", "sonia gandhi",
        # Cities
        "delhi", "new delhi",
        "mumbai", "bangalore", "bengaluru",
        "chennai", "kolkata", "hyderabad",
        "pune", "ahmedabad",
        # Economy
        "sensex", "nifty",
        "rupee", "inr",
        "rbi", "reserve bank of india",
        "gst",
        # Digital
        "aadhaar", "upi", "digital payment",
        # Education
        "iit", "iim", "indian institute",
        # Sports
        "ipl", "indian premier league",
        "cricket",
        # Entertainment
        "bollywood",
        # Festivals
        "diwali", "holi",
        # Government
        "lok sabha", "rajya sabha",
        "supreme court",
        # Economy
        "make in india", "digital india",
        "startup india",
        # Healthcare
        "ayushman bharat",
        # Military
        "indian army", "indian navy", "indian air force",
        # Companies
        "reliance", "tata group", "tata",
        "infosys", "tcs", "wipro", "hcl",
        "jio", "airtel",
        # General
        "indian stock market", "indian economy",
        "indian election", "indian government",
        # Agriculture
        "monsoon", "kharif", "rabi",
        "minimum support price", "msp",
        "farm law",
    ],
    "Sports": [
        # Team sports & competitions
        "football", "soccer", "basketball", "tennis",
        "golf", "baseball", "hockey", "cricket",
        "formula one", "f1",
        # Leagues
        "nfl", "nba", "mlb", "nhl", "epl",
        "league", "championship", "tournament",
        "olympic", "world cup",
        "premier league", "champions league",
        "super bowl", "world series", "stanley cup",
        # General sports
        "sport", "sports",
        "game", "match", "player", "team",
        "coach", "manager", "captain",
        "athlete", "athletics",
        "stadium", "arena",
        "season", "playoff", "final",
        "goal", "touchdown", "score",
        "sports news", "sports industry",
    ],
    "General": [
        # Entertainment (movies, TV)
        "movie", "film", "cinema",
        "actor", "actress",
        "hollywood", "entertainment",
        "tv show", "television", "series",
        "streaming",
        "music", "song", "album", "concert",
        "singer", "band",
        "theatre", "broadway",
        "celebrity", "star",
        "audition", "casting",
        "director", "producer", "screenplay",

        # Health
        "health", "healthcare", "hospital",
        "doctor", "patient", "disease",
        "cancer", "covid", "pandemic",
        "vaccine", "drug",
        "treatment", "therapy", "medicine",
        # Science
        "science", "research", "study",
        "scientist", "researcher",
        "space", "nasa", "astronomy",
        "planet", "mars", "moon",
        "spacex",
        "discovery", "experiment",
        # Education
        "education", "school", "university",
        "college", "student", "teacher",
        "professor",
        # Crime
        "crime", "police", "court",
        "judge", "trial", "prison",
        "jail", "lawsuit",
        # Weather
        "weather", "storm", "hurricane",
        "tornado", "earthquake",
        "flood", "wildfire",
        "natural disaster",
        # Lifestyle
        "food", "restaurant", "chef", "recipe",
        "travel", "tourism", "hotel",
        "fashion", "beauty",
        "art", "museum", "gallery",
        "book", "author", "novel",
        # Animals
        "animal", "pet", "dog", "cat",
        "wildlife", "nature",
    ],
}

# Build a list of all unique keywords for pre-processing
_all_sectors = list(SECTOR_KEYWORDS.keys())


def _compute_sector_scores(combined_text: str) -> dict[str, int]:
    """Compute keyword match scores for all sectors against the input text.

    Each occurrence of a keyword in the text adds 1 point to that sector.
    Multiple occurrences of the same keyword add multiple points.
    Matching is case-insensitive.

    Returns:
        Dict mapping sector name to integer match count.
    """
    if not combined_text or not combined_text.strip():
        return {s: 0 for s in _all_sectors}

    text_lower = combined_text.lower()
    scores: dict[str, int] = {s: 0 for s in _all_sectors}

    for sector, keywords in SECTOR_KEYWORDS.items():
        total = 0
        for kw in keywords:
            escaped = re.escape(kw)
            # Short keywords (≤2 chars) use full word boundary to prevent false matches
            #   e.g., "ev" doesn't match "every", "event", "revenue"
            # Longer keywords use negative lookbehind only to allow plural forms
            #   e.g., "bond yield" matches "bond yields", "oil price" matches "oil prices"
            if len(kw) <= 2:
                total += len(re.findall(rf'(?<!\w){escaped}(?!\w)', text_lower))
            else:
                total += len(re.findall(rf'(?<!\w){escaped}', text_lower))
        scores[sector] = total

    return scores


def _get_best_sectors(scores: dict[str, int], threshold: float = 0.15) -> list[str]:
    """Return top sectors by score, filtered by a relative threshold.

    Only returns sectors with score > 0 AND at least `threshold` fraction
    of the top score. Capped at 3 sectors.

    Args:
        scores: Dict of sector -> match count
        threshold: Minimum fraction of top score to include (0.0 to 1.0)

    Returns:
        List of sector names, sorted by score descending.
    """
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top_score = ranked[0][1]

    if top_score == 0:
        return ["General"]

    result = []
    for sector, score in ranked:
        if score > 0 and score >= top_score * threshold:
            result.append(sector)
        if len(result) >= 3:
            break

    if not result:
        return ["General"]

    return result


def classify_sectors(combined_text: str, source_sectors: list[str] | None = None) -> list[str]:
    """Classify news text into 1-3 sectors using deterministic keyword matching.

    Uses a two-tier approach:
      1. **Source-assigned sectors** (from RSS feed config) — always trusted
         and included in results. Source sectors are reliably assigned per-feed
         in the RSS_SOURCES config, so they take precedence over keywords.
      2. **Keyword-based classification** — runs on every article to ADD
         secondary sectors that source tags might have missed. Sectors scoring
         >= 30% of the top keyword score are appended.

    Args:
        combined_text: title + description/snippet combined text
        source_sectors: sectors pre-assigned from the article's RSS source

    Returns:
        List of 1-3 sector strings (e.g. ["India", "Markets"])
    """
    # Check cache
    suffix = f"|{','.join(source_sectors)}" if source_sectors else ""
    cache_key = f"{combined_text[:200]}{suffix}"
    if cache_key in _classification_cache:
        return _classification_cache[cache_key]

    # Compute keyword match scores
    scores = _compute_sector_scores(combined_text)

    # Log inputs for debugging
    logger.info(f"[CLASSIFY] source_sectors={source_sectors}, text={combined_text[:80]}")
    logger.debug(f"[CLASSIFY] scores={dict(sorted(scores.items(), key=lambda x: -x[1])[:5])}")

    # If source sectors exist, always include them (they come from the
    # trusted RSS_SOURCES config, not the polluted DB). Use keyword matching
    # only to ADD additional sectors that the source tag might have missed.
    if source_sectors and len(source_sectors) > 0:
        best = _get_best_sectors(scores, threshold=0.3)
        combined = list(dict.fromkeys(source_sectors + [s for s in best if s not in source_sectors]))
        result = combined[:3]
        logger.info(f"[CLASSIFY] result={result} (source + keyword)")
        _classification_cache[cache_key] = result
        return result

    best = _get_best_sectors(scores, threshold=0.3)
    logger.info(f"[CLASSIFY] result={best} (keyword only, source_sectors was empty)")
    _classification_cache[cache_key] = best
    return best


# Keep backward compatibility — single-sector wrapper
def classify_sector(title: str) -> str:
    """Legacy single-sector classification. Returns first sector."""
    sectors = classify_sectors(title)
    return sectors[0] if sectors else "General"
