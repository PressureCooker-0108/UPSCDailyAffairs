"use client"

import { useEffect, useState } from "react"
import { Header } from "@/components/header"
import { ErrorBoundary } from "@/components/error-boundary"
import type { UPSCStory, ExamPlaybook } from "@/types/story"
import { fetchUPSCStories } from "@/lib/api"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import {
  GraduationCap,
  BookOpen,
  Target,
  Lightbulb,
  Scale,
  FileText,
  BrainCircuit,
  BookMarked,
  Star,
  TrendingUp,
  Search,
  Layers,
  Globe,
  Zap,
  Gavel,
  Landmark,
  Leaf,
  Cog,
  Users,
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

const SECTOR_META: Record<string, { label: string; icon: React.ReactNode; color: string; border: string }> = {
  "Market": {
    label: "Market",
    icon: <TrendingUp className="h-3.5 w-3.5" />,
    color: "text-blue-400 bg-blue-500/10 border-blue-500/20",
    border: "border-l-blue-500/40",
  },
  "Geopolitics": {
    label: "Geopolitics",
    icon: <Globe className="h-3.5 w-3.5" />,
    color: "text-rose-400 bg-rose-500/10 border-rose-500/20",
    border: "border-l-rose-500/40",
  },
  "Tech": {
    label: "Tech",
    icon: <Zap className="h-3.5 w-3.5" />,
    color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    border: "border-l-emerald-500/40",
  },
  "Politics": {
    label: "Politics",
    icon: <Landmark className="h-3.5 w-3.5" />,
    color: "text-purple-400 bg-purple-500/10 border-purple-500/20",
    border: "border-l-purple-500/40",
  },
  "Economy": {
    label: "Economy",
    icon: <TrendingUp className="h-3.5 w-3.5" />,
    color: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    border: "border-l-amber-500/40",
  },
  "Environment": {
    label: "Environment",
    icon: <Leaf className="h-3.5 w-3.5" />,
    color: "text-green-400 bg-green-500/10 border-green-500/20",
    border: "border-l-green-500/40",
  },
  "Other": {
    label: "Other",
    icon: <Layers className="h-3.5 w-3.5" />,
    color: "text-slate-400 bg-slate-500/10 border-slate-500/20",
    border: "border-l-slate-500/40",
  },
}

function getSectorMeta(sector: string) {
  const match = Object.keys(SECTOR_META).find(k => k.toLowerCase() === sector.toLowerCase())
  if (match) return SECTOR_META[match]
  return {
    label: sector.charAt(0).toUpperCase() + sector.slice(1),
    icon: <Layers className="h-3.5 w-3.5" />,
    color: "text-slate-400 bg-slate-500/10 border-slate-500/20",
    border: "border-l-slate-500/40",
  }
}

const PRIORITY_COLORS: Record<string, string> = {
  critical: "text-red-400 bg-red-500/10",
  high: "text-orange-400 bg-orange-500/10",
  medium: "text-yellow-400 bg-yellow-500/10",
  low: "text-slate-400 bg-slate-500/10",
}

function mapStoryToSector(story: UPSCStory): string {
  if (story.sectors && story.sectors.length > 0) return story.sectors[0];
  
  const content = (story.headline + " " + story.summary + " " + (story.subtopics || []).join(" ") + " " + (story.gs_paper || "")).toLowerCase();
  
  if (content.includes("market") || content.includes("economy") || content.includes("bank") || content.includes("finance") || content.includes("rbi") || content.includes("inflation") || content.includes("trade") || content.includes("investment") || story.gs_paper === "GS Paper III") return "Economy";
  if (content.includes("tech") || content.includes("ai") || content.includes("digital") || content.includes("space") || content.includes("isro") || content.includes("software") || content.includes("cyber") || content.includes("science")) return "Tech";
  if (content.includes("geopolitics") || content.includes("international") || content.includes("foreign") || content.includes("china") || content.includes("us") || content.includes("russia") || content.includes("war") || content.includes("diplomacy") || story.gs_paper === "GS Paper II") return "Geopolitics";
  if (content.includes("politi") || content.includes("election") || content.includes("court") || content.includes("law") || content.includes("parliament") || content.includes("governance") || content.includes("minister")) return "Politics";
  if (content.includes("environment") || content.includes("climate") || content.includes("pollution") || content.includes("forest") || content.includes("wildlife") || content.includes("energy") || content.includes("species")) return "Environment";
  
  return "Other";
}

function getPriorityLabel(score: number): string {
  if (score >= 0.8) return "critical"
  if (score >= 0.6) return "high"
  if (score >= 0.4) return "medium"
  return "low"
}

function RelevanceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color =
    pct >= 80 ? "bg-green-500/15 text-green-400 border-green-500/20" :
    pct >= 60 ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/20" :
    pct >= 40 ? "bg-amber-500/15 text-amber-400 border-amber-500/20" :
    "bg-red-500/15 text-red-400 border-red-500/20"
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border ${color}`}>
      <Zap className="h-2.5 w-2.5" />
      {pct}%
    </span>
  )
}

function ScoreBar({ label, value, maxWidth = 80 }: { label: string; value: number; maxWidth?: number }) {
  const pct = Math.min(Math.round(value * 100), 100)
  const color =
    pct >= 80 ? "bg-green-500" :
    pct >= 60 ? "bg-emerald-500" :
    pct >= 40 ? "bg-amber-500" :
    "bg-red-500"
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="text-muted-foreground w-16 sm:w-20 shrink-0 truncate">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-border/50 overflow-hidden" style={{ maxWidth }}>
        <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-muted-foreground w-6 text-right font-mono tabular-nums shrink-0">{pct}</span>
    </div>
  )
}

function StoryCard({ story, index }: { story: UPSCStory; index: number }) {
  const [open, setOpen] = useState(false)
  const sector = mapStoryToSector(story)
  const meta = getSectorMeta(sector)
  const priority = getPriorityLabel(story.priority_score || 0)

  return (
    <>
      <div
        onClick={() => setOpen(true)}
        className={cn(
          "group relative rounded-xl border border-border/50 bg-card transition-all duration-300 hover:shadow-lg hover:border-primary/20 sm:hover:-translate-y-0.5 animate-fade-in overflow-hidden cursor-pointer text-left h-full flex flex-col",
          meta.border,
          "border-l-2"
        )}
        style={{ animationDelay: `${Math.min(index * 0.05, 1)}s` }}
      >
          <div className="p-3.5 sm:p-5 flex-1 flex flex-col">
            <div className="flex items-start gap-2.5 mb-2.5">
              <span className="text-[10px] font-mono text-muted-foreground/40 shrink-0 mt-0.5 hidden sm:inline">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div className="flex-1 min-w-0">
                <h3 className="text-xs sm:text-sm md:text-base font-semibold leading-snug text-foreground/90 group-hover:text-foreground transition-colors line-clamp-2">
                  {story.headline}
                </h3>
                {story.source && story.source.length > 0 && (
                  <p className="text-[10px] text-muted-foreground/50 mt-1 truncate">
                    {story.source.join(", ")}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <RelevanceBadge score={story.relevance_score || 0} />
              </div>
            </div>

            <div className="flex flex-wrap gap-1.5 mb-2.5">
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border ${meta.color} shrink-0`}>
                {meta.icon}
                {meta.label}
              </span>
              {story.subtopics?.slice(0, 3).map((st, i) => (
                <span key={i} className="px-1.5 py-0.5 rounded bg-primary/5 text-muted-foreground text-[9px] border border-border/30 shrink-0">
                  {st}
                </span>
              ))}
              {story.subtopics && story.subtopics.length > 3 && (
                <span className="px-1.5 py-0.5 rounded text-[9px] text-muted-foreground/50 shrink-0">
                  +{story.subtopics.length - 3}
                </span>
              )}
            </div>

            <p className="text-[11px] sm:text-xs text-muted-foreground/70 leading-relaxed line-clamp-2 mb-2.5 flex-1">
              {story.summary}
            </p>

            {story.why_it_matters && (
              <div className="flex items-start gap-1.5 mb-2.5">
                <Lightbulb className="h-3 w-3 text-amber-400/60 shrink-0 mt-0.5" />
                <p className="text-[10px] text-amber-400/70 leading-relaxed line-clamp-1">{story.why_it_matters}</p>
              </div>
            )}

            <div className="space-y-1 mb-2.5 mt-auto">
              <ScoreBar label="Relevance" value={story.relevance_score || 0} />
              <ScoreBar label="Priority" value={story.priority_score || 0} />
            </div>

            <div className="flex items-center gap-2 flex-wrap pt-1">
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-medium ${PRIORITY_COLORS[priority] || PRIORITY_COLORS.low} border border-transparent`}>
                <Star className="h-2.5 w-2.5" />
                {priority.charAt(0).toUpperCase() + priority.slice(1)} Priority
              </span>
              {story.article_count && (
                <span className="text-[9px] text-muted-foreground/40">
                  {story.article_count} source{story.article_count !== 1 ? "s" : ""}
                </span>
              )}
            </div>
          </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-[95vw] w-full max-h-[90vh] h-[90vh] md:max-w-[80vw] md:w-[80vw] md:h-[80vh] p-0 overflow-hidden flex flex-col md:flex-row bg-background border-border/50 shadow-2xl rounded-xl">
        <DialogTitle className="sr-only">{story.headline}</DialogTitle>
        
        {/* Main Story Area (Left) */}
        <div className="flex-1 overflow-y-auto p-6 sm:p-8 md:border-r border-border/50">
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${meta.color}`}>
              {meta.icon}
              {meta.label}
            </span>
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium ${PRIORITY_COLORS[priority] || PRIORITY_COLORS.low} border border-transparent`}>
              <Star className="h-3 w-3" />
              {priority.charAt(0).toUpperCase() + priority.slice(1)} Priority
            </span>
          </div>
          
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground/90 mb-6 leading-tight">
            {story.headline}
          </h2>
          
          {story.image_url && (
            <div className="w-full h-48 sm:h-72 md:h-80 rounded-xl overflow-hidden mb-8 border border-border/50 shadow-sm">
              <img src={story.image_url} alt={story.headline} className="w-full h-full object-cover" />
            </div>
          )}
          
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-foreground/80">
                <FileText className="h-5 w-5 text-blue-400" />
                Original Story Summary
              </h3>
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <p className="text-base text-muted-foreground leading-relaxed whitespace-pre-wrap">{story.summary}</p>
              </div>
            </div>
            
            {story.why_it_matters && (
              <div className="bg-amber-500/5 border border-amber-500/10 rounded-xl p-5">
                <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-amber-500">
                  <Lightbulb className="h-5 w-5" />
                  Why it matters
                </h3>
                <p className="text-base text-foreground/80 leading-relaxed whitespace-pre-wrap">{story.why_it_matters}</p>
              </div>
            )}
            
            {story.url && (
              <div className="pt-4 pb-8">
                <a href={story.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-sm text-primary hover:underline font-medium">
                  Read Original Source <Globe className="h-4 w-4" />
                </a>
              </div>
            )}
          </div>
        </div>
        
        {/* Exam Analysis Area (Right) */}
        <div className="w-full md:w-[350px] lg:w-[450px] bg-muted/30 overflow-y-auto p-6 sm:p-8 flex-shrink-0">
          <div className="flex items-center gap-2 mb-8">
            <div className="h-8 w-8 rounded-lg bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20">
              <BrainCircuit className="h-4 w-4 text-emerald-500" />
            </div>
            <h3 className="text-xl font-bold tracking-tight">AI Exam Analysis</h3>
          </div>
          
          {story.exam_playbook ? (
            <div className="space-y-6">
              <div className="space-y-2">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70 font-bold flex items-center gap-1.5">
                  <Target className="h-3 w-3" /> Prelims Angle
                </span>
                <p className="text-sm text-foreground/90 leading-relaxed">{story.exam_playbook.prelims_angle}</p>
              </div>
              <div className="space-y-2">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70 font-bold flex items-center gap-1.5">
                  <BookOpen className="h-3 w-3" /> Mains Angle
                </span>
                <p className="text-sm text-foreground/90 leading-relaxed">{story.exam_playbook.mains_angle}</p>
              </div>
              <div className="space-y-2">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70 font-bold flex items-center gap-1.5">
                  <Layers className="h-3 w-3" /> Static Connect
                </span>
                <p className="text-sm text-foreground/90 leading-relaxed">{story.exam_playbook.static_connect}</p>
              </div>
              <div className="space-y-2">
                <span className="text-[10px] uppercase tracking-wider text-emerald-500 font-bold flex items-center gap-1.5">
                  <FileText className="h-3 w-3" /> Probable Question
                </span>
                <div className="bg-emerald-500/10 border border-emerald-500/20 p-4 rounded-xl shadow-sm">
                  <p className="text-sm text-foreground font-medium italic">
                    "{story.exam_playbook.probable_question}"
                  </p>
                </div>
              </div>
              <div className="space-y-2">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70 font-bold">Key Terms</span>
                <div className="flex flex-wrap gap-1.5">
                  {story.exam_playbook.key_terms.map((term, i) => (
                    <Badge key={i} variant="secondary" className="text-xs font-mono bg-background shadow-sm">
                      {term}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="pt-6 mt-4 border-t border-border/50">
                <span className="text-[10px] uppercase tracking-wider text-amber-500 font-bold flex items-center gap-1.5">
                  <Zap className="h-3 w-3" /> One Line Takeaway
                </span>
                <p className="mt-2 text-sm text-foreground/80 font-medium leading-relaxed italic">
                  {story.exam_playbook.one_line_takeaway}
                </p>
              </div>
            </div>
          ) : (
            <div className="h-64 flex flex-col items-center justify-center text-center space-y-3 opacity-50">
              <BrainCircuit className="h-12 w-12 text-muted-foreground" />
              <p className="text-sm font-medium">No exam playbook available for this story.</p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
    </>
  )
}

function SectorSection({
  sector,
  stories,
  onSelect,
  selected,
}: {
  sector: string
  stories: UPSCStory[]
  onSelect: () => void
  selected: boolean
}) {
  const meta = getSectorMeta(sector)
  const avgRelevance = stories.reduce((s, st) => s + (st.relevance_score || 0), 0) / (stories.length || 1)
  const avgPriority = stories.reduce((s, st) => s + (st.priority_score || 0), 0) / (stories.length || 1)

  return (
    <button
      onClick={onSelect}
      className={cn(
        "w-full text-left rounded-xl border p-3 sm:p-4 transition-all duration-300 sm:hover:-translate-y-0.5 sm:hover:shadow-lg active:scale-[0.98] sm:active:scale-100",
        selected
          ? "border-primary/30 bg-primary/5 shadow-md"
          : "border-border/50 bg-card hover:border-border/80"
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border ${meta.color} shrink-0`}>
            {meta.icon}
            {meta.label}
          </span>
          <span className="text-xs font-medium text-foreground/80 truncate capitalize">{sector}</span>
        </div>
        <span className="text-[10px] font-mono text-muted-foreground/50 shrink-0 ml-2">{stories.length} stories</span>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 text-[10px] text-muted-foreground/60">
        <span className="flex items-center gap-1">
          Relevance: {Math.round(avgRelevance * 100)}%
        </span>
        <span className="hidden sm:inline text-muted-foreground/20">·</span>
        <span className="flex items-center gap-1">
          Priority: {Math.round(avgPriority * 100)}%
        </span>
        <span className="hidden sm:inline text-muted-foreground/20">·</span>
        <span className="flex items-center gap-1">
          <BrainCircuit className="h-2.5 w-2.5 shrink-0" />
          {stories.filter((s) => s.exam_playbook).length} analyzed
        </span>
      </div>
    </button>
  )
}

export default function Home() {
  const [stories, setStories] = useState<UPSCStory[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedSector, setSelectedSector] = useState<string | null>(null)
  const [stats, setStats] = useState({ total: 0, analyzed: 0 })

  async function load() {
    try {
      setLoading(true)
      const data = await fetchUPSCStories(50, 0)
      setStories(data.stories)
      setStats({ total: data.total_count, analyzed: data.has_exam_playbook })
    } catch (err) {
      console.error("Failed to load UPSC stories:", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 120000)
    return () => clearInterval(interval)
  }, [])

  const query = searchQuery.toLowerCase()

  // Group by sector
  const sectorGroups: Record<string, UPSCStory[]> = {}
  stories.forEach(story => {
    const rawSector = mapStoryToSector(story)
    const sector = rawSector.charAt(0).toUpperCase() + rawSector.slice(1).toLowerCase()
    if (!sectorGroups[sector]) sectorGroups[sector] = []
    sectorGroups[sector].push(story)
  })

  const displayStories = selectedSector
    ? (sectorGroups[selectedSector] || [])
    : stories

  const filteredStories = query
    ? displayStories.filter(
        (s) =>
          s.headline.toLowerCase().includes(query) ||
          s.summary.toLowerCase().includes(query) ||
          (s.subtopics && s.subtopics.some((st) => st.toLowerCase().includes(query))) ||
          (s.sectors && s.sectors.some((sec) => sec.toLowerCase().includes(query))) ||
          (s.gs_paper && s.gs_paper.toLowerCase().includes(query))
      )
    : displayStories

  const avgRelevance = stories.length > 0
    ? stories.reduce((s, st) => s + (st.relevance_score || 0), 0) / stories.length
    : 0
  const highPriorityCount = stories.filter((s) => (s.priority_score || 0) >= 0.6).length
  const sectorsCount = Object.keys(sectorGroups).length

  if (loading && stories.length === 0) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 space-y-6">
          <div className="animate-pulse space-y-4">
            <div className="bg-muted h-8 w-40 sm:w-48 rounded" />
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="bg-muted h-20 rounded-xl" />
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="animate-pulse rounded-xl border border-border/50 p-3.5 sm:p-4 space-y-3">
                  <div className="bg-muted h-4 sm:h-5 w-3/4 rounded" />
                  <div className="bg-muted/60 h-2.5 sm:h-3 w-full rounded" />
                  <div className="bg-muted/60 h-2.5 sm:h-3 w-5/6 rounded" />
                </div>
              ))}
            </div>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 space-y-6 sm:space-y-8">
        <ErrorBoundary>
        {/* Hero */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
          <div className="h-10 w-10 rounded-xl bg-amber-500/15 flex items-center justify-center shrink-0">
            <GraduationCap className="h-5 w-5 text-amber-400" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight">
              UPSC Current Affairs <span className="text-amber-400">Intelligence</span>
            </h1>
            <p className="text-xs sm:text-sm text-muted-foreground/70 mt-0.5">
              Sector-aware filtering · Exam-focused analysis · Priority-ranked stories
            </p>
          </div>
        </div>


        {/* Search */}
        <div className="relative w-full sm:max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search stories, subtopics, sectors..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-10 text-sm w-full"
          />
        </div>

        {/* Sector selector */}
        <div className="-mx-4 sm:mx-0 overflow-x-auto sm:overflow-visible px-4 sm:px-0 pb-1 sm:pb-0">
          <div className="flex sm:grid sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 sm:gap-3 min-w-max sm:min-w-0">
            <button
              onClick={() => setSelectedSector(null)}
              className={cn(
                "rounded-xl border p-3 text-center transition-all duration-300 sm:hover:-translate-y-0.5 sm:hover:shadow-lg active:scale-[0.98] sm:active:scale-100 min-w-[120px] sm:min-w-0 w-full",
                !selectedSector
                  ? "border-primary/30 bg-primary/5 shadow-md"
                  : "border-border/50 bg-card hover:border-border/80"
              )}
            >
              <span className="text-xs font-medium text-foreground/80">All Sectors</span>
              <p className="text-[10px] text-muted-foreground/50 mt-1">{stories.length} stories</p>
            </button>
            {Object.keys(sectorGroups).sort().map((sector) => (
              <SectorSection
                key={sector}
                sector={sector}
                stories={sectorGroups[sector]}
                onSelect={() => setSelectedSector(selectedSector === sector ? null : sector)}
                selected={selectedSector === sector}
              />
            ))}
          </div>
        </div>

        {/* Stories grid */}
        {filteredStories.length === 0 ? (
          <div className="text-center py-12 sm:py-16">
            <BookMarked className="h-8 w-8 sm:h-10 sm:w-10 mx-auto mb-3 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground/60">
              {searchQuery
                ? `No stories match "${searchQuery}"`
                : "No UPSC-relevant stories found. The pipeline may still be processing."}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 items-stretch">
            {filteredStories.map((story, i) => (
              <StoryCard key={`${story.headline}-${i}`} story={story} index={i} />
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="border-t border-border/50 pt-5 sm:pt-6 text-center">
          <div className="flex items-center justify-center gap-3 sm:gap-4 text-[10px] text-muted-foreground/40 flex-wrap">
            <span className="flex items-center gap-1">
              <Zap className="h-3 w-3 shrink-0" /> Local ML Filtering
            </span>
            <span className="flex items-center gap-1">
              <BrainCircuit className="h-3 w-3 shrink-0" /> AI Playbook
            </span>
            <span className="flex items-center gap-1">
              <BookOpen className="h-3 w-3 shrink-0" /> Sector-Aware
            </span>
            <span className="flex items-center gap-1">
              <Scale className="h-3 w-3 shrink-0" /> UPSC-Aligned
            </span>
          </div>
        </div>
        </ErrorBoundary>
      </main>
    </div>
  )
}
