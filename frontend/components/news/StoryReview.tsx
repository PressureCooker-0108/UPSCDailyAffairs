"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

import { submitReview } from "@/lib/api"
import { MessageSquare, ThumbsUp, Loader2, AlertTriangle, MapPin, BookOpen, Lightbulb, Sparkles } from "lucide-react"

interface StoryReviewProps {
  storyTitle: string
  storyUrl?: string
  currentSector?: string
  currentGsPaper?: string
}

const SECTORS = [
  "Economy", "Geopolitics", "Politics", "Tech", "Environment",
  "Social Issues", "Security", "Culture", "Agriculture", "Science & Tech",
  "Governance", "International Relations",
]

const GS_PAPERS = [
  "GS Paper I", "GS Paper II", "GS Paper III", "GS Paper IV", "Prelims",
]

export function StoryReview({ storyTitle, storyUrl, currentSector, currentGsPaper }: StoryReviewProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  // Core review fields
  const [isRelevant, setIsRelevant] = useState<"yes" | "no" | "">("")
  const [sectorCorrect, setSectorCorrect] = useState<"yes" | "no" | "">("")
  const [suggestedSector, setSuggestedSector] = useState("")
  const [gsPaperCorrect, setGsPaperCorrect] = useState<"yes" | "no" | "">("")
  const [suggestedGsPaper, setSuggestedGsPaper] = useState("")
  const [suggestions, setSuggestions] = useState("")

  const [error, setError] = useState("")

  const handleSubmit = async () => {
    setError("")
    if (!isRelevant || !sectorCorrect || !gsPaperCorrect) {
      setError("Please answer all required questions.")
      return
    }

    setSubmitting(true)
    const result = await submitReview({
      story_title: storyTitle,
      story_url: storyUrl,
      is_relevant: isRelevant,
      sector_correct: sectorCorrect,
      suggested_sector: sectorCorrect === "no" ? suggestedSector : undefined,
      gs_paper_correct: gsPaperCorrect,
      suggested_gs_paper: gsPaperCorrect === "no" ? suggestedGsPaper : undefined,
      suggestions: suggestions || undefined,
    })

    setSubmitting(false)
    if (result) {
      setSubmitted(true)
    } else {
      setError("Failed to submit. Please try again.")
    }
  }

  const handleReset = () => {
    setIsOpen(false)
    setSubmitted(false)
    setIsRelevant("")
    setSectorCorrect("")
    setSuggestedSector("")
    setGsPaperCorrect("")
    setSuggestedGsPaper("")
    setSuggestions("")
    setError("")
  }

  if (submitted) {
    return (
      <div className="rounded-xl border border-emerald-500/20 bg-gradient-to-br from-emerald-500/5 to-emerald-500/[0.02] p-5 text-center">
        <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/10">
          <ThumbsUp className="h-5 w-5 text-emerald-500" />
        </div>
        <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
          Thank you for your feedback!
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Your review helps train the ML model to better filter UPSC-relevant stories.
        </p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-3 text-xs"
          onClick={handleReset}
        >
          Submit another review
        </Button>
      </div>
    )
  }

  return (
    <div className="border-t border-border/40 pt-4">
      <Button
        variant="ghost"
        size="sm"
        className="gap-2 text-xs text-muted-foreground hover:text-foreground"
        onClick={() => setIsOpen(!isOpen)}
      >
        <MessageSquare className="h-3.5 w-3.5" />
        {isOpen ? "Close review" : "Review this story"}
      </Button>

      {isOpen && (
        <div className="mt-3 space-y-5 rounded-xl border border-border/40 bg-gradient-to-br from-muted/30 to-muted/10 p-5">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
            </div>
            <p className="text-xs font-semibold text-foreground/70 uppercase tracking-wider">
              Help Improve the ML Model
            </p>
          </div>

          {/* ── Question 1: Is this story relevant to UPSC? ── */}
          <div className="space-y-2.5 rounded-lg border border-border/30 bg-background/50 p-4">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <Label className="text-sm font-medium">
                  Is this story relevant for UPSC exam preparation?
                  <span className="text-red-400 ml-1">*</span>
                </Label>
                <p className="text-[10px] text-muted-foreground/60 mt-0.5">
                  Would you expect to see this in a UPSC current affairs compilation?
                </p>
              </div>
            </div>
            <RadioGroup
              value={isRelevant}
              onValueChange={(v) => setIsRelevant(v as "yes" | "no")}
              className="flex gap-4 pt-1"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="yes" id="ir-yes" className="h-4 w-4" />
                <Label htmlFor="ir-yes" className="text-xs cursor-pointer font-medium text-emerald-600 dark:text-emerald-400">Yes, relevant</Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="no" id="ir-no" className="h-4 w-4" />
                <Label htmlFor="ir-no" className="text-xs cursor-pointer font-medium text-red-500">No, not relevant</Label>
              </div>
            </RadioGroup>
          </div>

          {/* ── Question 2: Is the sector mapping correct? ── */}
          <div className="space-y-2.5 rounded-lg border border-border/30 bg-background/50 p-4">
            <div className="flex items-start gap-2">
              <MapPin className="h-4 w-4 text-blue-400 shrink-0 mt-0.5" />
              <div>
                <Label className="text-sm font-medium">
                  Is the sector mapping correct?
                  <span className="text-red-400 ml-1">*</span>
                </Label>
                <p className="text-[10px] text-muted-foreground/60 mt-0.5">
                  Currently mapped to: <span className="font-medium text-foreground/80">{currentSector || "Unknown"}</span>
                </p>
              </div>
            </div>
            <RadioGroup
              value={sectorCorrect}
              onValueChange={(v) => setSectorCorrect(v as "yes" | "no")}
              className="flex gap-4 pt-1"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="yes" id="sc-yes" className="h-4 w-4" />
                <Label htmlFor="sc-yes" className="text-xs cursor-pointer font-medium text-emerald-600 dark:text-emerald-400">Yes, correct</Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="no" id="sc-no" className="h-4 w-4" />
                <Label htmlFor="sc-no" className="text-xs cursor-pointer font-medium text-red-500">No, wrong</Label>
              </div>
            </RadioGroup>

            {sectorCorrect === "no" && (
              <div className="pt-2">
                <Label className="text-xs font-medium text-muted-foreground">
                  Which sector should it be in?
                </Label>
                <Select value={suggestedSector} onValueChange={setSuggestedSector}>
                  <SelectTrigger className="mt-1.5 h-9 text-xs">
                    <SelectValue placeholder="Select correct sector..." />
                  </SelectTrigger>
                  <SelectContent>
                    {SECTORS.map((s) => (
                      <SelectItem key={s} value={s} className="text-xs">
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* ── Question 3: Is the GS paper mapping correct? ── */}
          <div className="space-y-2.5 rounded-lg border border-border/30 bg-background/50 p-4">
            <div className="flex items-start gap-2">
              <BookOpen className="h-4 w-4 text-purple-400 shrink-0 mt-0.5" />
              <div>
                <Label className="text-sm font-medium">
                  Is the GS paper mapping correct?
                  <span className="text-red-400 ml-1">*</span>
                </Label>
                <p className="text-[10px] text-muted-foreground/60 mt-0.5">
                  Currently mapped to: <span className="font-medium text-foreground/80">{currentGsPaper || "Unknown"}</span>
                </p>
              </div>
            </div>
            <RadioGroup
              value={gsPaperCorrect}
              onValueChange={(v) => setGsPaperCorrect(v as "yes" | "no")}
              className="flex gap-4 pt-1"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="yes" id="gp-yes" className="h-4 w-4" />
                <Label htmlFor="gp-yes" className="text-xs cursor-pointer font-medium text-emerald-600 dark:text-emerald-400">Yes, correct</Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="no" id="gp-no" className="h-4 w-4" />
                <Label htmlFor="gp-no" className="text-xs cursor-pointer font-medium text-red-500">No, wrong</Label>
              </div>
            </RadioGroup>

            {gsPaperCorrect === "no" && (
              <div className="pt-2">
                <Label className="text-xs font-medium text-muted-foreground">
                  Which GS paper should it be in?
                </Label>
                <Select value={suggestedGsPaper} onValueChange={setSuggestedGsPaper}>
                  <SelectTrigger className="mt-1.5 h-9 text-xs">
                    <SelectValue placeholder="Select correct paper..." />
                  </SelectTrigger>
                  <SelectContent>
                    {GS_PAPERS.map((p) => (
                      <SelectItem key={p} value={p} className="text-xs">
                        {p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* ── Optional: Suggestions ── */}
          <div className="space-y-2 rounded-lg border border-border/30 bg-background/50 p-4">
            <div className="flex items-start gap-2">
              <Lightbulb className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <Label className="text-sm font-medium">
                  Additional suggestions (optional)
                </Label>
                <p className="text-[10px] text-muted-foreground/60 mt-0.5">
                  Any other thoughts — what could improve this story's classification?
                </p>
              </div>
            </div>
            <Textarea
              value={suggestions}
              onChange={(e) => setSuggestions(e.target.value)}
              placeholder="E.g., 'This should be tagged under Education as well', 'The subtopics are incorrect'..."
              className="min-h-[70px] text-xs resize-none mt-1"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-red-500/10 border border-red-500/20 p-3">
              <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
              <p className="text-xs text-red-500">{error}</p>
            </div>
          )}

          <Button
            size="sm"
            className="w-full gap-2 text-xs h-9"
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Submitting...
              </>
            ) : (
              <>
                <Sparkles className="h-3.5 w-3.5" />
                Submit Review & Train the Model
              </>
            )}
          </Button>

          <p className="text-[9px] text-center text-muted-foreground/40 leading-relaxed">
            Your feedback is used as training data to improve the ML model's accuracy.
            Every review helps the system learn better filtering.
          </p>
        </div>
      )}
    </div>
  )
}
