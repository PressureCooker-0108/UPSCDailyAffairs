# Serious Operator News Dashboard — Frontend

High-signal global news aggregation frontend, built with Next.js 16, React 19, shadcn/ui, and Tailwind CSS 4.

## Overview

This is the frontend for the **Serious Operator News Dashboard** — a decision-support tool for founders, investors, and analysts. It displays clustered, ranked, and classified news stories from 26+ RSS sources across 7 intelligence sectors.

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
- **StoryCard** — News card with Dialog modal for details + integrated **StoryReview** form
- **StoryReview** — Collapsible review form for users to flag incorrect sectors, rate summaries, and report missing images
- **Header** — Sticky header with refresh, theme toggle, export (MD/JSON/PDF)

## Sectors

Markets · Tech · Geopolitics · Energy · India · Sports · General

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
