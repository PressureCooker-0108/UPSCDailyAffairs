# Serious Operator News Dashboard

High-signal global news aggregation, clustering, ranking, and briefing — designed for founders, investors, and analysts who need signal, not noise.

## Philosophy

This is not a traditional news website. It's a **decision-support tool** that answers:

- What are the most important things happening today?
- Why do they matter?
- What are the implications?

**Less is more.** Top 5–10 stories max. No clickbait. No fluff. High signal density.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  26+ RSS    │ ──▶ │  Backend API     │ ──▶ │  Next.js     │
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

### Backend (Python/FastAPI)

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API | FastAPI + Uvicorn | REST endpoints for news, markets, briefings, reviews |
| Database | SQLAlchemy + PostgreSQL/SQLite | Story storage, market data, briefings, reviews |
| Pipeline | APScheduler (6h interval) | RSS fetch → TF-IDF dedup + HDBSCAN cluster → rank → classify → summarize |
| Services | 9 service modules | Fetch, clean, cluster, classify, rank, summarize, markets, briefing, PDF |
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

# 2. Run the pipeline (fetches 26+ RSS sources)
curl -X POST http://localhost:8001/pipeline/run

# 3. Open the dashboard
open http://localhost:3000

# Or run frontend separately:
cd frontend && npm install && npm run dev
```

## Features

- **26+ RSS sources** across global news, tech, business, energy, India, and sports
- **7 intelligence sectors**: Markets, Tech, Geopolitics, Energy, India, Sports, General
- **TF-IDF clustering** — no external ML models, instant startup, works in 512MB RAM
- **4-factor ranking** — coverage, recency, source authority, source diversity
- **Automated briefings** — Markdown + PDF executive summaries
- **Market data** — 33 tickers via yfinance, refreshed every pipeline run
- **Story reviews** — users can flag incorrect sectors, rate summaries, and report missing images

## Deployment

| Component | Host | Method |
|-----------|------|--------|
| Backend | Render | Docker (Dockerfile at repo root) |
| Database | Supabase (free) or Render PostgreSQL | Connection string via DATABASE_URL |
| Frontend | Vercel | Next.js static export (vercel.json) |

See [`frontend/AGENTS.md`](frontend/AGENTS.md) for the complete AI-readable project reference.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Health check (no DB dependency) |
| GET | `/news` | Top stories (cached 5 min) |
| GET | `/news/stories` | All stories |
| GET | `/news/sectors` | List of active sectors |
| GET | `/news/sector/{sector}` | Stories filtered by sector |
| GET | `/news/sector-summaries` | Per-sector AI summaries |
| GET | `/news/reviews` | All submitted story reviews |
| POST | `/news/reviews` | Submit a story review (public) |
| GET | `/markets` | Market data (indices, gainers, losers) |
| POST | `/markets/refresh` | Refresh market data (rate-limited) |
| GET | `/briefing` | Latest executive briefing |
| POST | `/briefing/generate` | Generate new briefing |
| GET | `/export/markdown` | Download Markdown briefing |
| GET | `/export/json` | Download JSON export |
| GET | `/export/pdf` | Download PDF briefing |
| GET | `/sources` | Source diversity stats |
| GET | `/trending` | Trending topics (default 48h) |
| POST | `/pipeline/run` | Trigger full pipeline (rate-limited) |

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | For production | PostgreSQL connection string |
| `API_KEY` | Recommended | Auth for POST endpoints (except `/news/reviews`) |
| `CORS_ORIGINS` | For production | Frontend URL for CORS |
| `LOG_LEVEL` | No | Default: INFO |
| `NEXT_PUBLIC_API_URL` | For frontend | Backend URL |

## License

MIT
