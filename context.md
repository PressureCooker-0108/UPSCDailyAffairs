# Serious Operator News Dashboard — Complete Project Context

## 1. Project Identity

**Name:** Serious Operator News Dashboard
**Purpose:** High-signal global news aggregation, clustering, ranking, and briefing for founders, investors, and analysts.
**Philosophy:** Less is more. Top 5-10 stories max. No clickbait. No fluff. Signal over noise.
**Stack:** Python/FastAPI (backend) + Next.js 16/React 19 (frontend) + PostgreSQL (database)

## 2. Architecture Overview

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  16+ RSS    │ ──▶ │  Backend API     │ ──▶ │  Next.js     │
│  Sources    │     │  FastAPI +       │     │  Frontend    │
│             │     │  PostgreSQL      │     │  (Vercel)    │
└─────────────┘     └──────────────────┘     └──────────────┘
                          │
                          ▼
                    ┌──────────────────┐
                    │  Pipeline (6h)   │
                    │  Fetch → Clean   │
                    │  → Cluster →     │
                    │  Rank → Summarize│
                    │  → Briefing      │
                    └──────────────────┘
```

## 3. Backend — Full File Map

```
backend/
├── main.py                # FastAPI app, endpoints, middleware, rate limiter
├── config.py              # RSS feed URLs, pipeline constants, topic templates
├── scheduler.py           # APScheduler (6h interval), pipeline orchestration
├── migrate_to_postgres.py # SQLite → PostgreSQL migration script (one-time)
├── start.sh               # Startup script for Render
├── requirements.txt       # Python dependencies
├── pyproject.toml         # Pytest configuration
├── Procfile               # Render Process file (cd backend && uvicorn main:app)
├── Dockerfile             # Docker build (multi-stage, slim)
├── models/
│   ├── database.py        # SQLAlchemy engine, session, all CRUD functions
│   └── models.py          # SQLAlchemy ORM models (Article, Cluster, Summary, MarketData, Briefing, SectorSummary, StoryReview)
├── services/
│   ├── fetch_news.py      # Parallel RSS feed fetching (ThreadPoolExecutor, 8 workers)
│   ├── clean_news.py      # HTML stripping, whitespace normalization
│   ├── cluster_news.py    # TF-IDF dedup + LDA topic extraction + HDBSCAN clustering
│   ├── classify_news.py   # TF-IDF cosine similarity against sector descriptions
│   ├── rank_news.py       # Weighted scoring: coverage(50%) + recency(30%) + authority(10%) + diversity(10%)
│   ├── summarize_news.py  # TF-IDF centroid headline picking + extractive summary + topic templates
│   ├── market_data.py     # yfinance parallel fetcher for WATCHLIST tickers
│   ├── briefing.py        # Executive markdown briefing generator
│   └── pdf_briefing.py    # FPDF-based PDF briefing generator (custom BriefingPDF class)
└── tests/
    ├── conftest.py        # Pytest fixtures (sample_articles, app, client)
    ├── test_api.py        # Integration tests for all endpoints
    ├── test_classify.py   # Sector classification unit tests
    ├── test_pipeline.py   # Pipeline smoke tests (skipped by default, real HTTP)
    └── __init__.py
```

### 3a. Pipeline Data Flow (scheduler.py → `run_pipeline()`)

1. **Phase 1 (Sequential):**
   - `fetch_rss_feeds()` → 16+ RSS sources in parallel (ThreadPoolExecutor)
   - `clean_articles()` → strip HTML, normalize whitespace
   - `save_articles()` → persist to DB
   - `cluster_articles()` → TF-IDF dedup → LDA topics → HDBSCAN clustering
   - `rank_clusters()` → score by coverage × recency × authority × diversity
   - `classify_sectors()` → TF-IDF vs sector descriptions
   - `summarize_stories()` → centroid headlines + extractive summaries + "why it matters"
   - `save_stories()` → persist to DB

2. **Phase 2 (Parallel — ThreadPoolExecutor):**
   - `fetch_and_store_market_data()` → yfinance for WATCHLIST tickers
   - `generate_briefing()` → executive markdown briefing

### 3b. Key Design Decisions (Backend)

| Decision | Rationale |
|----------|-----------|
| **TF-IDF instead of sentence-transformers** | No model downloads, instant startup, works in 512MB RAM. 1.5GB+ saved from removing torch/transformers. |
| **HDBSCAN for clustering** | Doesn't require specifying cluster count; labels noise as -1 (handled as individual stories) |
| **LDA topic modeling** | 5 topics extracted from TF-IDF features, one-hot encoded into clustering input |
| **ALoguru logging** | Structured JSON output (LOG_FORMAT=json) for Datadog/CloudWatch; rotating file for local debug |
| **Rate limiter** | In-memory, thread-safe, per-action cooldowns. No Redis dependency. |
| **sslmode=require logic** | Auto-detects localhost, SQLite, and Render internal PostgreSQL (dpg-* hosts) to skip SSL where not needed |
| **Single uvicorn worker** | Render free tier has 512MB RAM; --workers 2 causes OOM |

### 3c. API Endpoints

| Method | Path | Rate Limited | Description |
|--------|------|-------------|-------------|
| GET | `/` | No | Health check (no DB dependency — always returns 200) |
| GET | `/news` | No | Top stories, cached 5 min. Supports `?force_refresh=true` |
| GET | `/news/stories` | No | All raw stories. `?limit=N` (1-100) |
| GET | `/news/sectors` | No | Active sectors with story counts |
| GET | `/news/sector/{sector}` | No | Stories by sector. `?limit=N` (1-50) |
| GET | `/news/sector-summaries` | No | Per-sector AI summaries |
| GET | `/markets` | No | Market data (indices, gainers, losers) |
| POST | `/markets/refresh` | 60s | Refresh market data |
| GET | `/briefing` | No | Latest executive briefing |
| POST | `/briefing/generate` | 60s | Generate new briefing |
| GET | `/export/markdown` | No | Download markdown briefing |
| GET | `/export/json` | No | Download JSON export |
| GET | `/export/pdf` | No | Download PDF briefing |
| GET | `/sources` | No | Source diversity stats |
| GET | `/trending` | No | Trending topics. `?hours=N` (1-168) |
| POST | `/news/reviews` | No | Submit a story review (public, no API key required) |
| GET | `/news/reviews` | No | Get all submitted story reviews |
| POST | `/pipeline/run` | 600s | Trigger full pipeline. Requires `X-API-Key` if `API_KEY` is set. |

### 3d. Middleware

1. **CORS** — Configurable via `CORS_ORIGINS` env var (default: `*`)
2. **Security Headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`
3. **API Key Auth** — If `API_KEY` env var is set, all POST endpoints require `X-API-Key` header

## 4. Database Models (SQLAlchemy)

### Article (`articles`)
| Column | Type | Notes |
|--------|------|-------|
| id | String, PK | MD5 hash of article URL |
| title | Text | |
| url | Text, unique | |
| source | String | |
| published_at | String | ISO-8601 timestamp |
| content_snippet | Text | Cleaned text |
| fetched_at | String | ISO-8601 timestamp |
| cluster_id | String, nullable | FK to clusters |

### Summary / Story (`stories`)
| Column | Type | Notes |
|--------|------|-------|
| id | Integer, PK, autoincrement | |
| title | Text | Best headline from cluster |
| summary | Text | Extractive 3-sentence summary |
| why_it_matters | Text | Topic-based template |
| url | String, nullable | Best article URL |
| score | Float | Composite ranking score |
| article_count | Integer | Number of clustered articles |
| source | String | Comma-separated source names |
| published_at | String | Earliest timestamp |
| latest_at | String | Latest timestamp |
| created_at | String | Pipeline run timestamp |
| sectors | String | JSON array, e.g. `["Markets","Tech"]` |
| sector_summary | Text, nullable | Per-sector AI analysis |
| trending_score | Float, nullable | Trending momentum |

### MarketData (`market_data`)
| Column | Type |
|--------|------|
| id | Integer, PK |
| ticker | String |
| name | String |
| price | Float |
| change | Float |
| change_pct | Float |
| market_cap | Float, nullable |
| sector | String |
| recorded_at | String |

### Briefing (`briefings`)
| Column | Type |
|--------|------|
| id | Integer, PK |
| content | Text (markdown) |
| created_at | String |

### SectorSummary (`sector_summaries`)
| Column | Type |
|--------|------|
| id | Integer, PK |
| sector | String, unique |
| summary | Text |
| headline_count | Integer |
| created_at | String |

### StoryReview (`story_reviews`)
| Column | Type | Notes |
|--------|------|-------|
| id | String, PK | UUID |
| story_title | String | |
| story_url | String, nullable | |
| correct_section | String | "yes" or "no" |
| suggested_section | String, nullable | Sector user suggested |
| summary_concise | String | "yes" or "no" |
| picture_available | String | "yes" or "no" |
| comment | Text, nullable | Free-text feedback |
| created_at | String | ISO-8601 timestamp |

## 5. RSS Feed Sources (16)

**Global News:** BBC (3 feeds), Al Jazeera, NPR, NYT (2 feeds), The Guardian, Washington Post, Reuters
**Business:** CNBC (2 feeds), MarketWatch, Investing.com
**Tech:** TechCrunch, Hacker News, Wired, Ars Technica, The Verge
**Energy:** OilPrice, Energy Voice
**India:** The Hindu, NDTV, Times of India, Indian Express, Business Standard, Moneycontrol
**Sports:** BBC Sport, ESPN, Sky Sports, The Guardian Sport, CBS Sports, Yahoo Sports, Sports Illustrated, Reuters Sports, NYT Sports, Fox Sports

## 6. Sectors (Classification)

- **Markets** — stocks, bonds, forex, crypto, IPOs, Fed, rates, inflation, GDP, trade
- **Tech** — AI, SaaS, hardware, cybersecurity, startups, big tech, regulation
- **Geopolitics** — conflict, sanctions, diplomacy, elections, policy, security
- **Energy** — oil, gas, renewables, OPEC, climate, grid, nuclear
- **India** — Indian economy, markets, politics, policy, tech
- **Sports** — football, cricket, basketball, tennis, Olympics, leagues, transfers
- **General** — Fallback for unclassified stories

## 7. Frontend — Full File Map

```
frontend/
├── app/
│   ├── layout.tsx          # Root layout: Geist fonts, ThemeProvider, ErrorBoundary, Toaster
│   ├── page.tsx            # Main dashboard: BigStory, MarketDashboard, SectorHeatmap, TopStories, SectorSection
│   ├── globals.css         # Tailwind CSS v4 imports and custom styles
│   └── sectors/
│       └── [sector]/
│           └── page.tsx    # Dynamic sector page with hero, story grid, source landscape
├── components/
│   ├── header.tsx           # Sticky header: logo, refresh, theme toggle, export buttons
│   ├── theme-provider.tsx   # next-themes provider wrapper
│   ├── error-boundary.tsx   # React error boundary with retry and dev-mode stack trace
│   ├── markets/
│   │   └── MarketDashboard.tsx  # Indices grid, gainers/losers lists, Recharts bar chart
│   └── news/
│       ├── BigStory.tsx     # Hero story: large headline, summary, "Why it matters"
│       ├── TopStories.tsx   # Bento-grid layout for top 6 stories
│       ├── SectorSection.tsx # Sector card grid with icons, headlines, counts
│       ├── SectorHeatmap.tsx # Score-based heatmap with proportional sizing, sparklines│   ├── StoryCard.tsx    # News card with Dialog modal for details
│   ├── StoryReview.tsx  # Collapsible review form (section, summary, image feedback)
│   └── ui/                  # shadcn/ui components (70+ files: button, card, dialog, badge, etc.)
├── lib/
│   ├── api.ts              # API client: fetchStories, fetchMarketData, fetchBriefing, exports
│   └── utils.ts            # Tailwind class merging utility (cn())
├── types/
│   └── story.ts            # TypeScript interfaces: Story, MarketDataPoint, SectorSummary, SourceDiversity, Briefing
├── hooks/
│   ├── use-toast.ts        # shadcn/ui toast hook
│   └── use-mobile.ts       # Mobile detection hook
├── package.json            # Dependencies: next 16, react 19, recharts, lucide-react, shadcn/ui
├── next.config.ts          # Next.js config (default, no custom options)
├── vercel.json             # { "framework": "nextjs" }
├── tsconfig.json           # TypeScript config
├── eslint.config.mjs       # ESLint flat config
├── postcss.config.mjs      # PostCSS with Tailwind CSS v4
└── Dockerfile              # Frontend Dockerfile (multi-stage, Next.js standalone output)
```

### 7a. Frontend Component Architecture

```
RootLayout (layout.tsx)
├── ThemeProvider
│   ├── ErrorBoundary
│   │   └── Page Content (page.tsx)
│   │       ├── Header (header.tsx) — sticky, refresh/theme/export controls
│   │       ├── Trending Topics Bar — scrolling top stories
│   │       ├── BigStory — featured story (highest scored)
│   │       ├── MarketDashboard — indices, bar chart, gainers/losers
│   │       ├── SectorHeatmap — score-colored sector tiles with sparklines
│   │       ├── SectorSection — sector cards → links to /sectors/[sector]
│   │       ├── TopStories — bento-grid of StoryCards
│   │       ├── StoryCard → StoryReview — review form in story dialog
│   │       └── Export Footer — Markdown/JSON/PDF download buttons
│   └── Toaster (sonner)
└── Dynamic Routes
    └── /sectors/[sector] — hero, story grid, source landscape
```

## 8. Deployment

### Production (Render — Python Native Runtime)

| Config | Value |
|--------|-------|
| Runtime | Python (native, not Docker) |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Root Procfile | `web: cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Database | Render PostgreSQL (free tier, 1GB RAM, 1GB storage) — Internal connection URL |
| Port | Set via $PORT env var |
| Python Version | 3.11.11 (runtime.txt) |

**Important Deployment Notes:**
- Render's free tier instances have 512MB RAM — single uvicorn worker only
- The root `requirements.txt` and `backend/requirements.txt` must be kept in sync
- The root `Procfile` is required because Render's auto-detection ignores `render.yaml` settings for manually-created services
- Render's Python native runtime auto-detects `runtime.txt` at repo root for Python version
- Render PostgreSQL internal URLs start with `dpg-`. They don't need `sslmode=require` since connections stay within Render's network.

### Local Development

```bash
# Docker (full stack):
docker compose up -d
# This starts PostgreSQL + backend. Frontend runs separately.

# Without Docker (SQLite fallback):
cd backend
pip install -r requirements.txt
uvicorn main:app --port 8001

# Frontend:
cd frontend
npm install
npm run dev  # → localhost:3000

# Run the pipeline:
curl -X POST http://localhost:8001/pipeline/run

# Run tests:
cd backend && python -m pytest tests/ -v -m "not smoke"
```

### Docker

- **Dockerfile** at repo root (multi-stage: `python:3.11-slim`). Verifies Render's `--only-binary :all:` optimization for hdbscan (no native compilation). Uses single uvicorn worker.
- **docker-compose.yml** at repo root. Starts `postgres:16-alpine` + backend. Frontend container is commented out (run separately for faster dev).
- Dev DB: `postgresql://newsdash:newsdash_dev_password@postgres:5432/newsdash?sslmode=disable`

### Vercel (Frontend)

- Framework preset: Next.js
- Config: `{ "framework": "nextjs" }` in `vercel.json`
- Requires `NEXT_PUBLIC_API_URL` env var set to backend URL

## 9. Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `DATABASE_URL` | For prod | `sqlite:///news.db` | PostgreSQL connection string |
| `API_KEY` | Recommended | None | Auth for POST endpoints |
| `CORS_ORIGINS` | For prod | `*` | Frontend URL for CORS |
| `LOG_LEVEL` | No | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `LOG_FORMAT` | No | `text` | `text` or `json` |
| `PORT` | Render sets | `8001` | Server port |
| `_TESTING` | No | None | Set `=1` to skip scheduler in tests |
| `NEXT_PUBLIC_API_URL` | Frontend | `http://127.0.0.1:8001` | Backend URL for frontend |

## 10. Key Code Patterns and Conventions

### Import Pattern (avoid circular imports)
Models are imported inside function bodies, not at module top level, to avoid circular imports between `database.py` and `models.py`.

### Session Management
- `get_db()` — generator for FastAPI dependency injection
- All CRUD functions create their own session if none provided
- Batch operations accept optional `db` parameter for transaction grouping
- Always: try → commit → except rollback → finally close

### Rate Limiting
- `RateLimiter` class uses `time.monotonic()` + locks
- Per-action cooldowns stored in dict
- Returns `retry_after` seconds in 429 responses

### Caching
- News endpoint: in-memory dict with 300s TTL
- Sector classification: in-memory dict (keyed by input text)
- No Redis dependency (limited to Render's 512MB)

## 11. Testing

### Backend Tests
```bash
cd backend && python -m pytest tests/ -v -m "not smoke"
```
- 35 unit/integration tests, 10 smoke tests skipped (real HTTP)
- Test classes: TestNewsEndpoint, TestHealthEndpoint, TestSourcesEndpoint, TestTrendingEndpoint, TestMarketsEndpoint, TestSectorSummariesEndpoint, TestBriefingEndpoint, TestExportEndpoints
- 30 sector classification tests: TestClassifySectors
- Uses SQLite test database (`test_news.db`)
- Pytest fixtures: `sample_articles()`, `app()`, `client(app)`, `clear_classify_cache()`

### Frontend
- No tests yet (zero test files)

## 12. Production Readiness Status (Known Gaps)

| Area | Status | Notes |
|------|--------|-------|
| ✅ Database | Done | Render PostgreSQL (internal), working |
| ✅ Deploy Backend | Done | Render native Python runtime |
| ✅ Deploy Frontend | Done | Vercel |
| ✅ Logging | Done | Loguru structured logging |
| ✅ Rate Limiting | Done | In-memory, thread-safe |
| ✅ Pipelines | Done | APScheduler 6h interval |
| ✅ Security Headers | Done | HSTS, XSS, Clickjacking protection |
| ✅ Error Boundary | Done | Frontend error boundary |
| ✅ ML Bloat Removed | Done | No sentence-transformers/torch |
| ✅ Story Reviews | Done | Public POST endpoint + frontend form |
| ✅ CI/CD | Done | GitHub Actions (test matrix) |
| ❌ Sentry | Missing | No error tracking in production |
| ❌ Alembic | Missing | Uses `create_all()` on startup |
| ❌ Frontend Tests | Missing | No Playwright/Vitest |
| ❌ Database Backups | Missing | No automated pg_dump |
| ❌ CSP Header | Missing | Content-Security-Policy not set |
| ❌ Prometheus Metrics | Missing | No request/error metrics |

## 13. Recent Changes (Commit History)

- `e71a7a9` — Switch to Render PostgreSQL: update connection logic and env template
- `927b741` — Fix Render deploy: clean deps, root Procfile, security headers, error boundary
- `09cc9bf` — Fix Render deploy: Python 3.11 native runtime, clean deps, correct start command
- `ba02afa` — Render deployment fix
- `9edb615` — Phase 2 + Deployment fixes
- `b1b5df0` — Phase 1
- `bf74444` — Limiting + heatmap added

## 14. Key Dependencies

### Backend (Python)
fastapi, uvicorn, sqlalchemy, psycopg2-binary, feedparser, numpy, apscheduler, python-dateutil, httpx, hdbscan, scikit-learn, yfinance, fpdf2, loguru

### Frontend (JavaScript/TypeScript)
next 16, react 19, recharts, lucide-react, next-themes, sonner, class-variance-authority, tailwindcss 4, shadcn/ui (radix primitives), date-fns, zod

## 15. Quick Reference Commands

```bash
# Backend
cd backend && uvicorn main:app --port 8001 --reload
cd backend && python -m pytest tests/ -v -m "not smoke"
cd backend && python -m pytest tests/test_classify.py -v

# Frontend
cd frontend && npm run dev
cd frontend && npx next build

# Pipeline
curl -X POST http://localhost:8001/pipeline/run
curl -X POST http://localhost:8001/markets/refresh
curl -X POST http://localhost:8001/briefing/generate

# Health
curl http://localhost:8001/

# Docker
docker compose up -d
docker compose logs -f
docker compose down

# Git (avoid nul file on Windows — add files individually)
git add <specific files> && git commit -m "msg" && git push
```

## 16. Windows-Specific Notes

- Git operations fail with `git add -A` due to a `nul` reserved device artifact
- Always use `git add <file1> <file2> ...` with explicit file paths
- The project lives at `C:\Users\Adity\OneDrive\Desktop\Projects\news-dashboard`
- Python 3.14 installed locally (but deployment uses 3.11 via runtime.txt)
- Line endings: LF → CRLF warnings on git add are normal on Windows
