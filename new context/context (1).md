# Serious Operator News Dashboard — Complete Project Context

## 1. Project Identity

**Name:** Serious Operator News Dashboard
**Current Purpose:** High-signal global news aggregation, clustering, ranking, and briefing for founders, investors, and analysts.
**Active Extension:** UPSC Current Affairs MVP — an exam-intelligence layer on top of the existing pipeline. Every news story relevant to India gets processed into an "exam playbook" (Prelims angle, Mains angle, probable question, static connect, key terms) using the Gemini API. This is served via a new `/upsc` API endpoint and a new `/upsc-dashboard` frontend page.
**Philosophy:** Less is more. Top 5-10 stories max. No clickbait. No fluff. Signal over noise.
**Stack:** Python/FastAPI (backend) + Next.js 16/React 19 (frontend) + PostgreSQL (database)

---

## 2. Architecture Overview

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  16+ RSS    │ ──▶ │  Backend API     │ ──▶ │  Next.js     │
│  Sources    │     │  FastAPI +       │     │  Frontend    │
│  (incl.     │     │  PostgreSQL      │     │  (Vercel)    │
│  Indian     │     │                  │     │              │
│  feeds)     │     └──────────────────┘     └──────────────┘
└─────────────┘           │
                          ▼
                    ┌──────────────────┐
                    │  Pipeline (6h)   │
                    │  Fetch → Clean   │
                    │  → Cluster →     │
                    │  Rank → Summarize│
                    │  → Exam Playbook │  ← NEW (Gemini API)
                    │  → Briefing      │
                    └──────────────────┘
```

---

## 3. Backend — Full File Map

```
backend/
├── main.py                  # FastAPI app, endpoints, middleware, rate limiter
├── config.py                # RSS feed URLs, pipeline constants, Gemini key
├── scheduler.py             # APScheduler (6h interval), pipeline orchestration
├── upsc_analyzer.py         # NEW — Gemini API caller, exam playbook generator
├── upsc_syllabus.json       # NEW — structured UPSC syllabus schema (prompt context)
├── migrate_to_postgres.py   # SQLite → PostgreSQL migration script (one-time)
├── start.sh                 # Startup script for Render
├── requirements.txt         # Python dependencies (add: httpx, google-generativeai)
├── pyproject.toml           # Pytest configuration
├── Procfile                 # Render Process file
├── Dockerfile               # Docker build (multi-stage, slim)
├── models/
│   ├── database.py          # SQLAlchemy engine, session, CRUD (stories table has exam_playbook column)
│   └── models.py            # ORM models (Summary/Story model has exam_playbook field)
├── services/
│   ├── fetch_news.py        # Parallel RSS feed fetching (ThreadPoolExecutor, 8 workers)
│   ├── clean_news.py        # HTML stripping, whitespace normalization
│   ├── cluster_news.py      # TF-IDF dedup + LDA topic extraction + HDBSCAN clustering
│   ├── classify_news.py     # TF-IDF cosine similarity against sector descriptions
│   ├── rank_news.py         # Weighted scoring: coverage(50%) + recency(30%) + authority(10%) + diversity(10%)
│   ├── summarize_news.py    # Existing summarizer — also calls upsc_analyzer after summary
│   ├── market_data.py       # yfinance parallel fetcher for WATCHLIST tickers
│   ├── briefing.py          # Executive markdown briefing generator
│   └── pdf_briefing.py      # FPDF-based PDF briefing generator
└── tests/
    ├── conftest.py
    ├── test_api.py
    ├── test_classify.py
    ├── test_pipeline.py
    └── __init__.py
```

### 3a. Pipeline Data Flow (Updated)

1. **Phase 1 (Sequential):**
   - `fetch_rss_feeds()` → 16+ RSS sources including Indian feeds
   - `clean_articles()` → strip HTML, normalize whitespace
   - `save_articles()` → persist to DB
   - `cluster_articles()` → TF-IDF dedup → LDA topics → HDBSCAN clustering
   - `rank_clusters()` → score by coverage × recency × authority × diversity
   - `classify_sectors()` → TF-IDF vs sector descriptions
   - `summarize_stories()` → centroid headlines + extractive summaries + "why it matters"
   - `generate_exam_playbooks()` → **NEW** — for each story, call upsc_analyzer.py → Gemini API → store exam_playbook JSON
   - `save_stories()` → persist to DB (including exam_playbook field)

2. **Phase 2 (Parallel — ThreadPoolExecutor):**
   - `fetch_and_store_market_data()` → yfinance
   - `generate_briefing()` → executive markdown briefing

### 3b. Key Design Decisions

| Decision | Rationale |
|---|---|
| TF-IDF instead of sentence-transformers | No model downloads, instant startup, works in 512MB RAM |
| HDBSCAN for clustering | Doesn't require specifying cluster count; labels noise as -1 |
| Gemini 2.0 Flash for exam playbooks | Free tier (1500 req/day), no card required, fast |
| Indian keyword filter before Gemini call | Avoids wasting API quota on non-India stories |
| exam_playbook stored as JSON TEXT column | Avoids schema complexity; parsed at query time |
| Separate /upsc endpoint | Doesn't break existing /news endpoint or any existing consumers |

### 3c. API Endpoints (Full List Including New)

| Method | Path | Rate Limited | Description |
|---|---|---|---|
| GET | `/` | No | Health check |
| GET | `/news` | No | Top stories, cached 5 min |
| GET | `/news/stories` | No | All raw stories |
| GET | `/news/sectors` | No | Active sectors with story counts |
| GET | `/news/sector/{sector}` | No | Stories by sector |
| GET | `/news/sector-summaries` | No | Per-sector AI summaries |
| GET | `/markets` | No | Market data |
| POST | `/markets/refresh` | 60s | Refresh market data |
| GET | `/briefing` | No | Latest executive briefing |
| POST | `/briefing/generate` | 60s | Generate new briefing |
| GET | `/export/markdown` | No | Download markdown briefing |
| GET | `/export/json` | No | Download JSON export |
| GET | `/export/pdf` | No | Download PDF briefing |
| GET | `/sources` | No | Source diversity stats |
| GET | `/trending` | No | Trending topics |
| POST | `/news/reviews` | No | Submit story review |
| GET | `/news/reviews` | No | Get all story reviews |
| POST | `/pipeline/run` | 600s | Trigger full pipeline (requires X-API-Key) |
| GET | `/upsc` | No | **NEW** — UPSC stories with exam playbooks |
| GET | `/upsc-dashboard` | No | **NEW** — Serves static/upsc.html |
| POST | `/pipeline/refresh` | 60s | **NEW** — Manual pipeline trigger for dev/testing |

---

## 4. Database Models

### Summary / Story (`stories`) — Updated

| Column | Type | Notes |
|---|---|---|
| id | Integer, PK, autoincrement | |
| title | Text | Best headline from cluster |
| summary | Text | Extractive 3-sentence summary |
| why_it_matters | Text | Topic-based template |
| url | String, nullable | Best article URL |
| score | Float | Composite ranking score |
| article_count | Integer | |
| source | String | Comma-separated source names |
| published_at | String | Earliest timestamp |
| latest_at | String | Latest timestamp |
| created_at | String | Pipeline run timestamp |
| sectors | String | JSON array |
| sector_summary | Text, nullable | |
| trending_score | Float, nullable | |
| **exam_playbook** | **Text, nullable** | **NEW — JSON string from Gemini** |

### exam_playbook JSON structure (stored as TEXT)

```json
{
  "is_relevant": true,
  "gs_papers": ["GS2", "GS3"],
  "prelims_angle": "What MCQ or factual question could be asked...",
  "mains_angle": "Which GS paper and what analytical question...",
  "probable_question": "Examine the role of...",
  "static_connect": "Connects to Chapter X of NCERT Polity / Laxmikant...",
  "key_terms": ["term1", "term2", "term3"],
  "one_line_takeaway": "The single most exam-relevant fact in one line."
}
```

All other models (Article, MarketData, Briefing, SectorSummary, StoryReview) are unchanged.

---

## 5. RSS Feed Sources

**Global:** BBC (3 feeds), Al Jazeera, NPR, NYT (2 feeds), The Guardian, Washington Post, Reuters
**Business:** CNBC (2 feeds), MarketWatch, Investing.com
**Tech:** TechCrunch, Hacker News, Wired, Ars Technica, The Verge
**Energy:** OilPrice, Energy Voice
**India (existing):** The Hindu, NDTV, Times of India, Indian Express, Business Standard, Moneycontrol
**India (new additions for UPSC):**
- PIB: `https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3`
- Down to Earth: `https://www.downtoearth.org.in/rss/latest`
- Livemint: `https://www.livemint.com/rss/news`
**Sports:** BBC Sport, ESPN, Sky Sports, etc.

---

## 6. UPSC Exam Context (for AI Prompt Construction)

The UPSC Civil Services Examination has 3 stages:

**Prelims** — Screening only. 2 papers: GS Paper 1 (100 MCQs, 200 marks, -1/3 negative marking) + CSAT Paper 2 (80 MCQs, qualifying at 33%). Prelims marks do NOT count toward final rank.

**Mains** — 9 papers, 7 count for merit (1750 marks total):
- Essay (250) — write on any topic, tests clarity and structure
- GS1 (250) — History, Culture, Geography, Indian Society
- GS2 (250) — Polity, Governance, IR, Social Justice
- GS3 (250) — Economy, Science & Tech, Environment, Internal Security
- GS4 (250) — Ethics, Integrity, Aptitude, Case Studies
- Optional I + II (250 each) — candidate's chosen subject
- 2 language papers — qualifying only, don't count

**Interview** — 275 marks. Final rank = Mains (1750) + Interview (275) = max 2025.

**High-frequency UPSC current affairs topics (news maps to these most often):**
RBI monetary policy, Budget/GST, India-China/India-Pakistan relations, Climate change/COP/NDCs, ISRO missions, SC judgements, Parliament bills, Social welfare schemes, Agriculture (MSP, food security), Internal security (naxalism, J&K), International organisations (UN, G20, BRICS, SCO), Science & tech (AI, semiconductors, defence), Health (NHM, outbreaks), Environment (biodiversity, wetlands), Governance (RTI, CAG reports), Ethics (scams, governance failures), Women/child welfare, Tribal rights.

**The full syllabus is in `upsc_syllabus.json`** — this file is the primary prompt context for Gemini.

---

## 7. New File: upsc_analyzer.py

Location: `backend/upsc_analyzer.py`

**Purpose:** Takes a story's headline, summary, and why_it_matters. Does a quick India-relevance keyword check. If relevant, calls Gemini 2.0 Flash API with the syllabus as context. Returns a structured exam playbook dict or None.

**Key functions:**
- `is_upsc_relevant(headline, summary) → bool` — keyword filter to avoid wasting Gemini quota
- `generate_exam_playbook(headline, summary, why_it_matters) → dict | None` — main Gemini call

**Gemini model:** `gemini-2.0-flash` via REST API (`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent`)

**API key:** Read from `os.environ.get("GEMINI_API_KEY")` — never hardcoded.

**Rate limit awareness:** Free tier = 15 req/min, 1500/day. Pipeline runs ~10 stories every 6h = ~40 calls/day. Well within limits.

---

## 8. New File: static/upsc.html

Location: `backend/static/upsc.html`

A standalone HTML/CSS/JS page (no frameworks, no build step) served by FastAPI's StaticFiles. Fetches from `/upsc` on load and renders exam playbook cards.

**Card structure:**
- Headline (large, bold)
- GS paper badges (color-coded: GS1=green, GS2=blue, GS3=orange, GS4=purple)
- One-line takeaway (highlighted callout box)
- Collapsible sections: Prelims Angle | Mains Angle | Probable Question | Static Connect | Key Terms
- Source names + timestamp
- "Not relevant" graceful fallback for stories without playbooks

**Design:** Dark navy background, white text, mobile responsive. No external JS dependencies.

---

## 9. Deployment

### Backend (Render — Python Native Runtime)

| Config | Value |
|---|---|
| Runtime | Python (native, not Docker) |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Database | Render PostgreSQL (internal connection URL) |

### Environment Variables (Full List)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | For prod | `sqlite:///news.db` | PostgreSQL connection string |
| `API_KEY` | Recommended | None | Auth for POST endpoints |
| `CORS_ORIGINS` | For prod | `*` | Frontend URL for CORS |
| `LOG_LEVEL` | No | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `LOG_FORMAT` | No | `text` | `text` or `json` |
| `PORT` | Render sets | `8001` | Server port |
| `_TESTING` | No | None | Set =1 to skip scheduler in tests |
| `NEXT_PUBLIC_API_URL` | Frontend | `http://127.0.0.1:8001` | Backend URL for frontend |
| `GEMINI_API_KEY` | **NEW** | None | Gemini API key (from Google AI Studio) |

### Frontend (Vercel)

- Framework: Next.js
- Requires `NEXT_PUBLIC_API_URL` env var
- The UPSC dashboard (`/upsc-dashboard`) is served from FastAPI directly — not part of Next.js

---

## 10. Key Code Patterns and Conventions

**Import pattern:** Models are imported inside function bodies, not at module top level, to avoid circular imports between `database.py` and `models.py`.

**Session management:** `get_db()` generator for FastAPI DI. All CRUD functions create their own session if none provided. Always: try → commit → except rollback → finally close.

**Rate limiting:** `RateLimiter` class uses `time.monotonic()` + locks. Per-action cooldowns stored in dict.

**Caching:** News endpoint: in-memory dict with 300s TTL. No Redis dependency.

**Error handling in upsc_analyzer:** All Gemini API calls are wrapped in try/except. Returns None on any failure — the pipeline continues without the playbook rather than failing entirely.

---

## 11. Production Readiness Status

| Area | Status | Notes |
|---|---|---|
| ✅ Database | Done | Render PostgreSQL (internal), working |
| ✅ Deploy Backend | Done | Render native Python runtime |
| ✅ Deploy Frontend | Done | Vercel |
| ✅ Logging | Done | Loguru structured logging |
| ✅ Rate Limiting | Done | In-memory, thread-safe |
| ✅ Pipelines | Done | APScheduler 6h interval |
| ✅ Security Headers | Done | HSTS, XSS, Clickjacking protection |
| ✅ Error Boundary | Done | Frontend error boundary |
| ✅ CI/CD | Done | GitHub Actions |
| ✅ Story Reviews | Done | Public POST endpoint + frontend form |
| 🔄 UPSC Extension | In progress | exam_playbook column + analyzer + new endpoints |
| ❌ Sentry | Missing | No error tracking in production |
| ❌ Alembic | Missing | Uses create_all() on startup |
| ❌ Frontend Tests | Missing | No Playwright/Vitest |
| ❌ Database Backups | Missing | No automated pg_dump |

---

## 12. Windows-Specific Notes

- Git `add -A` fails due to `nul` reserved device artifact → always use `git add <file1> <file2> ...`
- Project path: `C:\Users\Adity\OneDrive\Desktop\Projects\news-dashboard`
- Python 3.14 installed locally (deployment uses 3.11 via runtime.txt)
- Line endings: LF → CRLF warnings on git add are normal

---

## 13. Quick Reference Commands

```bash
# Backend
cd backend && uvicorn main:app --port 8001 --reload

# Test UPSC endpoint after pipeline runs
curl http://localhost:8001/upsc

# Trigger pipeline manually (for dev)
curl -X POST http://localhost:8001/pipeline/run

# Frontend
cd frontend && npm run dev

# Docker
docker compose up -d
docker compose logs -f

# Git (Windows — always explicit files)
git add backend/upsc_analyzer.py backend/main.py backend/models/models.py backend/services/summarize_news.py backend/static/upsc.html backend/upsc_syllabus.json backend/config.py backend/requirements.txt context.md
git commit -m "feat: UPSC exam intelligence layer MVP"
git push
```

---

## 14. Key Dependencies

### Backend (Python)
fastapi, uvicorn, sqlalchemy, psycopg2-binary, feedparser, numpy, apscheduler, python-dateutil, httpx, hdbscan, scikit-learn, yfinance, fpdf2, loguru, **google-generativeai** (new)

### Frontend (JavaScript/TypeScript)
next 16, react 19, recharts, lucide-react, next-themes, sonner, class-variance-authority, tailwindcss 4, shadcn/ui, date-fns, zod
