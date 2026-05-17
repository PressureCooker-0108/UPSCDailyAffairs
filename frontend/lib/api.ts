import { Story, MarketDataPoint, SectorSummary, SourceDiversity, Briefing } from "@/types/story"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001"

export async function fetchStories(): Promise<Story[]> {
  try {
    const res = await fetch(`${API_URL}/news`, { cache: "no-store" })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const stories = data.top_stories || []

    return stories.map((s: any) => ({
      headline: s.title || s.headline || "Untitled",
      summary: s.summary || "No summary available",
      why_it_matters: s.why_it_matters || "Analysis pending",
      url: s.url || undefined,
      sectors: s.sectors || ["General"],
      score: s.score,
      article_count: s.article_count,
      source: s.source || [],
    }))
  } catch (err) {
    console.error("Failed to fetch stories:", err)
    return []
  }
}

export async function fetchSectorStories(sector: string): Promise<Story[]> {
  try {
    const res = await fetch(`${API_URL}/news/sector/${encodeURIComponent(sector)}`, { cache: "no-store" })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const stories = data.stories || []

    return stories.map((s: any) => ({
      headline: s.title || s.headline || "Untitled",
      summary: s.summary || "No summary available",
      why_it_matters: s.why_it_matters || "Analysis pending",
      url: s.url || undefined,
      sectors: s.sectors || [sector],
      score: s.score,
      article_count: s.article_count,
      source: s.source || [],
    }))
  } catch (err) {
    console.error(`Failed to fetch stories for sector ${sector}:`, err)
    return []
  }
}

export async function fetchMarketData(): Promise<{ all: MarketDataPoint[]; gainers: MarketDataPoint[]; losers: MarketDataPoint[]; indices: MarketDataPoint[] }> {
  try {
    const res = await fetch(`${API_URL}/markets`, { cache: "no-store" })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    console.error("Failed to fetch market data:", err)
    return { all: [], gainers: [], losers: [], indices: [] }
  }
}

export async function fetchBriefing(): Promise<Briefing | null> {
  try {
    const res = await fetch(`${API_URL}/briefing`, { cache: "no-store" })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    console.error("Failed to fetch briefing:", err)
    return null
  }
}

export async function generateBriefing(): Promise<Briefing | null> {
  try {
    const res = await fetch(`${API_URL}/briefing/generate`, { method: "POST" })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    console.error("Failed to generate briefing:", err)
    return null
  }
}

export async function fetchSectorSummaries(): Promise<SectorSummary[]> {
  try {
    const res = await fetch(`${API_URL}/news/sector-summaries`, { cache: "no-store" })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    return data.summaries || []
  } catch (err) {
    console.error("Failed to fetch sector summaries:", err)
    return []
  }
}

export async function fetchSourceDiversity(): Promise<SourceDiversity[]> {
  try {
    const res = await fetch(`${API_URL}/sources`, { cache: "no-store" })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    return data.sources || []
  } catch (err) {
    console.error("Failed to fetch source diversity:", err)
    return []
  }
}

export async function fetchTrending(hours: number = 48): Promise<{ title: string; score: number; article_count: number; sectors: string[] }[]> {
  try {
    const res = await fetch(`${API_URL}/trending?hours=${hours}`, { cache: "no-store" })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    return data.trending || []
  } catch (err) {
    console.error("Failed to fetch trending:", err)
    return []
  }
}

export async function submitReview(review: {
  story_title: string
  story_url?: string
  correct_section: "yes" | "no"
  suggested_section?: string
  summary_concise: "yes" | "no"
  picture_available: "yes" | "no"
  comment?: string
}): Promise<{ status: string } | null> {
  try {
    const res = await fetch(`${API_URL}/news/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(review),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    console.error("Failed to submit review:", err)
    return null
  }
}

async function downloadExport(endpoint: string, _ext: string): Promise<void> {
  // Hidden anchor with target=_blank creates a real HTTP request
  // that IDM can intercept, while avoiding popup blockers.
  const a = document.createElement("a")
  a.href = `${API_URL}${endpoint}`
  a.target = "_blank"
  a.style.display = "none"
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

export async function downloadMarkdown(): Promise<void> {
  try {
    await downloadExport("/export/markdown", "md")
  } catch (err) {
    console.error("Failed to download markdown:", err)
    throw err
  }
}

export async function downloadJson(): Promise<void> {
  try {
    await downloadExport("/export/json", "json")
  } catch (err) {
    console.error("Failed to download JSON:", err)
    throw err
  }
}

export async function downloadPdf(): Promise<void> {
  try {
    await downloadExport("/export/pdf", "pdf")
  } catch (err) {
    console.error("Failed to download PDF:", err)
    throw err
  }
}
