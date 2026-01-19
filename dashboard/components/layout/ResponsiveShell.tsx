"use client"

import { useState } from "react"

import { ThemeToggle } from "@/components/theme/ThemeToggle"
import { ChampionshipComparator } from "@/components/widgets/ChampionshipComparator"
import { LiveMatchCenter } from "@/components/widgets/LiveMatchCenter"
import { PredictionAccuracyTracker } from "@/components/widgets/PredictionAccuracyTracker"
import { StatisticalPredictionsDashboard } from "@/components/widgets/StatisticalPredictionsDashboard"

type Section = "pred" | "live" | "acc" | "compare"

const sections: { key: Section; label: string }[] = [
  { key: "pred", label: "Previsioni" },
  { key: "live", label: "Live" },
  { key: "acc", label: "Accuracy" },
  { key: "compare", label: "Confronto" }
]

export function ResponsiveShell() {
  const [active, setActive] = useState<Section>("pred")
  const [collapsed, setCollapsed] = useState(false)

  const Content = () => {
    if (active === "pred") return <StatisticalPredictionsDashboard />
    if (active === "live") return <LiveMatchCenter />
    if (active === "acc") return <PredictionAccuracyTracker />
    return <ChampionshipComparator />
  }

  return (
    <div className="flex min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <aside
        className={`hidden md:flex flex-col border-r border-white/10 bg-white/60 dark:bg-zinc-950/60 backdrop-blur-md transition-all ${
          collapsed ? "w-[72px]" : "w-64"
        }`}
      >
        <div className="flex items-center justify-between px-4 py-3">
          <div className="text-sm font-bold truncate">{collapsed ? "FM" : "Forecast Master"}</div>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            {collapsed ? "›" : "‹"}
          </button>
        </div>

        <nav className="flex-1 space-y-1 px-2">
          {sections.map((s) => {
            const activeItem = active === s.key
            return (
              <button
                key={s.key}
                onClick={() => setActive(s.key)}
                className={[
                  "w-full rounded-xl px-3 py-2 text-left text-sm font-medium transition",
                  activeItem
                    ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-900"
                ].join(" ")}
              >
                {collapsed ? s.label[0] : s.label}
              </button>
            )
          })}
        </nav>

        <div className="px-4 py-3">
          <ThemeToggle />
        </div>
      </aside>

      <main className="flex-1 px-4 py-4 md:px-6 md:py-6">
        <Content />
      </main>

      <nav className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around border-t border-white/10 bg-white/80 backdrop-blur-md dark:bg-zinc-950/80 md:hidden">
        {sections.map((s) => {
          const activeItem = active === s.key
          return (
            <button
              key={s.key}
              onClick={() => setActive(s.key)}
              className={[
                "flex flex-col items-center gap-1 py-2 text-xs font-medium transition",
                activeItem ? "text-emerald-600 dark:text-emerald-400" : "text-zinc-500 dark:text-zinc-400"
              ].join(" ")}
            >
              {s.label}
            </button>
          )
        })}
      </nav>
    </div>
  )
}

