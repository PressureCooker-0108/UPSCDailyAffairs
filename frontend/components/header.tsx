"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { RefreshCw, FileText, Download, Globe, FileDown, Sun, Moon, Timer } from "lucide-react"
import Link from "next/link"
import { useTheme } from "next-themes"
import { toast } from "sonner"
import { downloadMarkdown, downloadJson, downloadPdf } from "@/lib/api"

export function Header() {
  const [refreshing, setRefreshing] = useState(false)
  const { theme, setTheme } = useTheme()

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001"}/pipeline/run`, {
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
                Operator <span className="font-semibold">Brief</span>
              </h1>
              <p className="text-[10px] text-muted-foreground -mt-0.5">
                What actually matters today
              </p>
            </div>
          </Link>

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
            <div className="h-5 w-px bg-border/60 mx-1 hidden sm:block" />
            <Button variant="ghost" size="sm" onClick={downloadMarkdown} className="hidden sm:flex" title="Download Markdown Briefing">
              <FileText className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="sm" onClick={downloadJson} className="hidden sm:flex" title="Download JSON Export">
              <Download className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={downloadPdf} className="gap-1.5">
              <FileDown className="h-4 w-4" />
              <span className="hidden sm:inline text-xs font-medium">PDF</span>
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
