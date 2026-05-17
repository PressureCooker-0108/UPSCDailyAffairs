"use client"

import { useEffect, useState, useRef, useCallback } from "react"
import { Story } from "@/types/story"
import { fetchStories, fetchTrending } from "@/lib/api"
import { Header } from "@/components/header"
import { BigStory } from "@/components/news/BigStory"
import { TopStories } from "@/components/news/TopStories"
import { SectorSection } from "@/components/news/SectorSection"
import { SectorHeatmap } from "@/components/news/SectorHeatmap"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Activity,
  Globe,
  TrendingUp,
  RefreshCw,
  FileText,
  Download,
  FileDown,
  Search,
  Clock,
  LayoutGrid,
} from "lucide-react"
import { Input } from "@/components/ui/input"
import Link from "next/link"
import { downloadMarkdown, downloadJson, downloadPdf } from "@/lib/api"
import { toast } from "sonner"

const SCOLORS: Record<string, string> = {
  Markets: "emerald",
  Tech: "blue",
  Geopolitics: "red",
  Energy: "amber",
  India: "orange",
  Sports: "purple",
  General: "slate",
}

export default function Dashboard() {
  const [stories, setStories] = useState<Story[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [debouncedQuery, setDebouncedQuery] = useState("")
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [trendingData, setTrendingData] = useState<{ title: string; score: number }[]>([])
  const [now, setNow] = useState(Date.now())
  const [lastFetchedAt, setLastFetchedAt] = useState(Date.now())

  async function load() {
    try {
      setLoading(true)
      const [s, t] = await Promise.all([
        fetchStories(),
        fetchTrending(48),
      ])
      setStories(s)
      setTrendingData(t.slice(0, 10))
      setLastFetchedAt(Date.now())
      setError(null)
    } catch {
      setError("Failed to load stories")
    } finally {
      setLoading(false)
    }
  }

  // Tick clock every second for auto-refresh indicator
  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(tick)
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 120000) // Refresh every 2 mins
    return () => clearInterval(interval)
  }, [])

  // Debounce search query — 300ms
  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setDebouncedQuery(value), 300)
  }, [])

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  // Search filter
  const query = debouncedQuery.toLowerCase()
  const filteredStories = query
    ? stories.filter(
        (s) =>
          s.headline.toLowerCase().includes(query) ||
          s.summary.toLowerCase().includes(query) ||
          (s.sectors && s.sectors.some((sec) => sec.toLowerCase().includes(query)))
      )
    : stories

  // Sector grouping (using filtered stories for display)
  const sectorGroups: Record<string, Story[]> = {}
  const seenSectors = new Set<string>()

  for (const story of filteredStories) {
    for (const sector of story.sectors || ["General"]) {
      if (!sectorGroups[sector]) sectorGroups[sector] = []
      sectorGroups[sector].push(story)
      seenSectors.add(sector)
    }
  }

  const displayOrder = ["Markets", "Tech", "Geopolitics", "Energy", "India", "Sports", "General"]
  const activeSectors = displayOrder.filter((s) => seenSectors.has(s))

  // Calculate relative time for last update
  function relativeTime(ms: number): string {
    const secs = Math.floor((Date.now() - ms) / 1000)
    if (secs < 5) return "just now"
    if (secs < 60) return `${secs}s ago`
    const mins = Math.floor(secs / 60)
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    return `${hrs}h ago`
  }

  if (loading && stories.length === 0) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
          {/* Hero skeleton */}
          <div className="animate-pulse">
            <div className="rounded-xl bg-muted h-64 sm:h-80 lg:h-96 w-full" />
          </div>
          {/* Story card skeletons — grid of 6 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="animate-pulse rounded-xl border border-border/50 p-4 space-y-3">
                <div className="bg-muted h-5 w-3/4 rounded" />
                <div className="bg-muted/60 h-3 w-full rounded" />
                <div className="bg-muted/60 h-3 w-5/6 rounded" />
                <div className="flex gap-2 pt-2">
                  <div className="bg-muted/40 h-5 w-16 rounded-full" />
                  <div className="bg-muted/40 h-5 w-12 rounded-full" />
                </div>
              </div>
            ))}
          </div>
        </main>
      </div>
    )
  }

  if (error && stories.length === 0) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex flex-col items-center justify-center py-32 gap-4">
            <p className="text-red-400">{error}</p>
            <Button variant="outline" onClick={load}>
              <RefreshCw className="h-4 w-4 mr-2" /> Retry
            </Button>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-10">
        {stories.length === 0 && !searchQuery ? (
          <div className="flex flex-col items-center justify-center py-32 gap-4">
            <div className="rounded-full bg-muted p-6">
              <Activity className="h-10 w-10 text-muted-foreground" />
            </div>
            <h2 className="text-xl font-semibold">Station Idle</h2>
            <p className="text-sm text-muted-foreground max-w-md text-center">
              The pipeline is warming up. Intelligence will appear here once the first
              processing cycle completes.
            </p>
          </div>
        ) : (
          <>
            {/* Top Bar: Search + Refresh Indicator — full-width on mobile */}
            <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
              <div className="relative w-full sm:max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search stories, sectors, topics..."
                  value={searchQuery}
                  onChange={(e) => handleSearchChange(e.target.value)}
                  className="pl-9 h-10 text-sm w-full"
                />
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground shrink-0 self-end sm:self-auto">
                <Clock className="h-3.5 w-3.5" />
                <span>Updated {relativeTime(lastFetchedAt)}</span>
              </div>
            </div>

            {/* Trending Topics Bar */}
            {trendingData.length > 0 && (
              <div className="animate-fade-in">
                <div className="flex items-center gap-2 mb-3">
                  <TrendingUp className="h-4 w-4 text-primary shrink-0" />
                  <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">
                    Trending Now
                  </span>
                  <div className="h-px flex-1 bg-border/60" />
                </div>
                <div className="flex flex-wrap gap-2">
                  {trendingData.slice(0, 6).map((item, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary/5 border border-primary/10 text-xs font-medium text-foreground/80 hover:bg-primary/10 hover:text-primary transition-colors cursor-default"
                    >
                      <span className="text-[10px] font-bold text-primary/60">
                        {String.fromCharCode(65 + i)}
                      </span>
                      <span className="truncate max-w-[140px] sm:max-w-[200px]">
                        {item.title.length > 40 ? item.title.slice(0, 40) + "…" : item.title}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Filter notice */}
            {searchQuery && filteredStories.length === 0 && (
              <div className="text-center py-12">
                <Search className="h-8 w-8 mx-auto mb-3 text-muted-foreground/40" />
                <p className="text-sm text-muted-foreground">
                  No stories match &ldquo;{searchQuery}&rdquo;
                </p>
                <Button variant="link" size="sm" onClick={() => setSearchQuery("")}>
                  Clear filter
                </Button>
              </div>
            )}

            {/* ── SECTOR INTELLIGENCE (moved to the top) ── */}
            <div className="animate-fade-in">
              {/* Section label */}
              <div className="flex items-center gap-2 mb-4">
                <LayoutGrid className="h-4 w-4 text-primary" />
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">
                  Sectors
                </span>
                <div className="h-px flex-1 bg-border/60" />
              </div>

              {/* Sector Heatmap — visual overview with color-coded intensity */}
              <SectorHeatmap sectorGroups={sectorGroups} activeSectors={activeSectors} />

              {/* Sector Navigation Cards */}
              {activeSectors.length > 0 && (
                <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 sm:gap-3">
                  {activeSectors.map((sector, i) => (
                    <Link
                      key={sector}
                      href={`/sectors/${sector.toLowerCase()}`}
                      className={`group relative overflow-hidden rounded-xl border border-border/50 bg-card p-3 sm:p-4 transition-all duration-300 hover:shadow-lg hover:border-primary/30 hover:-translate-y-0.5 animate-fade-in stagger-${Math.min(i + 1, 6)}`}
                    >
                      <p className="text-xl sm:text-2xl mb-1">
                        {sector === "Markets" && "📊"}
                        {sector === "Tech" && "💻"}
                        {sector === "Geopolitics" && "🌍"}
                        {sector === "Energy" && "⚡"}
                        {sector === "India" && "🇮🇳"}
                        {sector === "General" && "📰"}
                      </p>
                      <p className="font-semibold text-xs sm:text-sm group-hover:text-primary transition-colors">
                        {sector}
                      </p>
                      <p className="text-[10px] sm:text-xs text-muted-foreground mt-0.5">
                        {sectorGroups[sector]?.length || 0} stories
                      </p>
                    </Link>
                  ))}
                </div>
              )}
            </div>

            {/* Intelligence Feed */}
            {filteredStories[0] && (
              <div className="animate-fade-in">
                <div className="flex items-center gap-2 mb-4">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">
                    Top Story
                  </span>
                  <div className="h-px flex-1 bg-border/60" />
                </div>
                <BigStory story={filteredStories[0]} />
              </div>
            )}

            {/* More Stories */}
            {filteredStories.length > 1 && (
              <div className="animate-fade-in">
                <TopStories stories={filteredStories.slice(1, 7)} />
              </div>
            )}

            {/* Sector Breakdown */}
            {filteredStories.length > 0 && (
              <div className="animate-fade-in">
                <SectorSection stories={filteredStories} />
              </div>
            )}

            {/* Export Buttons */}
            <div className="flex flex-wrap gap-2 sm:gap-3 justify-center pt-4 border-t border-border/50">
              <Button variant="outline" size="sm" className="text-xs sm:text-sm" onClick={async () => { try { await downloadMarkdown(); toast.success("Markdown brief downloaded", { duration: 2500 }); } catch { toast.error("Failed to download Markdown brief"); } }}>
                <FileText className="h-4 w-4 mr-1.5 sm:mr-2" />
                <span className="hidden sm:inline">Export </span>Markdown
              </Button>
              <Button variant="outline" size="sm" className="text-xs sm:text-sm" onClick={async () => { try { await downloadJson(); toast.success("JSON export downloaded", { duration: 2500 }); } catch { toast.error("Failed to download JSON export"); } }}>
                <Download className="h-4 w-4 mr-1.5 sm:mr-2" />
                <span className="hidden sm:inline">Export </span>JSON
              </Button>
              <Button variant="outline" size="sm" className="text-xs sm:text-sm" onClick={async () => { try { await downloadPdf(); toast.success("PDF briefing downloaded", { duration: 2500 }); } catch { toast.error("Failed to download PDF briefing"); } }}>
                <FileDown className="h-4 w-4 mr-1.5 sm:mr-2" />
                <span className="hidden sm:inline">Export </span>PDF
              </Button>
            </div>
          </>
        )}
      </main>

      <footer className="border-t border-border mt-12 py-8 text-center text-xs text-muted-foreground">
        <p className="mb-2">Serious Operator News Dashboard &mdash; Intelligence Grade: Reliable</p>
        <p>Data aggregated from 16+ global news sources across 6 intelligence sectors</p>
      </footer>
    </div>
  )
}
