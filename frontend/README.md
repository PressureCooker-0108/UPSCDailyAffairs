# UPSC Daily Affairs — Frontend

UPSC current affairs intelligence frontend, built with Next.js 16, React 19, shadcn/ui, and Tailwind CSS 4.

## Overview

This is the frontend for **UPSC Daily Affairs** — an exam-intelligence platform for UPSC Civil Services aspirants. It displays syllabus-classified current affairs stories from 40+ RSS sources, with GS paper mapping, AI-generated exam verdicts (PASS/FLAG/REJECT), and full exam playbooks covering Prelims format, Mains approach, and factual accuracy.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 16 + React 19 |
| Styling | Tailwind CSS 4 |
| UI | shadcn/ui (Radix Primitives) |
| Charts | Recharts |
| Icons | Lucide |
| Deployment | Vercel |

## Key Components

- **BigStory** — Featured hero story (highest scored)
- **MarketDashboard** — Indices grid, gainers/losers, Recharts bar chart
- **SectorHeatmap** — Color-coded sector tiles with proportional sizing
- **SectorSection** — 3-column grid linking to `/sectors/{sector}`
- **TopStories** — Bento-grid layout for top 6 stories
- **StoryCard** — News card with Dialog modal showing AI review verdict, GS paper mapping, exam playbook, and integrated **StoryReview** feedback form
- **StoryReview** — Collapsible review form for users to flag incorrect verdicts, suggest corrections, rate summary quality, and report issues
- **Header** — Sticky header with refresh, theme toggle, export (MD/JSON/PDF)
- **ErrorBoundary** — React error boundary with retry and dev-mode stack trace

## Sectors

Markets · Tech · Geopolitics · Energy · India · Sports · General

## Story Review Flow

Each story card shows:
- **AI Verdict badge** — PASS (green) / FLAG (yellow) / REJECT (red)
- **GS Paper mapping** — Paper I–IV with topic match
- **Exam Playbook** — Prelims format, Mains approach, factual accuracy note
- **StoryReview form** — Users can flag incorrect verdicts and suggest improvements

Story reviews submitted to `POST /news/reviews` (public endpoint, no auth).

## Quick Start

```bash
cd frontend
npm install
npm run dev
```

The app runs at [http://localhost:3000](http://localhost:3000). It connects to the backend API at `http://127.0.0.1:8001` by default (set `NEXT_PUBLIC_API_URL` to override).

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8001` | Backend API URL |

## Deployment

Deploy on Vercel:

1. Push to GitHub
2. Import repo in Vercel
3. Set `NEXT_PUBLIC_API_URL` to your Render backend URL
4. Deploy

The `vercel.json` config: `{ "framework": "nextjs" }`

## Learn More

- [Next.js Documentation](https://nextjs.org/docs)
- [shadcn/ui](https://ui.shadcn.com)
- [Tailwind CSS v4](https://tailwindcss.com)
