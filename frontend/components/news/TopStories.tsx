import { Story } from "@/types/story"
import { StoryCard } from "./StoryCard"

interface TopStoriesProps {
  stories: Story[]
}

export function TopStories({ stories }: TopStoriesProps) {
  return (
    <section className="space-y-8">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground/60">
          Intelligence Feed
        </h3>
        <div className="h-px flex-1 ml-4 bg-border/60" />
      </div>
      
      {/* Bento Grid Layout */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 auto-rows-[250px]">
        {stories.slice(0, 6).map((story, idx) => {
          // Determine spanning logic for bento effect
          let spanClass = "md:col-span-1 md:row-span-1"
          if (idx === 0) spanClass = "md:col-span-2 md:row-span-2" // Featured item
          if (idx === 1) spanClass = "md:col-span-2 md:row-span-1" // Wide item
          if (idx === 4) spanClass = "md:col-span-1 md:row-span-2" // Tall item
          
          return (
            <div key={idx} className={spanClass}>
              <StoryCard story={story} className="h-full" />
            </div>
          )
        })}
      </div>
    </section>
  )
}
