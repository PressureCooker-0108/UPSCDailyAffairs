"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { Story, SectorSummary } from "@/types/story"
import { fetchSectorStories, fetchSectorSummaries, fetchSourceDiversity } from "@/lib/api"
import { MarketDashboard } from "@/components/markets/MarketDashboard"
import { Header } from "@/components/header"
import { StoryCard } from "@/components/news/StoryCard"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ArrowLeft, TrendingUp, Newspaper, Activity, BarChart3 } from "lucide-react"

const SECTOR_COLORS: Record<string, { bg: string; text: string; accent: string }> = {
  Markets: { bg: "from-emerald-500/20 to-emerald-600/10", text: "text-emerald-400", accent: "border-emerald-500/30" },
  Tech: { bg: "from-blue-500/20 to-blue-600/10", text: "text-blue-400", accent: "border-blue-500/30" },
  Geopolitics: { bg: "from-red-500/20 to-red-600/10", text: "text-red-400", accent: "border-red-500/30" },
  Energy: { bg: "from-amber-500/20 to-amber-600/10", text: "text-amber-400", accent: "border-amber-500/30" },
  India: { bg: "from-orange-500/20 to-orange-600/10", text: "text-orange-400", accent: "border-orange-500/30" },
  Sports: { bg: "from-purple-500/20 to-purple-600/10", text: "text-purple-400", accent: "border-purple-500/30" },
  General: { bg: "from-slate-500/20 to-slate-600/10", text: "text-slate-400", accent: "border-slate-500/30" },
}

const SECTOR_ICONS: Record<string, string> = {
  Markets: "📊",
  Tech: "💻",
  Geopolitics: "🌍",
  Energy: "⚡",
  India: "🇮🇳",
  Sports: "🏆",
  General: "📰",
}

export default function SectorPage() {
  const params = useParams()
  const router = useRouter()
  const sector = (params.sector as string).charAt(0).toUpperCase() + (params.sector as string).slice(1)

  const [stories, setStories] = useState<Story[]>([])
  const [summary, setSummary] = useState<SectorSummary | null>(null)
  const [sources, setSources] = useState<{ source: string; count: number }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const [storyData, summaryData, sourceData] = await Promise.all([
          fetchSectorStories(sector),
          fetchSectorSummaries(),
          fetchSourceDiversity(),
        ])
        setStories(storyData)
        setSummary(summaryData.find((s) => s.sector.toLowerCase() === sector.toLowerCase()) || null)
        setSources(sourceData.slice(0, 10))
      } catch (err) {
        setError("Failed to load sector data")
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [sector])

  const colors = SECTOR_COLORS[sector] || SECTOR_COLORS.General
  const icon = SECTOR_ICONS[sector] || "📰"

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-8">
          <div className="flex items-center justify-center py-16 sm:py-20">
            <div className="flex flex-col items-center gap-3 sm:gap-4">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              <p className="text-xs sm:text-sm text-muted-foreground">Loading {sector} intel...</p>
            </div>
          </div>
        </main>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex flex-col items-center justify-center py-20">
            <p className="text-red-400">{error}</p>
            <Button variant="outline" className="mt-4" onClick={() => router.push("/")}>
              Back to Dashboard
            </Button>
          </div>
        </main>
      </div>
    )
  }

  const breakingNews = stories.filter((s) => (s.score || 0) > 70)

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-8 space-y-6 sm:space-y-8">
        {/* Back Button */}
        <Button
          variant="ghost"
          className="gap-2 text-muted-foreground hover:text-foreground text-xs sm:text-sm"
          onClick={() => router.push("/")}
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Button>

        {/* Hero Section */}
        <div className={`relative overflow-hidden rounded-xl sm:rounded-2xl border ${colors.accent} bg-gradient-to-br ${colors.bg} p-4 sm:p-8`}>
          <div className="relative z-10">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-3 sm:mb-4">
              <span className="text-2xl sm:text-4xl">{icon}</span>
              <h1 className="text-2xl sm:text-4xl font-bold tracking-tight">{sector}</h1>
              <Badge variant="secondary" className="text-[10px] sm:text-xs">
                {stories.length} stories
              </Badge>
            </div>

            {summary && (
              <p className="text-sm sm:text-lg text-muted-foreground max-w-3xl leading-relaxed">
                {summary.summary}
              </p>
            )}

            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-4 sm:mt-6">
              <div className="flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm text-muted-foreground">
                <Newspaper className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                {stories.length} headlines
              </div>
              <div className="flex items-center gap-1.5 sm:gap-2 text-xs sm:text-sm text-muted-foreground">
                <Activity className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                {sources.length} sources tracking
              </div>
            </div>
          </div>
        </div>

        {/* Markets Dashboard — full market data for the Markets sector */}
        {sector === "Markets" && (
          <div className="animate-fade-in">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 className="h-4 w-4 text-emerald-400" />
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">
                Live Market Data
              </span>
              <div className="h-px flex-1 bg-border/60" />
            </div>
            <MarketDashboard />
          </div>
        )}

        {/* Breaking News Alert */}
        {breakingNews.length > 0 && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-3 sm:p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="relative flex h-2.5 w-2.5 sm:h-3 sm:w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 sm:h-3 sm:w-3 bg-red-500" />
              </span>
              <h2 className="text-sm sm:text-base font-semibold text-red-400">Breaking News</h2>
            </div>
            <div className="grid gap-2 sm:gap-3">
              {breakingNews.slice(0, 3).map((story, i) => (
                <div key={i} className="rounded-lg bg-red-500/5 border border-red-500/20 p-2 sm:p-3">
                  <a href={story.url} target="_blank" rel="noopener noreferrer" className="group">
                    <h3 className="text-xs sm:text-sm font-medium group-hover:text-red-400 transition-colors line-clamp-2">{story.headline}</h3>
                    <p className="text-[11px] sm:text-sm text-muted-foreground mt-1 line-clamp-2">{story.summary}</p>
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* All Stories Grid */}
        <div>
          <h2 className="text-lg sm:text-2xl font-bold mb-4 sm:mb-6 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 sm:h-5 sm:w-5" />
            All {sector} Headlines
          </h2>

          {stories.length === 0 ? (
            <div className="text-center py-8 sm:py-12">
              <p className="text-sm sm:text-base text-muted-foreground">No stories available for this sector yet.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
              {stories.map((story, i) => (
                <div key={i} className={`animate-fade-in stagger-${Math.min((i % 6) + 1, 6)}`}>
                  <StoryCard story={story} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Source Landscape */}
        {sources.length > 0 && (
          <div className="rounded-xl border border-border bg-card p-4 sm:p-6">
            <h3 className="font-semibold mb-4 flex items-center gap-2 text-sm sm:text-base">
              <Activity className="h-4 w-4" />
              Source Landscape
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2 sm:gap-3">
              {sources.map((src, i) => (
                <div key={i} className="flex items-center gap-2 p-2 rounded-lg bg-muted/30">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs sm:text-sm font-medium truncate">{src.source}</p>
                    <p className="text-[10px] sm:text-xs text-muted-foreground">{src.count} articles</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-border mt-12 py-6 text-center text-xs text-muted-foreground">
        <p>Serious Operator News Dashboard &mdash; {sector} Sector Intelligence</p>
      </footer>
    </div>
  )
}
