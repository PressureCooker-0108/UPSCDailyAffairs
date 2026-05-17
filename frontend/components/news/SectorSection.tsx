"use client"

import { Story } from "@/types/story"
import Link from "next/link"
import { ArrowRight } from "lucide-react"

const SECTOR_ICONS: Record<string, string> = {
  Markets: "📊",
  Tech: "💻",
  Geopolitics: "🌍",
  Energy: "⚡",
  India: "🇮🇳",
  Sports: "🏆",
  General: "📰",
}

export function SectorSection({ stories }: { stories: Story[] }) {
  const sectorGroups: Record<string, Story[]> = {}
  const seenSectors = new Set<string>()

  for (const story of stories) {
    for (const sector of story.sectors || ["General"]) {
      if (!sectorGroups[sector]) sectorGroups[sector] = []
      sectorGroups[sector].push(story)
      seenSectors.add(sector)
    }
  }

  const displayOrder = ["Markets", "Tech", "Geopolitics", "Energy", "India", "Sports", "General"]
  const activeSectors = displayOrder.filter((s) => seenSectors.has(s))

  if (activeSectors.length === 0) return null

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold tracking-tight">Sector Breakdown</h2>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {activeSectors.map((sector) => {
          const sectorStories = sectorGroups[sector] || []
          return (
            <Link
              key={sector}
              href={`/sectors/${sector.toLowerCase()}`}
              className="group relative rounded-xl border border-border/50 bg-card p-5 transition-all duration-300 hover:shadow-lg hover:border-primary/30 hover:-translate-y-0.5"
            >
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <span className="text-xl">{SECTOR_ICONS[sector] || "📰"}</span>
                  <h3 className="font-semibold text-lg group-hover:text-primary transition-colors">
                    {sector}
                  </h3>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>

              <ul className="space-y-2">
                {sectorStories.slice(0, 4).map((story, i) => (
                  <li key={i}>
                    <p className="text-sm leading-snug text-muted-foreground line-clamp-2 group-hover:text-foreground/80 transition-colors">
                      {story.headline}
                    </p>
                  </li>
                ))}
                {sectorStories.length > 4 && (
                  <li className="pt-1">
                    <span className="text-xs text-primary/70 group-hover:text-primary transition-colors">
                      +{sectorStories.length - 4} more stories...
                    </span>
                  </li>
                )}
              </ul>
            </Link>
          )
        })}
      </div>
    </section>
  )
}
