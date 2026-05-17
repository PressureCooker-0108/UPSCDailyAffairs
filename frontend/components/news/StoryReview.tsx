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
import { SECTORS } from "@/types/story"
import { submitReview } from "@/lib/api"
import { MessageSquare, ThumbsUp, Loader2 } from "lucide-react"

interface StoryReviewProps {
  storyTitle: string
  storyUrl?: string
}

export function StoryReview({ storyTitle, storyUrl }: StoryReviewProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [correctSection, setCorrectSection] = useState<"yes" | "no" | "">("")
  const [suggestedSection, setSuggestedSection] = useState("")
  const [summaryConcise, setSummaryConcise] = useState<"yes" | "no" | "">("")
  const [pictureAvailable, setPictureAvailable] = useState<"yes" | "no" | "">("")
  const [comment, setComment] = useState("")
  const [error, setError] = useState("")

  const handleSubmit = async () => {
    setError("")
    if (!correctSection || !summaryConcise || !pictureAvailable) {
      setError("Please fill in all required fields.")
      return
    }

    setSubmitting(true)
    const result = await submitReview({
      story_title: storyTitle,
      story_url: storyUrl,
      correct_section: correctSection,
      suggested_section: suggestedSection || undefined,
      summary_concise: summaryConcise,
      picture_available: pictureAvailable,
      comment: comment || undefined,
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
    setCorrectSection("")
    setSuggestedSection("")
    setSummaryConcise("")
    setPictureAvailable("")
    setComment("")
    setError("")
  }

  if (submitted) {
    return (
      <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-4 text-center">
        <ThumbsUp className="h-6 w-6 text-green-500 mx-auto mb-2" />
        <p className="text-sm font-medium text-green-600 dark:text-green-400">
          Thank you for your feedback!
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          Your review helps improve the classification system.
        </p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-2 text-xs"
          onClick={handleReset}
        >
          Submit another
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
        <div className="mt-3 space-y-4 rounded-lg border border-border/40 bg-muted/30 p-4">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Help improve the system
          </p>

          {/* Correct Section */}
          <div className="space-y-2">
            <Label className="text-xs font-medium">
              Is this story in the correct section?{" "}
              <span className="text-red-400">*</span>
            </Label>
            <RadioGroup
              value={correctSection}
              onValueChange={(v) => setCorrectSection(v as "yes" | "no")}
              className="flex gap-4"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="yes" id="cs-yes" />
                <Label htmlFor="cs-yes" className="text-xs cursor-pointer">Yes</Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="no" id="cs-no" />
                <Label htmlFor="cs-no" className="text-xs cursor-pointer">No</Label>
              </div>
            </RadioGroup>
          </div>

          {/* Suggested Section */}
          {correctSection === "no" && (
            <div className="space-y-2">
              <Label className="text-xs font-medium">
                What section should it be in?
              </Label>
              <Select value={suggestedSection} onValueChange={setSuggestedSection}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="Select a section..." />
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

          {/* Summary Concise */}
          <div className="space-y-2">
            <Label className="text-xs font-medium">
              Is the summary concise and accurate?{" "}
              <span className="text-red-400">*</span>
            </Label>
            <RadioGroup
              value={summaryConcise}
              onValueChange={(v) => setSummaryConcise(v as "yes" | "no")}
              className="flex gap-4"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="yes" id="sc-yes" />
                <Label htmlFor="sc-yes" className="text-xs cursor-pointer">Yes</Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="no" id="sc-no" />
                <Label htmlFor="sc-no" className="text-xs cursor-pointer">No</Label>
              </div>
            </RadioGroup>
          </div>

          {/* Picture Available */}
          <div className="space-y-2">
            <Label className="text-xs font-medium">
              Is an image/picture available for this story?{" "}
              <span className="text-red-400">*</span>
            </Label>
            <RadioGroup
              value={pictureAvailable}
              onValueChange={(v) => setPictureAvailable(v as "yes" | "no")}
              className="flex gap-4"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="yes" id="pa-yes" />
                <Label htmlFor="pa-yes" className="text-xs cursor-pointer">Yes</Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="no" id="pa-no" />
                <Label htmlFor="pa-no" className="text-xs cursor-pointer">No</Label>
              </div>
            </RadioGroup>
          </div>

          {/* Comment */}
          <div className="space-y-2">
            <Label className="text-xs font-medium">
              Additional feedback (optional)
            </Label>
            <Textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Any other thoughts on this story..."
              className="min-h-[60px] text-xs resize-none"
            />
          </div>

          {error && (
            <p className="text-xs text-red-500">{error}</p>
          )}

          <Button
            size="sm"
            className="w-full gap-2 text-xs"
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Submitting...
              </>
            ) : (
              <>Submit Review</>
            )}
          </Button>
        </div>
      )}
    </div>
  )
}
