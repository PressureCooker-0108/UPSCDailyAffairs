# UPSC Daily Affairs

AI-powered current affairs aggregation for UPSC Civil Services Examination preparation. Every news story is classified by GS paper, scored for exam relevance, and analyzed for Prelims/Mains angles.

## Philosophy

This is not a general news dashboard. It's an **exam-intelligence tool** that answers:

- What current affairs topics are most relevant for UPSC today?
- Which GS paper does this map to?
- How should I approach this for Prelims vs Mains?

**Less is more.** Quality over quantity. No fluff. Syllabus-aligned.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  40+ RSS    │ ──▶ │  Backend API     │ ──▶ │  Next.js     │
│  Sources    │     │  FastAPI +       │     │  Frontend    │
│             │     │  PostgreSQL      │     │  (Vercel)    │
└─────────────┘     └──────────────────┘     └──────────────┘
                          │
                          ▼
                    ┌──────────────────┐
                    │  Pipeline (6h)   │
                    │  Fetch → Clean   │
                    │  → Cluster →     │
                    │  Rank → UPSC     │
                    │  Score → Analyze │
                    └──────────────────┘
```

### Backend (Python/FastAPI)

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API | FastAPI + Uvicorn | REST endpoints for news, UPSC intelligence, markets, briefings |
| Database | SQLAlchemy + PostgreSQL/SQLite | Story storage, UPSC scores, exam playbooks, market data |
| Pipeline | APScheduler (6h interval) | RSS fetch → TF-IDF classify → HDBSCAN cluster → rank → UPSC score → analyze → summarize |
| Services | 12 service modules | Fetch, clean, cluster, classify, rank, UPSC filter, UPSC analyzer, summarize, markets, briefing, PDF |
| Container | Docker (multi-stage) | Single uvicorn worker for 512MB RAM free tier |

### Frontend (Next.js/TypeScript)

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Framework | Next.js 16 + React 19 | SSR + client components |
| Styling | Tailwind CSS 4 | Utility-first styling |
| UI | shadcn/ui + Radix Primitives | Accessible component library |
| Charts | Recharts | Market movers bar chart |
| Icons | Lucide | Consistent icon set |
| Static Hosting | Vercel | Zero-config deployment |

## Quick Start

```bash
# 1. Start everything with Docker
docker compose up -d

# 2. Run the pipeline (fetches 40+ RSS sources)
curl -X POST http://localhost:8001/pipeline/run

# 3. Open the dashboard
open http://localhost:3000

# Or run frontend separately:
cd frontend && npm install && npm run dev
```

## Features

- **40+ RSS sources** across global news, tech, business, energy, India, and sports
- **UPSC Syllabus Classification** — TF-IDF matching against full syllabus for GS paper mapping
- **7 intelligence sectors**: Markets, Tech, Geopolitics, Energy, India, Sports, General
- **TF-IDF clustering** — no external ML models, instant startup, works in 512MB RAM
- **4-factor ranking** — coverage, recency, source authority, source diversity
- **UPSC Intelligence** — relevance scoring, novelty detection, exam playbook generation
- **Automated briefings** — Markdown + PDF executive summaries
- **Market data** — 33 tickers via yfinance, refreshed every pipeline run
- **Story reviews** — users can flag incorrect sectors, rate summaries, and report missing images

## Deployment

| Component | Host | Method |
|-----------|------|--------|
| Backend | Render | Docker (Dockerfile at repo root) |
| Database | Supabase (free) or Render PostgreSQL | Connection string via DATABASE_URL |
| Frontend | Vercel | Next.js static export (vercel.json) |

## UPSC Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/upsc` | UPSC-filtered stories with exam playbooks |

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | For production | PostgreSQL connection string |
| `API_KEY` | Recommended | Auth for POST endpoints |
| `CORS_ORIGINS` | For production | Frontend URL for CORS |
| `GEMINI_API_KEY` | Recommended | Enables exam playbook generation |
| `LOG_LEVEL` | No | Default: INFO |
| `NEXT_PUBLIC_API_URL` | For frontend | Backend URL |
