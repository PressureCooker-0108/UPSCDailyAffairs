import { useState } from "react"
import { Story } from "@/types/story"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { ExternalLink, Newspaper, TrendingUp, BarChart3, FileText, ImageOff } from "lucide-react"
import { StoryReview } from "./StoryReview"

interface StoryCardProps {
  story: Story
  className?: string
}

export function StoryCard({ story, className }: StoryCardProps) {
  const [imgError, setImgError] = useState(false)
  const hasImage = !!story.image_url && !imgError

  const CardContent = (
    <article className={`h-full rounded-xl border border-border bg-card overflow-hidden transition-all duration-300 hover:shadow-lg hover:border-primary/30 hover:-translate-y-0.5 group cursor-pointer ${className}`}>
      {/* Thumbnail image */}
      {hasImage && (
        <div className="relative h-40 sm:h-48 w-full overflow-hidden">
          <img
            src={story.image_url!}
            alt=""
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
            loading="lazy"
            onError={() => setImgError(true)}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-card via-card/10 to-transparent" />
        </div>
      )}
      {!hasImage && (
        <div className="h-24 w-full bg-gradient-to-br from-primary/5 via-secondary/10 to-background flex items-center justify-center">
          <ImageOff className="h-6 w-6 text-muted-foreground/20" />
        </div>
      )}

      <div className="p-5 sm:p-6">
        <div className="flex flex-col space-y-3">
          {/* Headline */}
          <h4 className="font-semibold leading-tight text-foreground text-base sm:text-lg group-hover:text-primary transition-colors">
            {story.headline}
          </h4>
          
          {/* Summary */}
          <p className="text-sm leading-relaxed text-muted-foreground line-clamp-3">
            {story.summary}
          </p>
        </div>
        
        {/* Why it matters */}
        {story.why_it_matters && (
          <div className="mt-4 pt-4 border-t border-border/50">
            <p className="text-xs leading-relaxed text-muted-foreground italic font-light line-clamp-2">
              <span className="font-medium not-italic text-foreground/80">Context:</span> {story.why_it_matters}
            </p>
          </div>
        )}
      </div>
    </article>
  )

  return (
    <Dialog>
      <DialogTrigger asChild>
        <div className="block h-full">{CardContent}</div>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        {/* Hero image in dialog */}
        {hasImage && (
          <div className="relative -mx-6 -mt-6 mb-4 h-48 sm:h-64 overflow-hidden rounded-t-xl">
            <img
              src={story.image_url!}
              alt=""
              className="h-full w-full object-cover"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-background via-background/20 to-transparent" />
          </div>
        )}

        <DialogHeader>
          <DialogTitle className="text-xl leading-tight">{story.headline}</DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          {/* Metadata badges */}
          <div className="flex flex-wrap gap-2">
            {story.sectors?.map((s) => (
              <Badge key={s} variant="secondary" className="text-[10px]">
                {s}
              </Badge>
            ))}
            {story.score != null && (
              <Badge variant="outline" className="text-[10px] gap-1">
                <BarChart3 className="h-3 w-3" />
                Score: {story.score.toFixed(1)}
              </Badge>
            )}
            {story.article_count != null && (
              <Badge variant="outline" className="text-[10px] gap-1">
                <Newspaper className="h-3 w-3" />
                {story.article_count} sources
              </Badge>
            )}
            {story.source && story.source.length > 0 && (
              <Badge variant="outline" className="text-[10px] gap-1">
                <FileText className="h-3 w-3" />
                {story.source.slice(0, 3).join(", ")}
              </Badge>
            )}
          </div>

          {/* Full summary */}
          <div>
            <h4 className="text-sm font-semibold text-foreground/70 mb-2 uppercase tracking-wider">
              Summary
            </h4>
            <p className="text-sm leading-relaxed text-foreground/80">
              {story.summary}
            </p>
          </div>

          {/* Why it matters */}
          {story.why_it_matters && (
            <div className="rounded-lg bg-primary/5 border border-primary/10 p-4">
              <h4 className="text-xs font-semibold text-primary mb-2 uppercase tracking-wider flex items-center gap-1.5">
                <TrendingUp className="h-3.5 w-3.5" />
                Why It Matters
              </h4>
              <p className="text-sm leading-relaxed text-foreground/80">
                {story.why_it_matters}
              </p>
            </div>
          )}

          {/* Source link */}
          {story.url && (
            <a
              href={story.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-sm text-primary hover:text-primary/80 transition-colors font-medium"
            >
              <ExternalLink className="h-4 w-4" />
              View original source
            </a>
          )}

          {/* Story Review */}
          <StoryReview
            storyTitle={story.headline}
            storyUrl={story.url}
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}
