"use client"

import { useEffect, useState } from "react"
import { MarketDataPoint } from "@/types/story"
import { fetchMarketData } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { TrendingUp, TrendingDown, BarChart3, RefreshCw, Timer, Building2, Activity, GanttChartSquare } from "lucide-react"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts"
import { toast } from "sonner"

const SECTOR_ICONS: Record<string, string> = {
  Index: "📈",
  Tech: "💻",
  Finance: "🏦",
  Energy: "⚡",
  Healthcare: "🏥",
  Consumer: "🛒",
  "Consumer/ Tech": "🛒",
  India: "🇮🇳",
  Markets: "🌐",
}

function MarketCard({ point }: { point: MarketDataPoint }) {
  const isPositive = point.change >= 0
  return (
    <div
      className={`rounded-lg border p-3 transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 ${
        isPositive
          ? "bg-emerald-500/[0.03] border-emerald-500/20 hover:border-emerald-500/40"
          : "bg-red-500/[0.03] border-red-500/20 hover:border-red-500/40"
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-bold text-muted-foreground">{point.ticker}</span>
        {point.market_cap && (
          <span className="text-[10px] text-muted-foreground/60">{point.market_cap}</span>
        )}
      </div>
      <p className="text-lg font-bold">${point.price.toFixed(2)}</p>
      <div className="flex items-center gap-1 mt-1">
        <span
          className={`text-xs font-medium ${
            isPositive ? "text-emerald-400" : "text-red-400"
          }`}
        >
          {isPositive ? "+" : ""}
          {point.change.toFixed(2)}
        </span>
        <span
          className={`text-xs font-medium ${
            isPositive ? "text-emerald-400" : "text-red-400"
          }`}
        >
          ({isPositive ? "+" : ""}
          {point.change_pct.toFixed(2)}%)
        </span>
      </div>
    </div>
  )
}

export function MarketDashboard() {
  const [data, setData] = useState<{
    all: MarketDataPoint[]
    gainers: MarketDataPoint[]
    losers: MarketDataPoint[]
    indices: MarketDataPoint[]
  }>({ all: [], gainers: [], losers: [], indices: [] })
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<"all" | "gainers" | "losers" | "sectors">("all")

  async function load() {
    try {
      setLoading(true)
      const marketData = await fetchMarketData()
      setData(marketData)
      setError(null)
    } catch {
      setError("Failed to load market data")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 60000)
    return () => clearInterval(interval)
  }, [])

  async function handleRefresh() {
    setRefreshing(true)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001"}/markets/refresh`, {
        method: "POST",
      })
      if (res.status === 429) {
        const body = await res.json()
        const retryAfter = body.detail?.retry_after ?? 30
        toast.error("Rate limited", {
          description: `Market data was just refreshed. Try again in ${Math.ceil(retryAfter)} seconds.`,
          icon: <Timer className="h-4 w-4" />,
          duration: 4000,
        })
        return
      }
      if (!res.ok) {
        toast.error("Refresh failed", {
          description: `Server returned ${res.status}`,
        })
        return
      }
      await load()
    } catch {
      toast.error("Network error", {
        description: "Could not reach the server for market data refresh.",
      })
    } finally {
      setRefreshing(false)
    }
  }

  // Group stocks by sector (excluding indices)
  const stocksBySector: Record<string, MarketDataPoint[]> = {}
  for (const point of data.all) {
    const isIndex = point.ticker.startsWith("^") || point.sector === "Index"
    if (!isIndex) {
      if (!stocksBySector[point.sector]) stocksBySector[point.sector] = []
      stocksBySector[point.sector].push(point)
    }
  }

  // Count green vs red
  const greenCount = data.all.filter((d) => d.change >= 0).length
  const redCount = data.all.filter((d) => d.change < 0).length
  const totalCount = data.all.length

  // Chart data from top movers
  const chartData = data.gainers
    .slice(0, 5)
    .concat(data.losers.slice(0, 5))
    .map((m) => ({
      name: m.ticker,
      fullName: m.name,
      change: m.change_pct,
    }))

  if (loading && data.all.length === 0) {
    return (
      <Card className="border-border/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <BarChart3 className="h-5 w-5" />
            Markets
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error && data.all.length === 0) {
    return (
      <Card className="border-border/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <BarChart3 className="h-5 w-5" />
            Markets
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-3 py-6">
          <div className="rounded-full bg-muted p-3">
            <BarChart3 className="h-6 w-6 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground text-center">{error}</p>
          <p className="text-[11px] text-muted-foreground/50 text-center max-w-xs">
            Market data will auto-retry. Check back shortly or refresh manually.
          </p>
          <Button variant="outline" size="sm" onClick={load} className="mt-1">
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-border/50 overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-emerald-400" />
          <CardTitle className="text-lg">Markets Dashboard</CardTitle>
          {totalCount > 0 && (
            <div className="hidden sm:flex items-center gap-2 ml-3 text-xs text-muted-foreground">
              <span className="text-emerald-400 font-medium">{greenCount} ▲</span>
              <span className="text-red-400 font-medium">{redCount} ▼</span>
              <span className="text-muted-foreground/50">·</span>
              <span>{totalCount} tracked</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground/50 hidden sm:inline">
            auto-refreshes every 60s
          </span>
          <Button variant="ghost" size="sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Indices Row */}
        {data.indices.length > 0 && (
          <div className="animate-fade-in">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="h-4 w-4 text-primary" />
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Major Indices
              </h4>
              <div className="h-px flex-1 bg-border/60" />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
              {data.indices.map((idx, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-border/50 bg-muted/20 p-3 transition-all duration-200 hover:bg-muted/40"
                >
                  <p className="text-xs text-muted-foreground mb-1">{idx.ticker}</p>
                  <p className="text-lg font-bold tabular-nums">${idx.price.toFixed(2)}</p>
                  <span
                    className={`inline-flex items-center gap-1 text-xs font-medium mt-1 ${
                      idx.change_pct >= 0 ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {idx.change_pct >= 0 ? (
                      <TrendingUp className="h-3 w-3" />
                    ) : (
                      <TrendingDown className="h-3 w-3" />
                    )}
                    {idx.change_pct >= 0 ? "+" : ""}
                    {idx.change_pct.toFixed(2)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Movers Chart */}
        {chartData.length > 0 && (
          <div className="animate-fade-in">
            <div className="flex items-center gap-2 mb-3">
              <GanttChartSquare className="h-4 w-4 text-primary" />
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Notable Movers (% Change)
              </h4>
              <div className="h-px flex-1 bg-border/60" />
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical" margin={{ left: 40, right: 20 }}>
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 11 }} width={50} />
                  <Tooltip
                    formatter={(value: any) => {
                      const num = Number(value)
                      return [`${num >= 0 ? "+" : ""}${num.toFixed(2)}%`, "Change"]
                    }}
                    labelFormatter={(label: any) => {
                      const item = chartData.find((d) => d.name === label)
                      return item?.fullName || label
                    }}
                    contentStyle={{
                      background: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                  <Bar dataKey="change" radius={[0, 4, 4, 0]} maxBarSize={20}>
                    {chartData.map((entry, index) => (
                      <Cell key={index} fill={entry.change >= 0 ? "#22c55e" : "#ef4444"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Tabs: All | Gainers | Losers | By Sector */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Building2 className="h-4 w-4 text-primary" />
            <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Stocks
            </h4>
            <div className="h-px flex-1 bg-border/60" />
          </div>
          <div className="flex flex-wrap gap-1 mb-4">
            {(["all", "gainers", "losers", "sectors"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-3 py-1.5 text-xs font-medium rounded-full transition-all duration-200 ${
                  activeTab === tab
                    ? "bg-primary/10 text-primary border border-primary/30"
                    : "bg-muted/30 text-muted-foreground border border-border/50 hover:bg-muted/50"
                }`}
              >
                {tab === "all" && `All Stocks (${data.all.length - data.indices.length})`}
                {tab === "gainers" && `Gainers (${data.gainers.length})`}
                {tab === "losers" && `Losers (${data.losers.length})`}
                {tab === "sectors" && "By Sector"}
              </button>
            ))}
          </div>

          {/* All Stocks View */}
          {activeTab === "all" && (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
              {data.all
                .filter((d) => !(d.ticker.startsWith("^") || d.sector === "Index"))
                .sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
                .map((point, i) => (
                  <MarketCard key={i} point={point} />
                ))}
            </div>
          )}

          {/* Gainers View */}
          {activeTab === "gainers" && (
            <div>
              {data.gainers.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                  {data.gainers.slice(0, 12).map((m, i) => (
                    <MarketCard key={i} point={m} />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground text-center py-6">
                  No stocks moving more than 0.75% today
                </p>
              )}
            </div>
          )}

          {/* Losers View */}
          {activeTab === "losers" && (
            <div>
              {data.losers.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                  {data.losers.slice(0, 12).map((m, i) => (
                    <MarketCard key={i} point={m} />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground text-center py-6">
                  No stocks moving more than 0.75% today
                </p>
              )}
            </div>
          )}

          {/* By Sector View */}
          {activeTab === "sectors" && (
            <div className="space-y-4">
              {Object.entries(stocksBySector)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([sector, stocks]) => (
                  <div key={sector}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-sm">{SECTOR_ICONS[sector] || "📊"}</span>
                      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        {sector}
                      </span>
                      <span className="text-[10px] text-muted-foreground/50">({stocks.length})</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                      {stocks.map((point, i) => (
                        <MarketCard key={i} point={point} />
                      ))}
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
