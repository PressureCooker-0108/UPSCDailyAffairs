# UPSC Daily Affairs

AI-powered current affairs aggregation for UPSC Civil Services Examination preparation. Every news story is classified by GS paper, scored for exam relevance, analyzed for Prelims/Mains angles, and given an AI-generated exam playbook.

## Philosophy

This is not a general news dashboard. It's an **exam-intelligence tool** that answers:

- What current affairs topics are most relevant for UPSC today?
- Which GS paper does this map to?
- How should I approach this for Prelims vs Mains?
- What's the factual accuracy and exam relevance of this story?

**Less is more.** Quality over quantity. No fluff. Syllabus-aligned.

## Architecture

```
┌─────────────┐     ┌──────────────────────┐     ┌──────────────┐
│  40+ RSS    │ ──▶ │  Backend API         │ ──▶ │  Next.js     │
│  Sources    │     │  FastAPI + PostgreSQL│     │  Frontend    │
│             │     │                      │     │  (Vercel)    │
└─────────────┘     └──────────────────────┘     └──────────────┘
                          │
                          ▼
            ┌─────────────────────────────────────┐
            │  Pipeline (6h)                      │
            │  Fetch → Clean → Cluster → Rank →   │
            │  ↓                                  │
            │  ┌─ Phase 0: ML Review (free)       │
            │  ├─ Phase 1: AI Review (OpenRouter) │
            │  └─ Phase 2: Exam Playbook          │
            │         + Market Data + Briefing    │
            │                                     │
            │  ┌─ Continuous Improvement Loop     │
            │  │  Feedback → Auto-Retrain →       │
            │  │  Threshold Tune → Active Learnin │
            │  └──────────────────────────────────│
            └─────────────────────────────────────┘
```

### Backend (Python/FastAPI)

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API | FastAPI + Uvicorn | REST endpoints for news, UPSC intelligence, ML diagnostics |
| Database | SQLAlchemy + PostgreSQL/SQLite | Stories, AI reviews, exam playbooks, feedback buffer, market data |
| Pipeline | APScheduler (6h interval) | RSS fetch → classify → ML/AI review → UPSC score → playbook |
| ML Layer | scikit-learn LogisticRegression | Fast pre-filter (free, instant) — predicts PASS/FLAG/REJECT |
| AI Layer | OpenRouter (Owl Alpha) | Ground-truth verdicts, GS paper mapping, exam playbooks |
| Auto-Training | `ml_auto_retrain.py` | Feedback capture → threshold tuning → model retrain (6h/24h/144h) |
| Services | 12+ service modules | Fetch, clean, cluster, rank, UPSC filter, UPSC analyze, ML classify, AI review |
| Container | Docker (multi-stage) | Single uvicorn worker for 512MB RAM free tier |

### Frontend (Next.js/TypeScript)

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Framework | Next.js 16 + React 19 | SSR + client components |
| Styling | Tailwind CSS 4 | Utility-first styling |
| UI | shadcn/ui + Radix Primitives | Accessible component library |
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

## The 3-Tier Review Pipeline

Each story goes through three evaluation stages:

| Phase | Model | Cost | Speed | Output |
|-------|-------|------|-------|--------|
| **0 — ML Review** | LogisticRegression (TF-IDF) | Free | < 50ms per story | PASS / FLAG / REJECT + confidence |
| **1 — AI Review** | OpenRouter Owl Alpha | ~$0 per call (free tier) | ~8s per story | PASS / FLAG / REJECT + reasoning + GS paper mapping |
| **2 — Playbook** | OpenRouter Owl Alpha | ~$0 per call (free tier) | ~10s per story | Prelims format, Mains approach, factual accuracy check |

**Optimization:** If the ML model confidently predicts PASS (≥ confidence threshold), Phase 1 AI review is skipped — saving API budget. A 5% active learning sample still gets AI review for ground-truth feedback.

## Continuous Improvement Loop

```
Every pipeline run (6h):
  └─ Phase 0: ML review (free, instant)
  └─ Phase 1: AI review (costs budget) — ground truth
  └─ capture_feedback() — ML vs AI comparison saved to buffer
  
After pipeline:
  └─ check_should_retrain() — enough data + enough time?
         ├─ "continuous" mode: scales by model maturity
         └─ "scheduled" mode: fixed 3d collect / 6d retrain
  └─ auto_retrain() → auto_tune_threshold() → reload model
```

### Retrain Schedule

| Mode | Config Value | < 100 samples | 100–500 | 500+ |
|------|-------------|---------------|---------|------|
| **Continuous** (default) | `ML_RETRAIN_MODE = "continuous"` | every 6h | every 24h | every 144h (6d) |
| **Scheduled** | `ML_RETRAIN_MODE = "scheduled"` | every 6d | every 6d | every 6d |

Toggle in `backend/config.py`:
```python
ML_RETRAIN_MODE = "continuous"  # ← change to "scheduled" when model is mature
```

## Training Data Generation

To generate ground-truth AI reviews for ML training:

```bash
# 1. Trigger generation on production
curl -X POST https://upscdailyaffairs.onrender.com/train-data/generate

# 2. Check progress
curl https://upscdailyaffairs.onrender.com/train-data/status

# 3. Download training data
curl -o training_data.jsonl https://upscdailyaffairs.onrender.com/train-data/latest

# 4. Train ML model locally
python train_ml_classifier.py --eval
```

## Features

- **40+ RSS sources** across global news, tech, business, energy, India, and sports
- **UPSC Syllabus Classification** — TF-IDF matching against full syllabus for GS paper mapping
- **3-tier review pipeline** — ML pre-filter → AI ground truth → exam playbook
- **Exam Playbook generation** — GS paper, Prelims format, Mains approach, factual accuracy check
- **Continuous ML improvement** — auto-retrain, dynamic threshold tuning, active learning
- **7 intelligence sectors**: Markets, Tech, Geopolitics, Energy, India, Sports, General
- **TF-IDF clustering** — no external ML models, instant startup, works in 512MB RAM
- **4-factor ranking** — coverage, recency, source authority, source diversity
- **Story reviews** — users can flag verdicts, rate summaries, and report issues
- **Market data** — 33 tickers via yfinance, refreshed every pipeline run

## UPSC Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/upsc` | UPSC-filtered stories with AI reviews and exam playbooks |
| GET | `/upsc/status` | Pipeline status and story counts |
| GET | `/pipeline/status` | Full pipeline status (ML, AI, budget) |
| GET | `/pipeline/test-openrouter` | OpenRouter connectivity test |
| POST | `/pipeline/run` | Trigger full pipeline |
| POST | `/train-data/generate` | Batch-generate AI reviews for ML training |
| GET | `/train-data/status` | Training data generation status |
| GET | `/train-data/latest` | Download latest training data |
| POST | `/ml/retrain` | Manually trigger ML model retrain |
| GET | `/ml/retrain-state` | Auto-retrain diagnostics and state |

## Deployment

| Component | Host | Method |
|-----------|------|--------|
| Backend | Render | Python native runtime (or Docker) |
| Database | Render PostgreSQL (free) | Connection string via DATABASE_URL |
| Frontend | Vercel | Next.js static export (vercel.json) |

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | For production | PostgreSQL connection string |
| `OPENROUTER_API_KEY` | Recommended | Enables Owl Alpha exam playbook + AI review |
| `API_KEY` | Optional | Auth for POST endpoints |
| `CORS_ORIGINS` | For production | Frontend URL for CORS |
| `AI_MIN_REQUEST_INTERVAL_SECONDS` | No | Default: 3.5s between OpenRouter requests |
| `AI_FREE_TIER_RUN_CAP` | No | Default: 20 AI calls per pipeline run |
| `LOG_LEVEL` | No | Default: INFO |
| `NEXT_PUBLIC_API_URL` | For frontend | Backend URL |

**OpenRouter note:** `openrouter/owl-alpha` is configured as the review and playbook model. It is free to use, but free-tier request limits still apply and the provider may log prompts/completions.

### ML Retrain Mode

Set in `backend/config.py`:
```python
ML_RETRAIN_MODE = "continuous"  # or "scheduled" for 3d/6d cycle
```