# Serious Operator News Dashboard — AI Agent Reference

This document is a comprehensive reference of the **Serious Operator News Dashboard** project. It is designed for AI agents (Claude, ChatGPT, Codebuff, etc.) to understand the entire codebase without direct file access.

**Last updated:** April 2025
**Project status:** Active development — backend complete, frontend complete, deployment in progress.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Directory Structure](#3-directory-structure)
4. [Backend — Complete Reference](#4-backend--complete-reference)
   - 4.1 [Entry Point: main.py](#41-entry-point-mainpy)
   - 4.2 [Configuration: config.py](#42-configuration-configpy)
   - 4.3 [Scheduler: scheduler.py](#43-scheduler-schedulerpy)
   - 4.4 [Database Layer: models/database.py](#44-database-layer-modelsdatabasepy)
   - 4.5 [SQLAlchemy Models: models/models.py](#45-sqlalchemy-models-modelsmodelspy)
   - 4.6 [Service: fetch_news.py](#46-service-fetch_newspy)
   - 4.7 [Service: clean_news.py](#47-service-clean_newspy)
   - 4.8 [Service: cluster_news.py](#48-service-cluster_newspy)
   - 4.9 [Service: classify_news.py](#49-service-classify_newspy)
   - 4.10 [Service: rank_news.py](#410-service-rank_newspy)
   - 4.11 [Service: summarize_news.py](#411-service-summarize_newspy)
   - 4.12 [Service: market_data.py](#412-service-market_datapy)
   - 4.13 [Service: briefing.py](#413-service-briefingpy)
   - 4.14 [Service: pdf_briefing.py](#414-service-pdf_briefingpy)
   - 4.15 [Test Suite](#415-test-suite)
5. [Frontend — Complete Reference](#5-frontend--complete-reference)
   - 5.1 [Entry Point: layout.tsx & page.tsx](#51-entry-point-layouttsx--pagetsx)
   - 5.2 [Components: header.tsx](#52-components-headertsx)
   - 5.3 [Components: BigStory.tsx](#53-components-bigstorytsx)
   - 5.4 [Components: TopStories.tsx & StoryCard.tsx](#54-components-topstoriestsx--storycardtsx)
   - 5.5 [Components: SectorSection.tsx](#55-components-sectorsectiontsx)
   - 5.6 [Components: MarketDashboard.tsx](#56-components-marketdashboardtsx)
   - 5.7 [Pages: Sector Detail](#57-pages-sector-detail)
   - 5.8 [API Client: lib/api.ts](#58-api-client-libapits)
   - 5.9 [Types: types/story.ts](#59-types-typesstoryts)
   - 5.10 [shadcn/ui Components](#510-shadcnui-components)
6. [Data Pipeline](#6-data-pipeline)
7. [Database Schema](#7-database-schema)
8. [API Endpoints](#8-api-endpoints)
9. [Deployment Configuration](#9-deployment-configuration)
10. [CI/CD](#10-cicd)
11. [Known Issues & Gotchas](#11-known-issues--gotchas)
12. [Development Status & Roadmap](#12-development-status--roadmap)

---

## 1. Project Overview

The **Serious Operator News Dashboard** aggregates news from 26+ global RSS sources, deduplicates and clusters similar articles, classifies them into 7 intelligence sectors (Markets, Tech, Geopolitics, Energy, India, Sports, General), ranks them by importance, generates summaries with "why it matters" analysis, provides market data via yfinance, collects user story reviews for fine-tuning, and serves everything through a clean API and a Next.js frontend.

**Target users:** Founders, investors, analysts, and curious high-agency individuals.

**Core philosophy:**
- **Less is more** — top 5–10 stories max, not a firehose
- **Signal over noise** — duplicate grouping, TF-IDF clustering, multi-factor ranking
- **No clickbait, no fluff** — every story has a summary and a reason it matters
- **Speed and clarity** — designed for daily scanning, not deep reading

**Key technical decisions:**
- **Zero external ML models** — replaced sentence-transformers with TF-IDF vectors. No model downloads, instant startup, works great on news headlines (which share keywords with sector descriptions).
- **Single uvicorn worker** — Render's free tier has 512MB RAM; `--workers 2` causes OOM.
- **No pipeline on startup** — prevents OOM crash loop. Scheduler runs pipeline every 6 hours.
- **DB-independent health check** — Render's health checker no longer crashes when DB is unreachable.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       RSS SOURCES (16+)                      │
│  BBC, NYT, Reuters, Al Jazeera, TechCrunch, Wired,          │
│  CNBC, MarketWatch, Investing.com, NDTV, Times of India,    │
│  The Hindu, Hacker News, NPR, Al Jazeera                    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│               BACKEND (Python/FastAPI)                       │
│                                                              │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐   │
│  │ Fetch   │→ │ Clean    │→ │ Persist  │→ │ Cluster    │   │
│  │ (8 thr) │  │ (regex)  │  │ (SQL)    │  │ (HDBSCAN)  │   │
│  └─────────┘  └──────────┘  └──────────┘  └─────┬──────┘   │
│                                                  │           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │           │
│  │ Briefing │← │Summarize │← │ Rank     │←──────┘           │
│  │(Markdown)│  │(TF-IDF)  │  │(4-factor)│                   │
│  └──────────┘  └──────────┘  └──────────┘                   │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Market Data (yfinance, 33 tickers, 10 threads)    │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │ API Server (FastAPI, single uvicorn worker)       │       │
│  └──────────────────────────────────────────────────┘       │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               DATABASE (PostgreSQL / SQLite)                  │
│  Tables: articles, clusters, stories, market_data,           │
│          briefings, sector_summaries, story_reviews                          │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               FRONTEND (Next.js 16 / React 19)               │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Dashboard (/page.tsx)                                 │   │
│  │  ├─ Header (branding, refresh, theme, exports)       │   │
│  │  ├─ Search bar + trending topics bar                 │   │
│  │  ├─ Big Story (featured hero card)                   │   │
│  │  ├─ Market Dashboard (indices, chart, gainers/losers)│   │
│  │  ├─ Sector Heatmap (visual grid)                     │   │
│  │  ├─ Sector Navigation (7 sector cards)               │   │
│  │  ├─ Top Stories (bento grid, 6 stories)              │   │
│  │  └─ Sector Breakdown (3-col grid)                    │   │
│  │                                                      │   │
│  │  Sector Page (/sectors/[sector]/page.tsx)            │   │
│  │  ├─ Hero with sector gradient header                 │   │
│  │  ├─ Breaking news alert section                      │   │
│  │  ├─ Stories grid (StoryCard dialog)                  │   │
│  │  └─ Source landscape table                           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Directory Structure

```
/
├── Dockerfile               # Multi-stage Docker build (repo root)
├── render.yaml              # Render deployment config
├── docker-compose.yml       # Local dev with Postgres
├── .dockerignore            # Build context exclusions
├── .github/workflows/tests.yml  # CI pipeline
├── .env.example             # Documented env vars
│
├── backend/                 # Python FastAPI backend
│   ├── main.py              # API server (FastAPI app, all endpoints)
│   ├── config.py            # RSS feed list, constants, topic templates
│   ├── scheduler.py         # APScheduler pipeline orchestrator
│   ├── requirements.txt     # Python dependencies
│   ├── Procfile             # Render non-Docker fallback
│   ├── models/
│   │   ├── database.py      # SQLAlchemy engine, CRUD operations
│   │   └── models.py        # ORM models (Article, Cluster, Summary, etc.)
│   ├── services/
│   │   ├── fetch_news.py    # RSS fetch with ThreadPoolExecutor (8 workers)
│   │   ├── clean_news.py    # HTML tag stripping, whitespace normalization
│   │   ├── cluster_news.py  # TF-IDF + HDBSCAN + LDA clustering
│   │   ├── classify_news.py # TF-IDF sector classification (6 sectors)
│   │   ├── rank_news.py     # 4-factor scoring: coverage, recency, authority, diversity
│   │   ├── summarize_news.py# TF-IDF extractive summarization + "why it matters"
│   │   ├── market_data.py   # yfinance parallel fetcher (33 tickers)
│   │   ├── briefing.py      # Executive Markdown briefing generator
│   │   └── pdf_briefing.py  # PDF generation (fpdf2 library)
│   └── tests/
│       ├── conftest.py      # Pytest fixtures (test DB, TestClient)
│       ├── test_api.py      # 18 integration tests for all endpoints
│       ├── test_classify.py # 18 unit tests for TF-IDF classification
│       └── test_pipeline.py # 9 smoke tests with real RSS feeds
│
├── frontend/                # Next.js TypeScript frontend
│   ├── package.json         # Dependencies (Next 16, React 19, shadcn/ui)
│   ├── vercel.json          # Vercel static deployment config
│   ├── next.config.ts       # Next.js configuration
│   ├── tsconfig.json        # TypeScript configuration
│   ├── postcss.config.mjs   # PostCSS with Tailwind CSS v4
│   ├── eslint.config.mjs    # ESLint flat config
│   ├── types/story.ts       # TypeScript interfaces (Story, MarketData, etc.)
│   ├── lib/api.ts           # API client (all fetch functions)
│   ├── app/
│   │   ├── layout.tsx       # Root layout (Geist fonts, ThemeProvider, Toaster)
│   │   ├── globals.css      # Tailwind CSS v4 with shadcn/ui theme variables
│   │   ├── page.tsx         # Main dashboard (search, stories, markets, exports)
│   │   └── sectors/[sector]/page.tsx  # Sector detail page
│   └── components/
│       ├── header.tsx       # Sticky header with branding, refresh, theme, exports
│       ├── theme-provider.tsx # next-themes ThemeProvider wrapper
│       ├── markets/
│       │   └── MarketDashboard.tsx  # Indices grid, chart, gainers/losers
│       ├── news/
│       │   ├── BigStory.tsx         # Featured hero story card
│       │   ├── TopStories.tsx       # Bento grid layout (6 stories)
│       │   ├── StoryCard.tsx        # Story card with Dialog for details + StoryReview form
│       │   ├── StoryReview.tsx       # Collapsible review form (section, summary, image feedback)
│       │   └── SectorSection.tsx    # Sector breakdown grid
│       └── ui/              # shadcn/ui components (~40 components)
│           ├── accordion.tsx, alert.tsx, badge.tsx, button.tsx,
│           ├── card.tsx, dialog.tsx, input.tsx, skeleton.tsx,
│           └── ... (40+ Radix-based primitives)
```

---

## 4. Backend — Complete Reference

### 4.1 Entry Point: `main.py`

**File:** `backend/main.py`
**Version:** v2.0.0 (from docstring)

**Imports and setup:**
- FastAPI app with `lifespan` context manager
- CORS middleware (reads `CORS_ORIGINS` env var, defaults to `*`)
- API key middleware (if `API_KEY` env var is set, all POST endpoints require `X-API-Key` header)
- JSON-structured logging via loguru to stdout and `logs/pipeline.log`
- 5-minute TTL in-memory cache for `/news` endpoint

**Lifecycle (`lifespan`):**
1. Calls `init_db()` — creates tables if they don't exist
2. Calls `start_scheduler()` — starts APScheduler in background thread
3. Does NOT run the pipeline on startup (was causing OOM on 512MB)

**Rate Limiter:**
```python
class RateLimiter:
    # In-memory, thread-safe using RLock + deque
    # Tracks timestamps of recent calls; rejects if too many in window
    # Used by: /pipeline/run, /markets/refresh, /briefing/generate
```

**Caching:**
```python
_news_cache: dict[str, Any] = {}
_news_cache_time: float = 0
CACHE_TTL = 300  # 5 minutes
```

**Endpoints defined in main.py:**

| Method | Path | Function | Rate Limited | Cached |
|--------|------|----------|--------------|--------|
| GET | `/` | Health check | No | No |
| GET | `/news` | Top stories | No | Yes (5min) |
| GET | `/news/stories` | All stories | No | No |
| GET | `/news/sectors` | Active sectors list | No | No |
| GET | `/news/sector/{sector}` | Stories by sector | No | No |
| GET | `/news/sector-summaries` | Sector summaries | No | No |
| GET | `/markets` | Market data | No | No |
| POST | `/markets/refresh` | Refresh market data | Yes (1/60s) | No |
| GET | `/briefing` | Latest briefing | No | No |
| POST | `/briefing/generate` | Generate briefing | Yes (1/60s) | No |
| GET | `/export/markdown` | MD download | No | No |
| GET | `/export/json` | JSON download | No | No |
| GET | `/export/pdf` | PDF download | No | No |
| GET | `/sources` | Source diversity | No | No |
| GET | `/trending` | Trending topics | No | No |
| POST | `/pipeline/run` | Trigger pipeline | Yes (1/60s) | No |
| POST | `/news/reviews` | Submit story review (public) | No | No |
| GET | `/news/reviews` | Get all submitted reviews | No | No |

**Health check** (`GET /`):
```python
@app.get("/")
def health():
    return {"status": "seriously operational"}
```
Does NOT touch the database. Render's health check will never 500 due to DB issues.

**Startup command:**
```bash
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}
```
Single worker. `--workers 2` caused OOM on 512MB RAM.

---

### 4.2 Configuration: `config.py`

**File:** `backend/config.py`

**RSS_FEEDS:** 16 URLs:
- BBC News, BBC World, Al Jazeera, NPR, NYT World, NYT Business
- CNBC Business, CNBC Tech, MarketWatch Top Stories, Investing.com
- TechCrunch, Hacker News, Wired
- The Hindu, NDTV Top Stories, Times of India

**Pipeline constants:**
```python
MAX_STORIES = 20
CLUSTER_THRESHOLD = 0.45
RECENCY_WEIGHT = 0.4
COVERAGE_WEIGHT = 0.6
```

**TOPIC_TEMPLATES:** 11 topic → "why it matters" templates (election, war, economy, fed, rate, ai, climate, market, health, trade, default).

Note: There's also `RSS_SOURCES` in `fetch_news.py` (36 sources with names), which is the actual list used by the fetcher. The `RSS_FEEDS` list in config.py is a subset/duplicate that may be dead code.

---

### 4.3 Scheduler: `scheduler.py`

**File:** `backend/scheduler.py`

**Pipeline execution (`run_pipeline`):**

Phase 1 — Core Processing (sequential):
1. **Fetch:** `fetch_rss_feeds()` — 36 RSS sources, 8 parallel threads, dedup by URL
2. **Clean:** `clean_articles()` — strip HTML tags, normalize whitespace
3. **Persist:** `save_articles()` — batch insert to DB
4. **Get recent:** `get_recent_articles(24)` — last 24 hours
5. **Cluster:** `cluster_articles()` — TF-IDF → dedup → LDA → HDBSCAN
6. **Rank:** `rank_clusters()` — 4-factor scoring
7. **Classify + Summarize:** For each cluster, classify sectors + generate summary + "why it matters"
8. **Save stories:** `save_stories()` — batch write
9. **Save sector summaries:** For each sector, generate and save a summary

Phase 2 — Post-Pipeline (parallel via ThreadPoolExecutor):
- `fetch_and_store_market_data()` — yfinance for 33 tickers
- `generate_briefing()` — Markdown executive briefing

**Scheduling:** APScheduler, runs every 6 hours (first run starts 6 hours after deploy).

---

### 4.4 Database Layer: `models/database.py`

**File:** `backend/models/database.py`

**Engine creation logic:**
```python
if DATABASE_URL:
    # If it's SQLite, localhost, or already has sslmode → no extra args
    # If it's remote Postgres → add sslmode=require
else:
    # Default: sqlite:///news.db with check_same_thread=False
```

**Session management:**
- `get_db()` — FastAPI dependency that yields a session
- Most CRUD functions create their own session (auto-commit + close)
- Some functions accept an optional `db` parameter for batch operations from the scheduler

**CRUD functions:**

| Function | Purpose |
|----------|---------|
| `init_db()` | Create all tables |
| `save_articles(articles, db?)` | Batch insert new articles (skips duplicates by URL) |
| `get_recent_articles(hours)` | Articles fetched within N hours |
| `save_stories(stories, db?)` | Clears old stories, batch inserts new ones |
| `get_top_stories(limit)` | Order by score descending |
| `get_stories_by_sector(sector, limit)` | Filter stories by JSON sector field |
| `story_count()` | Count of stories in DB |
| `last_updated()` | Most recent story creation timestamp |
| `save_market_data(data)` | Clear old market data, batch insert new |
| `get_market_data()` | All market data |
| `save_briefing(content)` | Clear old briefing, insert new |
| `get_latest_briefing()` | Most recent briefing |
| `save_sector_summary(sector, summary, count, db?)` | Upsert sector summary |
| `get_sector_summaries()` | All sector summaries |
| `get_source_diversity()` | Article source counts for last 24h |
| `get_trending_topics(hours)` | Top stories by score within time window |
| `save_review(data)` | Save a user story review |
| `get_reviews()` | Get all submitted reviews |

---

### 4.5 SQLAlchemy Models: `models/models.py`

**File:** `backend/models/models.py`

**Table: `articles`**
```python
class Article(Base):
    __tablename__ = "articles"
    id: str                  # MD5 hash of URL (primary key)
    title: str
    url: str                 # Unique, indexed
    source: str
    published_at: str
    content_snippet: str     # First ~500 chars
    fetched_at: str          # ISO timestamp
    cluster_id: Optional[int]
    embedding: Optional[str] # JSON-serialized (deprecated, no longer used)
```

**Table: `clusters`**
```python
class Cluster(Base):
    __tablename__ = "clusters"
    id: int                  # Primary key, auto-increment
    theme: str
```

**Table: `stories`** (mapped from class `Summary`)
```python
class Summary(Base):
    __tablename__ = "stories"
    id: int                  # Primary key, auto-increment
    title: str
    summary: str
    why_it_matters: str
    url: Optional[str]
    score: float
    article_count: int
    source: str              # Comma-separated source names
    published_at: str
    latest_at: str
    created_at: str
    sectors: str             # JSON-serialized list e.g. '["Tech","Markets"]'
    sector_summary: Optional[str]
    trending_score: Optional[float]
```

**Table: `market_data`**
```python
class MarketData(Base):
    __tablename__ = "market_data"
    id: int
    ticker: str              # Indexed
    name: str
    price: float
    change: float
    change_pct: float
    market_cap: Optional[str] # Formatted like "$3.12T"
    sector: str
    recorded_at: str
```

**Table: `briefings`**
```python
class Briefing(Base):
    __tablename__ = "briefings"
    id: int
    content: str             # Full Markdown text
    created_at: str
```

**Table: `story_reviews`** (new!)
```python
class StoryReview(Base):
    __tablename__ = "story_reviews"
    id: str                  # UUID (primary key)
    story_title: str
    story_url: Optional[str]
    correct_section: str     # "yes" or "no"
    suggested_section: Optional[str]  # Sector user suggested if "no"
    summary_concise: str     # "yes" or "no"
    picture_available: str   # "yes" or "no"
    comment: Optional[str]   # Free-text feedback
    created_at: str
```

**Table: `sector_summaries`**
```python
class SectorSummary(Base):
    __tablename__ = "sector_summaries"
    id: int
    sector: str              # Indexed
    summary: str
    headline_count: int
    created_at: str
```

---

### 4.6 Service: `fetch_news.py`

**File:** `backend/services/fetch_news.py`

**RSS_SOURCES:** 36 named sources including:
- Global: NYTimes (World, Home, Business), BBC (World, Top), Reuters Top News, Al Jazeera, Guardian World, NPR
- Business: CNBC (Business, Tech), MarketWatch, Investing.com
- Tech: TechCrunch, HN, Wired, Ars Technica, The Verge
- India: NDTV, Times of India, The Hindu, Indian Express, Business Standard, Moneycontrol
- Energy: OilPrice, Energy Voice

**Key functions:**
```python
def _fetch_single_source(source: dict) -> list[dict]:
    """Fetch + normalize one RSS feed using feedparser.
    Returns articles with: id (MD5 of URL), title (lowercased), url, source, published_at, content_snippet."""

def fetch_rss_feeds() -> list[dict]:
    """ThreadPoolExecutor with 8 workers.
    All futures submitted → iterate as_completed → deduplicate by URL on main thread.
    Returns unique articles sorted by fetch order."""
```

---

### 4.7 Service: `clean_news.py`

**File:** `backend/services/clean_news.py`

Simple utility:
```python
def clean_text(text: str) -> str:
    # Strip HTML tags with regex (<[^>]*>)
    # Normalize whitespace (collapse multiple spaces)

def clean_articles(articles: list[dict]) -> list[dict]:
    # Apply clean_text to title and content_snippet
```

---

### 4.8 Service: `cluster_news.py`

**File:** `backend/services/cluster_news.py`

**Pipeline:**
1. Build text from title + snippet
2. TF-IDF vectorize (max 500 features, English stop words)
3. Deduplicate by cosine similarity > 0.92
4. LDA topic modeling (CountVectorizer → LatentDirichletAllocation)
5. Augment TF-IDF vectors with one-hot topic features (weight 0.3)
6. HDBSCAN clustering (euclidean, min_cluster_size = max(2, n/20))
7. Noise articles (label == -1) become single-article clusters

**Key parameters tuned for speed:**
```python
HDBSCAN(
    min_cluster_size=max(2, len(articles) // 20),
    min_samples=2,
    metric="euclidean",
    cluster_selection_epsilon=CLUSTER_THRESHOLD,  # 0.45
    prediction_data=False,   # Skip approximate_predict (not used downstream)
    core_dist_n_jobs=-1,     # Use all CPU cores
)
```

---

### 4.9 Service: `classify_news.py`

**File:** `backend/services/classify_news.py`

Classifies text into 1-2 of: **Markets, Tech, Geopolitics, Energy, India, General**.

**Method:** TF-IDF cosine similarity against rich sector descriptions (keyword-dense paragraphs, not keyword lists).

**Algorithm:**
1. Split combined text into segments at sentence boundaries (> 20 chars each)
2. TF-IDF vectorize each segment
3. Compare each segment vector against pre-computed sector description vectors
4. Weighted voting: each segment votes for its best sector, weighted by confidence
5. Return top sector + second sector if confidence gap isn't overwhelming (> 0.65)

**Sector descriptions** are detailed paragraphs, e.g.:
```python
"Markets": "Financial markets and the economy. Topics include stock market indices like the S&P 500 and Dow Jones, central bank policy decisions by the Federal Reserve and other major central banks..."
```

**Cache:** In-memory dict keyed by text hash.

---

### 4.10 Service: `rank_news.py`

**File:** `backend/services/rank_news.py`

**4-factor scoring (weighted sum):**

| Factor | Weight | Calculation |
|--------|--------|-------------|
| Coverage | 50% | Cluster size / max cluster size |
| Recency | 30% | Exponential decay: 1.0 (<2h) → 0.0 (>48h) |
| Source Authority | 10% | Average authority weight of unique sources |
| Source Diversity | 10% | min(num_sources, 5) / 5 |

**Source Authority weights** (from dict `SOURCE_AUTHORITY`):
- 1.0: Reuters, Associated Press
- 0.9: BBC, NYT, Guardian, NPR, Wired
- 0.8: Al Jazeera, Times of India
- 0.7: CNBC, MarketWatch
- 0.6: TechCrunch, The Verge, Ars Technica, The Hindu, Indian Express
- 0.5: Default (any unlisted source)
- 0.4: Business Standard, Moneycontrol, OilPrice, Energy Voice, Investing.com

**Returns:** Top `MAX_STORIES` (20) clusters sorted by score descending.

---

### 4.11 Service: `summarize_news.py`

**File:** `backend/services/summarize_news.py`

**Functions:**

**`_pick_headline(cluster)`** — TF-IDF centroid selection:
1. TF-IDF vectorize all titles in cluster
2. Compute centroid (mean vector)
3. Score each title: 80% cosine similarity to centroid + 20% title length
4. Return best title + URL

**`_make_summary(cluster)`** — Extractive summarization:
1. Extract sentences from all article snippets (regex split on `[.!?]`)
2. Filter out short (< 10 chars) and duplicate sentences
3. TF-IDF vectorize unique sentences
4. Score each sentence: 70% centroid similarity + 30% informativeness (proper nouns, numbers, length)
5. Select top sentences greedily, skipping sentences too similar (> 0.85 cos sim) to already-selected ones
6. Limit to 100 words

**`_why_it_matters(cluster)`** — Topic matching:
1. Pre-compute TF-IDF vectors for 11 topic descriptions at module load
2. Vectorize cluster text
3. Find best matching topic via cosine similarity
4. Return the template string (e.g., "AI developments are reshaping industries, labor markets, and competitive dynamics.")

**`summarize_stories(clusters)`** — Orchestrator:
- For each cluster: pick headline, generate summary, generate "why it matters"
- Returns list of story dicts

---

### 4.12 Service: `market_data.py`

**File:** `backend/services/market_data.py`

**Watchlist:** 33 tickers across sectors:
- **Indices (5):** ^GSPC, ^DJI, ^IXIC, ^RUT, ^VIX
- **Tech (7):** AAPL, MSFT, GOOGL, NVDA, META, TSLA, AVGO
- **Finance (6):** JPM, GS, V, MA, BAC, BRK-B
- **Energy (4):** XOM, CVX, COP, SLB
- **Healthcare (4):** UNH, JNJ, PFE, LLY
- **Consumer (5):** WMT, AMZN, HD, MCD, NKE
- **India (2):** ^BSESN, ^NSEI
- **Markets (1):** EEM

**Functions:**
```python
def fetch_one(item: dict) -> dict | None:
    # yfinance Ticker object → info dict
    # Falls back to fast_info if regularMarketPrice is missing

def fetch_and_store_market_data() -> list[dict]:
    # ThreadPoolExecutor with 10 workers
    # Fetches all 33 tickers in ~3-5s
    # Saves to DB in one batch

def get_big_market_movers(threshold=1.5) -> dict:
    # Returns { gainers, losers, indices, all }
    # Filtered by change_pct > threshold
```

---

### 4.13 Service: `briefing.py`

**File:** `backend/services/briefing.py`

Generates a formatted Markdown executive briefing:

```
# OPERATOR BRIEF — April 10, 2025 at 14:30 UTC

---

## Executive Summary
**Top Story:** [headline]
**Coverage:** [N] articles from [sources]
**Sectors:** [sectors]
**Total tracked stories:** [N]
**Sources monitoring:** [N]

---

## Market Dashboard
### Indices
| Ticker | Price | Change | % Change |
| 📈 S&P 500 | $5,432.10 | +23.45 | 📈 +0.43% |

### 📈 Notable Gainers
### 📉 Notable Losers

---

## Top Stories
### 1. [Headline]
**Score:** 85.3 | **Sources:** BBC, Reuters | **Sectors:** Geopolitics
> Summary...
**⚡ Implications:** ...
🔗 [Read more](url)

---

## Source Landscape
| Source | Articles | Share |
| BBC | 12 | 15.2% ███ |

---

*Generated automatically by the Serious Operator News Dashboard*
```

---

### 4.14 Service: `pdf_briefing.py`

**File:** `backend/services/pdf_briefing.py`

Uses `fpdf2` (FPDF) library to generate a styled PDF briefing. Features:
- Custom color palette (dark backgrounds, accent colors)
- Header with live indicator dot
- Executive summary card
- Market data tables with 📈/📉 indicators
- Top stories with score badges
- Source landscape with bar representation
- Sanitizes non-Latin-1 characters to ASCII (emojis → text)

---

### 4.15 Test Suite

**Directory:** `backend/tests/`

**`conftest.py`** — Fixtures:
- `test_db()` — SQLite in-memory database, creates tables, yields session, drops tables
- `client()` — FastAPI TestClient with overridden DB dependency
- `sample_articles()` — 3 sample article dicts
- `sample_clusters()` — 3 cluster lists

**`test_classify.py`** — 18 unit tests:
- `test_classify_sectors_markets()` — "S&P 500 hits record high" → ["Markets"]
- `test_classify_sectors_tech()` — "Apple launches new AI chip" → ["Tech"]
- `test_classify_sectors_multiple()` — "Fed rate cut boosts tech stocks" → ["Markets", "Tech"]
- `test_empty_text()` → ["General"]
- `test_cache()` — Verify caching works
- `test_classify_sector()` — Legacy wrapper returns single sector
- Various edge cases: short text, mixed sectors, energy keywords, India keywords

**`test_api.py`** — 18 integration tests:
- `test_health()` — GET / returns 200 with correct message
- `test_top_stories_empty()` — GET /news returns empty when no data
- `test_top_stories_with_data()` — GET /news returns stories after inserting
- `test_sectors()` — GET /news/sectors returns unique sorted sectors
- `test_sector_filter()` — GET /news/sector/Markets filters correctly
- `test_sector_summaries()` — GET /news/sector-summaries
- `test_market_data_empty()` — GET /markets
- `test_market_data_with_data()` — With market data inserted
- `test_briefing_empty()` — GET /briefing
- `test_export_json()` — GET /export/json
- `test_export_markdown()` — GET /export/markdown
- `test_export_pdf()` — GET /export/pdf
- `test_sources()` — GET /sources
- `test_trending()` — GET /trending
- `test_pipeline_run()` — POST /pipeline/run returns 202
- `test_rate_limiting()` — Multiple POSTs get 429
- `test_cors_headers()` — CORS headers present
- `test_health_db_independent()` — Health check returns 200 even with empty DB

**`test_pipeline.py`** — 9 smoke tests (marked with `@pytest.mark.smoke`):
- Test real RSS feed fetches from BBC, TechCrunch, Al Jazeera, NYT, Wired, and local feeds
- Test the full cluster_articles function with real data
- `continue-on-error: true` in CI — feed outages won't block PRs

**pyproject.toml:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "smoke: tests that make real HTTP requests to RSS feeds (network-dependent)",
]
```

---

## 5. Frontend — Complete Reference

### 5.1 Entry Point: `layout.tsx` & `page.tsx`

**`layout.tsx`** — Root layout:
- Geist Sans + Geist Mono fonts (via `next/font/google`)
- ThemeProvider (next-themes) wrapping children
- Toaster (sonner) for toast notifications
- Dark mode supported but defaults to light
- Metadata: "Serious Operator News Dashboard"

**`page.tsx`** — Main dashboard (client component):
- State: `stories`, `loading`, `error`, `searchQuery`, `trendingData`, `now`, `lastFetchedAt`
- **Data loading:** `fetchStories()` + `fetchTrending(48)` every 2 minutes, plus on mount
- **Search:** Filters stories by headline, summary, or sector match
- **Layout sections:**
  1. Top bar: Search input + "Updated Xm ago" indicator
  2. Trending topics bar: Top 6 trending topics as pills
  3. Big Story: Featured hero (highest-scored story)
  4. MarketDashboard: Markets section
  5. SectorHeatmap: Visual sector overview with color-coded intensity
  6. Sector Navigation: 6 clickable cards linking to `/sectors/{sector}`
  7. TopStories: Bento grid of stories #2-7
  8. SectorSection: 3-column grid of sector breakdowns
  9. Export buttons: Markdown, JSON, PDF
- **States:** Loading spinner, error with retry button, empty "Station Idle" state, search-no-results state

**Key detail:** The `SectorHeatmap` component is imported but its file is not listed in the component directory — it may need to be created or the import removed.

### 5.2 Components: `header.tsx`

**File:** `frontend/components/header.tsx`

Sticky header (`backdrop-blur-xl`):
- **Brand:** Globe icon with green pulsing dot + "Operator Brief" title + tagline
- **Actions:** Theme toggle (sun/moon), MD download, JSON download, PDF download, Refresh button
- **Refresh:** POSTs to `/pipeline/run`, handles 429 rate limit with toast, reloads page on success
- **API URL:** Falls back to `http://127.0.0.1:8001` if `NEXT_PUBLIC_API_URL` is not set

### 5.3 Components: `BigStory.tsx`

**File:** `frontend/components/news/BigStory.tsx`

The featured story — largest element on the page:
- Full-width card with gradient background
- "Critical Intelligence" label with animated ping dot
- 6xl bold headline (group hover: color shift)
- 2xl summary text
- "Implication" section (why_it_matters) in a bordered card
- Entire card is a clickable link to the original article URL
- Handles null/undefined story gracefully

### 5.4 Components: `TopStories.tsx` & `StoryCard.tsx`

**`TopStories.tsx`** — Bento grid layout:
```
┌─────────────────┬─────────────────┐
│                 │                 │
│   Story 0       │   Story 1       │
│   (featured)    │   (wide)        │
│   col-span-2    │                 │
│   row-span-2    ├─────────────────┤
│                 │                 │
│                 │   Story 2       │
├─────────────────┤                 │
│   Story 3       ├─────────────────┤
│                 │                 │
├─────────────────┤   Story 4       │
│   Story 5       │   (tall)        │
│                 │   col-span-1    │
│                 │   row-span-2    │
└─────────────────┴─────────────────┘
```

**`StoryCard.tsx`** — Card with dialog:
- Card shows: headline, summary (3-line clamp), "Context:" (why_it_matters, 2-line clamp italic)
- Clicking opens a Dialog with: sector badges, score badge, source count, full summary, "Why It Matters" box, "View original source" link, and a collapsible **StoryReview** form at the bottom where users can:
- Flag whether the story is in the correct sector (with suggested sector dropdown)
- Rate if the summary is concise
- Confirm whether the image/article is available
- Leave free-text feedback

All reviews are saved via `POST /news/reviews` (public endpoint, no API key required).

### 5.5 Components: `SectorSection.tsx`

**File:** `frontend/components/news/SectorSection.tsx`

3-column grid of sector cards:
- Each card shows: emoji icon, sector name, up to 4 story headlines (2-line clamp), "+N more stories..." if applicable
- Cards are links to `/sectors/{sector}`

### 5.6 Components: `MarketDashboard.tsx`

**File:** `frontend/components/markets/MarketDashboard.tsx`

Data fetched every 60 seconds:
- **Indices:** Grid of index cards showing ticker, price, change %, with green/red arrows
- **Chart:** Recharts `BarChart` showing top 10 movers (gainers green, losers red)
- **Gainers:** Emerald-themed list of top gainers with company name, ticker, price, change %
- **Losers:** Red-themed list of top losers (same format)
- Refresh button with rate limit handling
- Fallback for empty market data

### 5.7 Pages: Sector Detail

**File:** `frontend/app/sectors/[sector]/page.tsx`

Dynamic route for each of the 6 sectors:
- Back button to dashboard
- Hero section: Gradient banner with sector-specific colors (emerald/blue/red/amber/orange/slate), icon, story count badge, sector summary text, source count
- Breaking news alert: Score > 70 stories highlighted in red section
- All stories grid: 3-column StoryCard grid (with dialog)
- Source landscape: Grid of top 10 sources with article counts

### 5.8 API Client: `lib/api.ts`

**File:** `frontend/lib/api.ts`

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001"
```

**Functions:**

| Function | Endpoint | Returns |
|----------|----------|---------|
| `fetchStories()` | GET `/news` | `Story[]` |
| `fetchSectorStories(sector)` | GET `/news/sector/{sector}` | `Story[]` |
| `fetchMarketData()` | GET `/markets` | `{ all, gainers, losers, indices }` |
| `fetchBriefing()` | GET `/briefing` | `Briefing | null` |
| `generateBriefing()` | POST `/briefing/generate` | `Briefing | null` |
| `fetchSectorSummaries()` | GET `/news/sector-summaries` | `SectorSummary[]` |
| `fetchSourceDiversity()` | GET `/sources` | `SourceDiversity[]` |
| `fetchTrending(hours)` | GET `/trending?hours=N` | `TrendingItem[]` |
| `downloadMarkdown()` | GET `/export/markdown` | Opens in new tab (anchor click) |
| `downloadJson()` | GET `/export/json` | Opens in new tab |
| `downloadPdf()` | GET `/export/pdf` | Opens in new tab |
| `submitReview(review)` | POST `/news/reviews` | Submit user story review (public) |

All fetch functions have try/catch and return empty defaults on failure.

### 5.9 Types: `types/story.ts`

**File:** `frontend/types/story.ts`

```typescript
interface Story {
  headline: string
  summary: string
  why_it_matters: string
  url?: string
  sectors?: string[]
  score?: number
  article_count?: number
  source?: string[]
  sector_summary?: string
  trending_score?: number
}

interface MarketDataPoint {
  ticker: string
  name: string
  price: number
  change: number
  change_pct: number
  market_cap?: string
  sector: string
}

interface SectorSummary {
  sector: string
  summary: string
  headline_count: number
  created_at: string
}

interface SourceDiversity {
  source: string
  count: number
  pct: number
}

interface Briefing {
  content: string
  created_at: string
}

interface StoryReview {
  story_title: string
  story_url?: string
  correct_section: "yes" | "no"
  suggested_section?: string
  summary_concise: "yes" | "no"
  picture_available: "yes" | "no"
  comment?: string
}

const SECTORS = ["Markets", "Tech", "Geopolitics", "Energy", "India", "Sports", "General"] as const
type Sector = (typeof SECTORS)[number]
```

### 5.10 shadcn/ui Components

**Directory:** `frontend/components/ui/` — 40+ components generated by shadcn/ui.

All are standard shadcn/ui components (Radix primitives + Tailwind styling). Key ones used:
- `badge.tsx` — Sector badges, score badges
- `button.tsx` — All buttons (variant, size variants)
- `card.tsx` — Cards for sectors, markets, stories
- `dialog.tsx` — Story detail modal
- `input.tsx` — Search input
- `skeleton.tsx` — Loading skeletons

---

## 6. Data Pipeline

The full pipeline runs in this order:

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  1. FETCH │──▶│  2. CLEAN │──▶│ 3. PERSIST│──▶│ 4. CLUSTER│
│           │    │           │    │           │    │           │
│ 36 RSS    │    │ Strip HTML│    │ Save to   │    │ TF-IDF → │
│ sources   │    │ Normalize │    │ DB (batch)│    │ Dedup →  │
│ 8 threads │    │ whitespace│    │           │    │ LDA →    │
│           │    │           │    │           │    │ HDBSCAN  │
└──────────┘    └──────────┘    └──────────┘    └─────┬─────┘
                                                      │
                                                      ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 8. SAVE  │◀──│ 7. SUMM. │◀──│ 6. CLASS. │◀──│  5. RANK  │
│          │    │           │    │           │    │           │
│ Save     │    │ TF-IDF   │    │ TF-IDF   │    │ Coverage  │
│ stories  │    │ head-    │    │ sector   │    │ Recency   │
│ to DB    │    │ line +   │    │ classify │    │ Authority │
│          │    │ sum-     │    │ (6 sec-  │    │ Diversity │
│          │    │ mary +   │    │ tors)    │    │           │
│          │    │ context  │    │           │    │           │
└──────────┘    └──────────┘    └──────────┘    └──────────┘

                      │ (parallel)
                      ▼
            ┌─────────────────────┐
            │  9. POST-PIPELINE    │
            │  ┌───────────────┐  │
            │  │ Market Data   │  │
            │  │ (yfinance,    │  │
            │  │ 33 tickers)   │  │
            │  ├───────────────┤  │
            │  │ Briefing      │  │
            │  │ (Markdown)    │  │
            │  └───────────────┘  │
            └─────────────────────┘
```

---

## 7. Database Schema

The database uses SQLAlchemy ORM and supports both SQLite (dev) and PostgreSQL (production).

```
articles
├── id (PK, str, MD5 of URL)
├── title (str)
├── url (str, UNIQUE, indexed)
├── source (str)
├── published_at (str, ISO)
├── content_snippet (str)
├── fetched_at (str, ISO)
├── cluster_id (int, nullable, FK → clusters.id)
└── embedding (str, nullable, JSON, deprecated)

clusters
├── id (PK, int, auto)
└── theme (str)

stories
├── id (PK, int, auto)
├── title (str)
├── summary (str)
├── why_it_matters (str)
├── url (str, nullable)
├── score (float)
├── article_count (int)
├── source (str, comma-separated)
├── published_at (str, ISO)
├── latest_at (str, ISO)
├── created_at (str, ISO)
├── sectors (str, JSON array e.g. '["Tech","Markets"]')
├── sector_summary (str, nullable)
└── trending_score (float, nullable)

market_data
├── id (PK, int, auto)
├── ticker (str, indexed)
├── name (str)
├── price (float)
├── change (float)
├── change_pct (float)
├── market_cap (str, nullable, formatted)
├── sector (str)
└── recorded_at (str, ISO)

briefings
├── id (PK, int, auto)
├── content (str, full Markdown)
└── created_at (str, ISO)

sector_summaries
├── id (PK, int, auto)
├── sector (str, indexed)
├── summary (str)
├── headline_count (int)
└── created_at (str, ISO)

story_reviews
├── id (PK, str, UUID)
├── story_title (str)
├── story_url (str, nullable)
├── correct_section (str, "yes" or "no")
├── suggested_section (str, nullable)
├── summary_concise (str, "yes" or "no")
├── picture_available (str, "yes" or "no")
├── comment (text, nullable)
└── created_at (str, ISO)
```

---

## 8. API Endpoints

### GET /

Health check. No database dependency.

**Response:**
```json
{ "status": "seriously operational" }
```

### GET /news

Top stories, sorted by score descending. Cached for 5 minutes.

**Response:**
```json
{
  "top_stories": [
    {
      "title": "Fed Rate Decision...",
      "summary": "The Federal Reserve...",
      "why_it_matters": "Central bank decisions...",
      "url": "https://...",
      "score": 92.5,
      "article_count": 8,
      "source": ["Reuters", "BBC", "CNBC"],
      "published_at": "2025-04-10T10:00:00",
      "sectors": ["Markets"],
      "sector_summary": null,
      "trending_score": null
    }
  ],
  "count": 1
}
```

### GET /news/stories

All stories (no limit).

### GET /news/sectors

**Response:**
```json
{ "sectors": ["Energy", "Geopolitics", "Markets", "Tech"] }
```

### GET /news/sector/{sector}

Filter by sector (case-insensitive).

**Response:**
```json
{
  "sector": "Tech",
  "stories": [...]
}
```

### GET /news/sector-summaries

**Response:**
```json
{
  "summaries": [
    { "sector": "Tech", "summary": "...", "headline_count": 5, "created_at": "..." }
  ]
}
```

### GET /markets

**Response:**
```json
{
  "all": [{ "ticker": "NVDA", "name": "NVIDIA", "price": 875.32, "change": 12.45, "change_pct": 1.44, "market_cap": "$2.19T", "sector": "Tech" }],
  "gainers": [...],
  "losers": [...],
  "indices": [...]
}
```

### POST /markets/refresh

Rate-limited: 1 request per 60 seconds. Requires `X-API-Key` if `API_KEY` is set.

### GET /briefing

Latest stored briefing.

### POST /briefing/generate

Generates a new briefing. Rate-limited: 1 per 60 seconds. Requires `X-API-Key` if set.

### GET /export/markdown

Downloads raw Markdown briefing file.

### GET /export/json

Downloads JSON export of top stories.

### GET /export/pdf

Downloads PDF briefing document (uses fpdf2).

### GET /sources

Source diversity stats from last 24 hours of articles.

**Response:**
```json
{
  "sources": [
    { "source": "BBC News", "count": 15, "pct": 12.5 }
  ]
}
```

### GET /trending?hours=48

**Response:**
```json
{
  "trending": [
    { "title": "...", "score": 85.3, "article_count": 12, "sectors": ["Geopolitics"], "created_at": "..." }
  ]
}
```

### POST /pipeline/run

Triggers the full pipeline. Rate-limited: 1 per 60 seconds. Requires `X-API-Key` if `API_KEY` is set.

**Response:**
```json
{ "message": "Pipeline started", "status": "accepted" }
```

On rate limit:
```json
{ "detail": "Rate limit exceeded. Try again in X seconds.", "retry_after": X }
```

### POST /news/reviews

Submit a user story review. Public endpoint — does NOT require `X-API-Key` even if `API_KEY` is configured.

**Request body:**
```json
{
  "story_title": "Fed Rate Decision...",
  "story_url": "https://...",
  "correct_section": "no",
  "suggested_section": "Markets",
  "summary_concise": "yes",
  "picture_available": "no",
  "comment": "The image link is broken"
}
```

**Response:**
```json
{ "message": "Review submitted", "review": { ... }, "id": "uuid-string" }
```

### GET /news/reviews

Returns all submitted story reviews (for analysis and fine-tuning).

**Response:**
```json
{
  "reviews": [
    {
      "id": "uuid",
      "story_title": "Fed Rate Decision...",
      "correct_section": "no",
      "suggested_section": "Markets",
      "created_at": "2025-04-10T10:00:00"
    }
  ]
}
```

---

## 9. Deployment Configuration

### Dockerfile (repo root)

Multi-stage build:

1. **Builder stage** (`python:3.11-slim`):
   - Installs gcc/g++ (for hdbscan compilation if no wheel)
   - `pip install --only-binary :all:` with `||` fallback to source build
   
2. **Runtime stage** (`python:3.11-slim`):
   - Copies installed packages from builder
   - Copies `backend/` directory
   - Health check: `python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8001}/')"`
   - Single uvicorn worker: `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}`

### render.yaml

```yaml
services:
  - type: web
    name: news-dashboard-backend
    runtime: image
    region: oregon
    plan: free
    dockerfilePath: ./Dockerfile
    envVars:
      - key: DATABASE_URL     # Required, manual (sync: false)
      - key: API_KEY          # Optional, manual
      - key: CORS_ORIGINS     # Default: https://your-frontend.vercel.app
      - key: LOG_LEVEL        # Default: INFO
    healthCheckPath: /
```

### docker-compose.yml

For local development:
- `postgres` — PostgreSQL 16 Alpine with health check
- `backend` — Builds from repo root Dockerfile, connects to Postgres
- `frontend` — Commented out (run locally with `cd frontend && npm run dev`)

### .dockerignore

Excludes: frontend/, node_modules/, .git/, __pycache__/, .env, *.db, *.log, docker-compose.yml, render.yaml, README.md

### Vercel (frontend)

`vercel.json`: `{ "framework": "nextjs" }`
Env var: `NEXT_PUBLIC_API_URL` set to Render backend URL.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Production | PostgreSQL connection string (Supabase or Render PG) |
| `API_KEY` | Recommended | Auth for POST endpoints |
| `CORS_ORIGINS` | Production | Comma-separated frontend URLs |
| `LOG_LEVEL` | No | DEBUG/INFO/WARNING/ERROR (default: INFO) |
| `PORT` | No | Server port (Render sets this) |
| `NEXT_PUBLIC_API_URL` | Frontend | Backend URL for the frontend API client |

---

## 10. CI/CD

**File:** `.github/workflows/tests.yml`

**Name:** CI
**Triggers:** Push to main, pull request to main

**Jobs:**

| Job | Purpose | Time |
|-----|---------|------|
| `test (core)` | 35 unit + integration tests (no network) | ~2 min |
| `test (smoke)` | 9 real RSS fetch tests | ~30s |
| `lint` | Python syntax check + unused imports | ~1 min |

Key details:
- `fail-fast: false` — core and smoke run independently
- `continue-on-error: true` on smoke tests — feed outages don't block PRs
- `setup-python@v5` with pip caching (`cache-dependency-path: backend/requirements.txt`)
- `--only-binary :all:` with `||` fallback for pip install
- `gcc/g++` installed for hdbscan compilation
- Test results uploaded as artifacts (`actions/upload-artifact@v4`)
- Flake8 F401 check with `continue-on-error: true` (informational only)

---

## 11. Known Issues & Gotchas

1. **Dead import:** The `page.tsx` imports `SectorHeatmap` from `@/components/news/SectorHeatmap` but this component file does not exist in the file tree. This will cause a build error. Either create the component or remove the import.

2. **Duplicate RSS configs:** `config.py` has `RSS_FEEDS` (16 URLs) while `fetch_news.py` has `RSS_SOURCES` (36 named sources). The fetcher uses `RSS_SOURCES`. The `RSS_FEEDS` in config.py may be dead code.



4. **OOM on startup (fixed):** The pipeline no longer runs on startup. Dashboard is empty for up to 6 hours until the scheduler fires. Manual trigger: `POST /pipeline/run`.

5. **Health check DB-independent (fixed):** No longer crashes when DB is unreachable.

6. **Single uvicorn worker:** Render free tier (512MB) can't handle `--workers 2`.

7. **Docker build context:** The Dockerfile is at the repo root, not in `backend/`. All COPY paths use `backend/` prefix. The old `backend/Dockerfile` is deprecated and marked as such.

8. **Supabase sslmode:** The database.py engine logic auto-adds `sslmode=require` for remote Postgres URLs that don't already have it and aren't connecting to localhost.

9. **No migrations:** Tables are created via `Base.metadata.create_all()` on every startup. No Alembic or migration system. Schema changes require manual migration.

10. **`--only-binary :all:`:** The Dockerfile tries pre-compiled wheels first. If a package doesn't have a wheel (unlikely for Linux amd64), it falls back to source compilation which takes 10+ minutes.

11. **Python version in CI:** The CI workflow hardcodes `PYTHON_VERSION: "3.11"` as an env var. If the Dockerfile or requirements change to a different version, the CI must be updated too.

12. **No frontend tests:** The frontend has no test suite. No unit tests, no component tests, no e2e tests.

---

## 12. Development Status & Roadmap

### Current Status ✅
- ✅ Backend: Complete — 8 service modules, 7 database models (Article, Cluster, Summary, MarketData, Briefing, SectorSummary, StoryReview), full API
- ✅ Frontend: Complete — Dashboard + sector pages + market dashboard
- ✅ Core tests: 35 passing (18 unit + 17 integration) — smoke tests: 9 (RSS-dependent)
- ✅ Docker: Multi-stage build, optimized for Render free tier
- ✅ CI/CD: GitHub Actions with core/smoke/lint matrix
- ✅ Deployment: Render (Docker) + Vercel (Next.js)
- ✅ No external ML models — all TF-IDF, deterministic
- ✅ DB-independent health check
- ✅ Rate limiting on write endpoints

### In Progress 🔄
- 🔄 Render deployment — debugging build/runtime issues

### Planned 📋
- 📋 Create `SectorHeatmap` component referenced in `page.tsx`
- 📋 Add frontend tests (Vitest + Testing Library)
- 📋 Better ranking algorithms
- 📋 LLM-powered summaries (optional, future)
- 📋 Personalization
- 📋 India-specific relevance layer
- 📋 Alembic for database migrations
- 📋 Remove dead code (config.py RSS_FEEDS, backend/Dockerfile)

---

*Generated for AI agents. Last updated April 2025.*
