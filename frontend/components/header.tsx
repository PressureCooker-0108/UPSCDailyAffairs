"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { RefreshCw, Globe, Sun, Moon, Timer, GraduationCap } from "lucide-react"
import Link from "next/link"
import { useTheme } from "next-themes"
import { toast } from "sonner"

export function Header() {
  const [refreshing, setRefreshing] = useState(false)
  const { theme, setTheme } = useTheme()

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8002"}/pipeline/run`, {
        method: "POST",
      })
      if (res.status === 429) {
        const body = await res.json()
        const retryAfter = body.detail?.retry_after ?? 60
        toast.error("Rate limited", {
          description: `Pipeline was just run. Try again in ${Math.ceil(retryAfter)} seconds.`,
          icon: <Timer className="h-4 w-4" />,
          duration: 4000,
        })
        return
      }
      if (!res.ok) {
        toast.error("Pipeline request failed", {
          description: `Server returned ${res.status}`,
        })
        return
      }
      window.location.reload()
    } catch {
      toast.error("Network error", {
        description: "Could not reach the server. Make sure the backend is running.",
      })
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <header className="border-b border-border sticky top-0 bg-background/80 backdrop-blur-xl z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="flex items-center justify-between">
          {/* Left: Brand */}
          <Link href="/" className="flex items-center gap-3 group">
            <div className="relative">
              <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                <Globe className="h-4 w-4 text-primary" />
              </div>
              <span className="absolute -top-1 -right-1 h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
            </div>
            <div>
              <h1 className="text-xl font-light tracking-tight">
                UPSC <span className="font-semibold">Daily Affairs</span>
              </h1>
              <p className="text-[10px] text-muted-foreground -mt-0.5">
                Syllabus-aligned current affairs
              </p>
            </div>
          </Link>

          {/* Center: Navigation - UPSC only */}
          <nav className="hidden md:flex items-center gap-1">
            <Link
              href="/"
              className="px-3 py-1.5 rounded-md text-xs font-medium text-amber-400/80 hover:text-amber-300 hover:bg-amber-500/10 transition-colors flex items-center gap-1.5"
            >
              <GraduationCap className="h-3.5 w-3.5" />
              UPSC
            </Link>
          </nav>

          {/* Right: Actions */}
          <div className="flex items-center gap-1.5">
            {/* Theme Toggle */}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="h-9 w-9 p-0"
              title={theme === "dark" ? "Switch to light mode" : theme === "light" ? "Switch to dark mode" : "Toggle theme"}
            >
              <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
              <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              className="gap-2"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
          </div>
        </div>
      </div>
    </header>
  )
}
