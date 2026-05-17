export interface Story {
  headline: string
  summary: string
  why_it_matters: string
  url?: string
  sectors?: string[]
  score?: number
  article_count?: number
  source?: string[]
  sector_summary?: string
  trending_score?: number
  image_url?: string
  // UPSC fields
  relevance_score?: number
  priority_score?: number
  novelty_score?: number
  gs_paper?: string
  subtopics?: string[]
  exam_playbook?: ExamPlaybook | null
}

export interface ExamPlaybook {
  is_relevant: boolean
  relevance_score: number
  gs_paper: string
  subtopics: string[]
  prelims_angle: string
  mains_angle: string
  probable_question: string
  static_connect: string
  key_terms: string[]
  one_line_takeaway: string
}

export interface UPSCStory extends Story {
  relevance_score: number
  priority_score: number
  gs_paper: string
  subtopics: string[]
  exam_playbook?: ExamPlaybook | null
}

export interface UPSCResponse {
  stories: UPSCStory[]
  gs_groups: Record<string, UPSCStory[]>
  total_count: number
  has_exam_playbook: number
}

export interface MarketDataPoint {
  ticker: string
  name: string
  price: number
  change: number
  change_pct: number
  market_cap?: string
  sector: string
}

export interface SectorSummary {
  sector: string
  summary: string
  headline_count: number
  created_at: string
}

export interface SourceDiversity {
  source: string
  count: number
  pct: number
}

export interface Briefing {
  content: string
  created_at: string
}

export interface StoryReview {
  story_title: string
  story_url?: string
  correct_section: "yes" | "no"
  suggested_section?: string
  summary_concise: "yes" | "no"
  picture_available: "yes" | "no"
  comment?: string
}

export const SECTORS = ["Markets", "Tech", "Geopolitics", "Energy", "India", "Sports", "General"] as const
export type Sector = (typeof SECTORS)[number]
