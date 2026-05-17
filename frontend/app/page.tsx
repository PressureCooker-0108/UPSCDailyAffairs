"use client"

import { useEffect, useState } from "react"
import { Header } from "@/components/header"
import { ErrorBoundary } from "@/components/error-boundary"
import type { UPSCStory, ExamPlaybook } from "@/types/story"
import { fetchUPSCStories } from "@/lib/api"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
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
  ChevronDown,
  ChevronUp,
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

const GS_META: Record<string, { label: string; icon: React.ReactNode; color: string; border: string }> = {
  "GS Paper I": {
    label: "GS I",
    icon: <Landmark className="h-3.5 w-3.5" />,
    color: "text-blue-400 bg-blue-500/10 border-blue-500/20",
    border: "border-l-blue-500/40",
  },
  "GS Paper II": {
    label: "GS II",
    icon: <Gavel className="h-3.5 w-3.5" />,
    color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    border: "border-l-emerald-500/40",
  },
  "GS Paper III": {
    label: "GS III",
    icon: <Cog className="h-3.5 w-3.5" />,
    color: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    border: "border-l-amber-500/40",
  },
  "GS Paper IV": {
    label: "GS IV",
    icon: <Users className="h-3.5 w-3.5" />,
    color: "text-purple-400 bg-purple-500/10 border-purple-500/20",
    border: "border-l-purple-500/40",
  },
  "Prelims": {
    label: "Prelims",
    icon: <Target className="h-3.5 w-3.5" />,
    color: "text-rose-400 bg-rose-500/10 border-rose-500/20",
    border: "border-l-rose-500/40",
  },
  "Unmapped": {
    label: "General",
    icon: <Globe className="h-3.5 w-3.5" />,
    color: "text-slate-400 bg-slate-500/10 border-slate-500/20",
    border: "border-l-slate-500/40",
  },
}

const PRIORITY_COLORS: Record<string, string> = {
  critical: "text-red-400 bg-red-500/10",
  high: "text-orange-400 bg-orange-500/10",
  medium: "text-yellow-400 bg-yellow-500/10",
  low: "text-slate-400 bg-slate-500/10",
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

function ExamPlaybookCard({ playbook }: { playbook: ExamPlaybook }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="mt-3 rounded-lg border border-amber-500/15 bg-amber-500/5 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2.5 text-xs font-medium text-amber-400/80 hover:text-amber-300 active:text-amber-200 transition-colors min-h-[36px]"
      >
        <span className="flex items-center gap-1.5">
          <BrainCircuit className="h-3.5 w-3.5 shrink-0" />
          Exam Playbook
        </span>
        {expanded ? <ChevronUp className="h-3 w-3 shrink-0" /> : <ChevronDown className="h-3 w-3 shrink-0" />}
      </button>
      {expanded && (
        <div className="px-3 pb-3 space-y-3 text-xs">
          <div className="space-y-3 sm:space-y-0 sm:grid sm:grid-cols-2 sm:gap-3">
            <div className="space-y-1">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground/60 font-semibold">Prelims Angle</span>
              <p className="text-foreground/80 leading-relaxed text-[11px] sm:text-xs">{playbook.prelims_angle}</p>
            </div>
            <div className="space-y-1">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground/60 font-semibold">Mains Angle</span>
              <p className="text-foreground/80 leading-relaxed text-[11px] sm:text-xs">{playbook.mains_angle}</p>
            </div>
          </div>
          <div className="space-y-1">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground/60 font-semibold">Probable Question</span>
            <p className="text-foreground/90 font-medium italic leading-relaxed text-[11px] sm:text-xs">
              &ldquo;{playbook.probable_question}&rdquo;
            </p>
          </div>
          <div className="space-y-1">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground/60 font-semibold">Static Connect</span>
            <p className="text-foreground/70 leading-relaxed text-[11px] sm:text-xs">{playbook.static_connect}</p>
          </div>
          <div className="flex flex-wrap gap-1">
            {playbook.key_terms.map((term, i) => (
              <Badge key={i} variant="outline" className="text-[9px] px-1.5 py-0.5 h-auto text-amber-300/80 border-amber-500/20 bg-amber-500/10 font-mono">
                {term}
              </Badge>
            ))}
          </div>
          <div className="pt-1.5 border-t border-amber-500/10">
            <p className="text-[11px] sm:text-xs text-foreground/60 italic leading-relaxed">
              {playbook.one_line_takeaway}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

function StoryCard({ story, index }: { story: UPSCStory; index: number }) {
  const gsMeta = GS_META[story.gs_paper] || GS_META["Unmapped"]
  const priority = getPriorityLabel(story.priority_score || 0)
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className={cn(
        "group relative rounded-xl border border-border/50 bg-card transition-all duration-300 hover:shadow-lg hover:border-primary/20 sm:hover:-translate-y-0.5 animate-fade-in overflow-hidden",
        gsMeta.border,
        "border-l-2"
      )}
      style={{ animationDelay: `${Math.min(index * 0.05, 1)}s` }}
    >
      <div className="p-3.5 sm:p-5">
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
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border ${gsMeta.color} shrink-0`}>
            {gsMeta.icon}
            {gsMeta.label}
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

        <p className="text-[11px] sm:text-xs text-muted-foreground/70 leading-relaxed line-clamp-2 mb-2.5">
          {story.summary}
        </p>

        {story.why_it_matters && (
          <div className="flex items-start gap-1.5 mb-2.5">
            <Lightbulb className="h-3 w-3 text-amber-400/60 shrink-0 mt-0.5" />
            <p className="text-[10px] text-amber-400/70 leading-relaxed">{story.why_it_matters}</p>
          </div>
        )}

        <div className="space-y-1 mb-2.5">
          <ScoreBar label="Relevance" value={story.relevance_score || 0} />
          <ScoreBar label="Priority" value={story.priority_score || 0} />
          {story.novelty_score !== undefined && (
            <ScoreBar label="Novelty" value={story.novelty_score} />
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
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

        {story.exam_playbook && (
          <>
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-3 w-full py-2 rounded-md text-[10px] font-medium text-muted-foreground/50 hover:text-foreground/70 active:text-foreground/90 border border-border/30 hover:border-border/60 active:border-border/80 transition-colors min-h-[36px]"
            >
              {expanded ? "Hide Analysis" : "Show Exam Analysis"}
            </button>
            {expanded && <ExamPlaybookCard playbook={story.exam_playbook} />}
          </>
        )}
      </div>
    </div>
  )
}

function GSSection({
  paper,
  stories,
  onSelect,
  selected,
}: {
  paper: string
  stories: UPSCStory[]
  onSelect: () => void
  selected: boolean
}) {
  const meta = GS_META[paper] || GS_META["Unmapped"]
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
          <span className="text-xs font-medium text-foreground/80 truncate">{paper}</span>
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
  const [gsGroups, setGsGroups] = useState<Record<string, UPSCStory[]>>({})
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedPaper, setSelectedPaper] = useState<string | null>(null)
  const [stats, setStats] = useState({ total: 0, analyzed: 0 })

  async function load() {
    try {
      setLoading(true)
      const data = await fetchUPSCStories(50, 0)
      setStories(data.stories)
      setGsGroups(data.gs_groups)
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
  const displayStories = selectedPaper
    ? (gsGroups[selectedPaper] || [])
    : stories

  const filteredStories = query
    ? displayStories.filter(
        (s) =>
          s.headline.toLowerCase().includes(query) ||
          s.summary.toLowerCase().includes(query) ||
          (s.subtopics && s.subtopics.some((st) => st.toLowerCase().includes(query))) ||
          (s.gs_paper && s.gs_paper.toLowerCase().includes(query))
      )
    : displayStories

  const avgRelevance = stories.length > 0
    ? stories.reduce((s, st) => s + (st.relevance_score || 0), 0) / stories.length
    : 0
  const highPriorityCount = stories.filter((s) => (s.priority_score || 0) >= 0.6).length
  const papersWithStories = Object.keys(gsGroups).length

  const paperOrder = ["GS Paper I", "GS Paper II", "GS Paper III", "GS Paper IV", "Prelims", "Unmapped"]

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
              Syllabus-aware filtering · Exam-focused analysis · Priority-ranked stories
            </p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-3">
          <Card className="border-border/50">
            <CardContent className="p-3 sm:p-4">
              <div className="flex items-center justify-between">
                <div className="min-w-0">
                  <p className="text-[9px] sm:text-[10px] uppercase tracking-wider text-muted-foreground/50 font-semibold">Total Stories</p>
                  <p className="text-xl sm:text-2xl font-bold mt-0.5">{stats.total}</p>
                </div>
                <FileText className="h-4 w-4 sm:h-5 sm:w-5 text-muted-foreground/30 shrink-0" />
              </div>
            </CardContent>
          </Card>
          <Card className="border-border/50">
            <CardContent className="p-3 sm:p-4">
              <div className="flex items-center justify-between">
                <div className="min-w-0">
                  <p className="text-[9px] sm:text-[10px] uppercase tracking-wider text-muted-foreground/50 font-semibold">GS Papers</p>
                  <p className="text-xl sm:text-2xl font-bold mt-0.5">{papersWithStories}</p>
                </div>
                <Layers className="h-4 w-4 sm:h-5 sm:w-5 text-muted-foreground/30 shrink-0" />
              </div>
            </CardContent>
          </Card>
          <Card className="border-border/50">
            <CardContent className="p-3 sm:p-4">
              <div className="flex items-center justify-between">
                <div className="min-w-0">
                  <p className="text-[9px] sm:text-[10px] uppercase tracking-wider text-muted-foreground/50 font-semibold">High Priority</p>
                  <p className="text-xl sm:text-2xl font-bold mt-0.5">{highPriorityCount}</p>
                </div>
                <TrendingUp className="h-4 w-4 sm:h-5 sm:w-5 text-amber-400/50 shrink-0" />
              </div>
            </CardContent>
          </Card>
          <Card className="border-border/50">
            <CardContent className="p-3 sm:p-4">
              <div className="flex items-center justify-between">
                <div className="min-w-0">
                  <p className="text-[9px] sm:text-[10px] uppercase tracking-wider text-muted-foreground/50 font-semibold">AI Analyzed</p>
                  <p className="text-xl sm:text-2xl font-bold mt-0.5">{stats.analyzed}</p>
                </div>
                <BrainCircuit className="h-4 w-4 sm:h-5 sm:w-5 text-emerald-400/50 shrink-0" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Relevance bar */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground/60">
          <span className="whitespace-nowrap">Avg. Relevance</span>
          <div className="flex-1 h-2 rounded-full bg-border/50 overflow-hidden max-w-[200px]">
            <div
              className="h-full rounded-full bg-gradient-to-r from-red-500 via-amber-500 to-green-500 transition-all duration-1000"
              style={{ width: `${Math.round(avgRelevance * 100)}%` }}
            />
          </div>
          <span className="font-mono text-foreground/70 tabular-nums">{Math.round(avgRelevance * 100)}%</span>
        </div>

        {/* Search */}
        <div className="relative w-full sm:max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search stories, subtopics, GS papers..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-10 text-sm w-full"
          />
        </div>

        {/* GS Paper selector */}
        <div className="-mx-4 sm:mx-0 overflow-x-auto sm:overflow-visible px-4 sm:px-0 pb-1 sm:pb-0">
          <div className="flex sm:grid sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 sm:gap-3 min-w-max sm:min-w-0">
            <button
              onClick={() => setSelectedPaper(null)}
              className={cn(
                "rounded-xl border p-3 text-center transition-all duration-300 sm:hover:-translate-y-0.5 sm:hover:shadow-lg active:scale-[0.98] sm:active:scale-100 min-w-[120px] sm:min-w-0 w-full",
                !selectedPaper
                  ? "border-primary/30 bg-primary/5 shadow-md"
                  : "border-border/50 bg-card hover:border-border/80"
              )}
            >
              <span className="text-xs font-medium text-foreground/80">All Papers</span>
              <p className="text-[10px] text-muted-foreground/50 mt-1">{stories.length} stories</p>
            </button>
            {paperOrder.filter((p) => gsGroups[p] && gsGroups[p].length > 0).map((paper) => (
              <GSSection
                key={paper}
                paper={paper}
                stories={gsGroups[paper]}
                onSelect={() => setSelectedPaper(selectedPaper === paper ? null : paper)}
                selected={selectedPaper === paper}
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
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
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
              <BrainCircuit className="h-3 w-3 shrink-0" /> Gemini Analysis
            </span>
            <span className="flex items-center gap-1">
              <BookOpen className="h-3 w-3 shrink-0" /> Syllabus-Aware
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
