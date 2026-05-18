import { UPSCResponse } from "@/types/story"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8002"

export async function submitReview(review: {
  story_title: string
  story_url?: string
  // Core review fields
  is_relevant: "yes" | "no"
  sector_correct: "yes" | "no"
  suggested_sector?: string
  gs_paper_correct: "yes" | "no"
  suggested_gs_paper?: string
  suggestions?: string
  // Legacy fields (backward compat)
  correct_section?: "yes" | "no"
  suggested_section?: string
  summary_concise?: "yes" | "no"
  picture_available?: "yes" | "no"
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

// ── UPSC Intelligence API ──

export async function fetchUPSCStories(limit?: number, minRelevance?: number): Promise<UPSCResponse> {
  try {
    const params = new URLSearchParams()
    if (limit) params.set("limit", String(limit))
    if (minRelevance) params.set("min_relevance", String(minRelevance))
    const url = `${API_URL}/upsc${params.toString() ? "?" + params.toString() : ""}`
    const res = await fetch(url, { cache: "no-store" })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    // Map backend 'title' → frontend 'headline' like other fetch functions
    const mappedStories = (data.stories || []).map((s: any) => ({
      ...s,
      headline: s.title || s.headline || "Untitled",
    }))
    // Rebuild gs_groups with mapped stories
    const gsGroups: Record<string, any[]> = {}
    for (const story of mappedStories) {
      const paper = story.gs_paper || "Unmapped"
      if (!gsGroups[paper]) gsGroups[paper] = []
      gsGroups[paper].push(story)
    }
    return {
      stories: mappedStories,
      gs_groups: gsGroups,
      total_count: data.total_count || mappedStories.length,
      has_exam_playbook: data.has_exam_playbook || 0,
    }
  } catch (err) {
    console.error("Failed to fetch UPSC stories:", err)
    return { stories: [], gs_groups: {}, total_count: 0, has_exam_playbook: 0 }
  }
}
