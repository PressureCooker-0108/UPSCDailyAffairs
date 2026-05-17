import { Story } from "@/types/story"
import { ImageOff } from "lucide-react"
import { useState } from "react"

interface BigStoryProps {
  story?: Story
}

export function BigStory({ story }: BigStoryProps) {
  const [imgError, setImgError] = useState(false)

  if (!story) {
    return (
      <article className="rounded-xl border border-border bg-card p-8">
        <p className="text-sm text-muted-foreground">No story available</p>
      </article>
    )
  }

  const hasImage = !!story.image_url && !imgError

  const Content = (
    <article className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-secondary/50 to-background transition-all hover:shadow-xl hover:border-primary/20 group cursor-pointer">
      {/* Hero Image with gradient overlay */}
      {hasImage && (
        <div className="relative h-72 sm:h-96 lg:h-[28rem] w-full overflow-hidden">
          <img
            src={story.image_url!}
            alt=""
            className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105"
            loading="eager"
            onError={() => setImgError(true)}
          />
          {/* Gradient overlays */}
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-r from-background/40 to-transparent" />
        </div>
      )}

      {/* Fallback gradient when no image or image fails to load */}
      {!hasImage && (
        <div className="relative h-48 sm:h-64 w-full bg-gradient-to-br from-primary/10 via-secondary/20 to-background overflow-hidden">
          <div className="absolute inset-0 flex items-center justify-center">
            <ImageOff className="h-12 w-12 text-muted-foreground/20" />
          </div>
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/40 to-transparent" />
        </div>
      )}

      {/* Content overlay */}
      <div className={hasImage ? "relative -mt-32 px-6 sm:px-10 pb-8 sm:pb-12 space-y-6 sm:space-y-8" : "p-6 sm:p-10 space-y-6 sm:space-y-8"}>
        {/* Label */}
        <div className="flex items-center space-x-3">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span>
          </span>
          <div className="text-xs font-bold uppercase tracking-[0.2em] text-primary">
            Critical Intelligence
          </div>
        </div>

        {/* Headline */}
        <h2 className="text-3xl sm:text-5xl lg:text-6xl font-bold leading-[1.1] text-foreground tracking-tight group-hover:text-primary transition-colors">
          {story.headline}
        </h2>

        {/* Summary */}
        <p className="text-base sm:text-xl leading-relaxed text-muted-foreground max-w-4xl">
          {story.summary}
        </p>

        {/* Why it matters */}
        {story.why_it_matters && (
          <div className="rounded-xl bg-background/80 backdrop-blur-sm border border-border p-6 sm:p-8 shadow-sm">
            <div className="flex flex-col space-y-2">
              <span className="text-xs font-bold uppercase tracking-widest text-foreground/40">Implication</span>
              <p className="text-base sm:text-lg leading-relaxed text-foreground/80 font-medium">
                {story.why_it_matters}
              </p>
            </div>
          </div>
        )}
      </div>
    </article>
  )

  if (story.url) {
    return (
      <a href={story.url} target="_blank" rel="noopener noreferrer" className="block">
        {Content}
      </a>
    )
  }

  return Content
}
