"use client"

import { Story } from "@/types/story"
import Link from "next/link"

interface SectorHeatmapProps {
  sectorGroups: Record<string, Story[]>
  activeSectors: string[]
}

// RGB values for each sector's accent color (used in inline styles to avoid
// Tailwind's JIT limitation with dynamically constructed class names).
const SECTOR_RGB: Record<string, string> = {
  Markets:     "16, 185, 129",   // emerald-500
  Tech:        "59, 130, 246",   // blue-500
  Geopolitics: "239, 68, 68",    // red-500
  Energy:      "245, 158, 11",   // amber-500
  India:       "249, 115, 22",   // orange-500
  Sports:      "168, 85, 247",   // purple-500
  General:     "100, 116, 139",  // slate-500
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

export function SectorHeatmap({ sectorGroups, activeSectors }: SectorHeatmapProps) {
  if (activeSectors.length === 0) return null

  // Compute stats per sector
  const sectorStats = activeSectors.map((sector) => {
    const stories = sectorGroups[sector] || []
    const count = stories.length
    const avgScore =
      count > 0
        ? stories.reduce((sum, s) => sum + (s.score ?? 0), 0) / count
        : 0
    return { sector, count, avgScore, stories }
  })

  // Normalize counts for proportional sizing (0.5–2.0 multiplier)
  const maxCount = Math.max(...sectorStats.map((s) => s.count), 1)
  const maxScore = Math.max(...sectorStats.map((s) => s.avgScore), 1)

  function getSpanClass(count: number): string {
    const ratio = count / maxCount
    if (ratio >= 0.8) return "md:col-span-2 md:row-span-2"
    if (ratio >= 0.4) return "md:col-span-2 md:row-span-1"
    if (ratio >= 0.2) return "md:col-span-1 md:row-span-2"
    return "md:col-span-1 md:row-span-1"
  }

  // Saturation/opacity based on normalized score (0-1), used in inline styles
  function bgOpacity(score: number): number {
    return Math.max(0.04, Math.min(0.25, score / 100))
  }

  // Secondary heatmap grid — a denser overlay for more granular intensity
  function heatmapOverlay(score: number, rgb: string): string {
    const opacity = Math.max(0.06, Math.min(0.35, (score / 100) * 0.35))
    return `repeating-linear-gradient(45deg, rgba(${rgb}, ${opacity}) 0px, rgba(${rgb}, ${opacity}) 1px, transparent 1px, transparent 6px)`
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
        <h3 className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground/60">
          Sector Heatmap
        </h3>
        <div className="h-px flex-1 bg-border/60" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 auto-rows-[100px]">
        {sectorStats
          .sort((a, b) => b.avgScore - a.avgScore)
          .map(({ sector, count, avgScore, stories }) => {
            const rgb = SECTOR_RGB[sector] || SECTOR_RGB.General
            const icon = SECTOR_ICONS[sector] || "📰"
            const normalizedScore = maxScore > 0 ? (avgScore / maxScore) * 100 : 0
            const spanClass = getSpanClass(count)
            const opacity = bgOpacity(normalizedScore)

            return (
              <Link
                key={sector}
                href={`/sectors/${sector.toLowerCase()}`}
                className={`group relative overflow-hidden rounded-xl border transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 ${spanClass}`}
                style={{ borderColor: `rgba(${rgb}, 0.3)` }}
              >
                {/* Background layer — inline style to survive Tailwind purging */}
                <div
                  className="absolute inset-0 transition-opacity duration-500"
                  style={{ backgroundColor: `rgba(${rgb}, ${opacity})` }}
                />

                {/* Heatmap grid overlay — denser diagonal lines at higher intensity */}
                {normalizedScore > 20 && (
                  <div
                    className="absolute inset-0 transition-opacity duration-700"
                    style={{ backgroundImage: heatmapOverlay(normalizedScore, rgb) }}
                  />
                )}

                {/* Score intensity bar at bottom */}
                <div
                  className="absolute bottom-0 left-0 h-[3px] transition-all duration-700 ease-out group-hover:h-[4px]"
                  style={{
                    width: `${Math.min(normalizedScore, 100)}%`,
                    backgroundColor: `rgba(${rgb}, 0.8)`,
                  }}
                />

                <div className="relative z-10 h-full p-4 flex flex-col justify-between">
                  {/* Top row: icon + sector name */}
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">{icon}</span>
                      <span className="font-semibold text-sm group-hover:text-foreground transition-colors">
                        {sector}
                      </span>
                    </div>
                    <span
                      className="text-[10px] font-mono font-bold transition-opacity duration-300"
                      style={{
                        color: `rgba(${rgb}, 1)`,
                        opacity: normalizedScore >= 70 ? 1 : 0,
                      }}
                    >
                      {avgScore.toFixed(0)}
                    </span>
                    {/* Hover-only score badge for lower-scoring sectors */}
                    {normalizedScore < 70 && (
                      <span
                        className="text-[10px] font-mono font-bold opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                        style={{ color: `rgba(${rgb}, 1)` }}
                      >
                        {avgScore.toFixed(0)}
                      </span>
                    )}
                  </div>

                  {/* Bottom row: metrics */}
                  <div className="flex items-end justify-between">
                    <div className="space-y-0.5">
                      <p className="text-2xl font-bold tracking-tight">{count}</p>
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
                        {count === 1 ? "story" : "stories"}
                      </p>
                    </div>

                    {/* Mini score bar chart (sparkline-like) */}
                    <div className="hidden sm:flex items-end gap-[2px] h-8">
                      {stories.slice(0, 8).map((s, i) => {
                        const h = Math.max(4, ((s.score ?? 0) / maxScore) * 32)
                        return (
                          <div
                            key={i}
                            className="w-[4px] rounded-t-sm transition-all duration-300 opacity-60 group-hover:opacity-100"
                            style={{ height: h, backgroundColor: `rgba(${rgb}, 0.7)` }}
                          />
                        )
                      })}
                    </div>
                  </div>
                </div>
              </Link>
            )
          })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-[10px] text-muted-foreground/60">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-[3px] rounded-full" style={{ backgroundColor: "rgba(16, 185, 129, 0.6)" }} />
          <span>High signal</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-[3px] rounded-full" style={{ backgroundColor: "rgba(245, 158, 11, 0.6)" }} />
          <span>Moderate</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-[3px] rounded-full bg-muted-foreground/20" />
          <span>Low</span>
        </div>
        <div className="flex-1" />
        <span>Tile size ∝ story count · Color intensity ∝ avg. score</span>
      </div>
    </section>
  )
}
