"use client"

import { useMemo, useState } from "react"

import { StickyFiltersBar } from "@/components/layout/StickyFiltersBar"
import { ThemeToggle } from "@/components/theme/ThemeToggle"
import { Card } from "@/components/widgets/Card"
import { ChampionshipComparator } from "@/components/widgets/ChampionshipComparator"
import { LiveMatchCenter } from "@/components/widgets/LiveMatchCenter"
import { PredictionAccuracyTracker } from "@/components/widgets/PredictionAccuracyTracker"
import { StatisticalPredictionsDashboard } from "@/components/widgets/StatisticalPredictionsDashboard"

type TabKey = "pred" | "live" | "acc" | "compare"

function tabLabel(k: TabKey) {
  if (k === "pred") return "Previsioni"
  if (k === "live") return "Live"
  if (k === "acc") return "Accuracy"
  return "Confronto"
}

export function DashboardShell() {
  const [tab, setTab] = useState<TabKey>("pred")
  const showMatchFilters = tab === "pred"
  const filtersLeft = null
  const filtersRight = null
  const filtersBottom = null

  const subtitle = useMemo(() => {
    if (tab === "pred") return "Consigli e spiegazioni match-by-match"
    if (tab === "live") return "Aggiornamenti in tempo reale"
    if (tab === "acc") return "Trend stagionale e prestazioni"
    return "Panoramica multi-campionato"
  }, [tab])

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <header className="sticky top-3 z-20">
        <div className="rounded-[26px] border border-white/10 bg-white/10 px-4 py-3 shadow-sm backdrop-blur-md dark:bg-zinc-950/25">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-semibold tracking-tight">Forecast Master</div>
              <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">{subtitle}</div>
            </div>

            <div className="flex items-center gap-2">
              <nav className="flex flex-wrap items-center gap-2">
                {(["pred", "live", "acc", "compare"] as TabKey[]).map((k) => {
                  const active = tab === k
                  return (
                    <button
                      key={k}
                      type="button"
                      onClick={() => setTab(k)}
                      className={[
                        "rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm transition",
                        active
                          ? "border-white/20 bg-white/20 text-zinc-900 dark:bg-white/10 dark:text-zinc-50"
                          : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:text-zinc-200",
                      ].join(" ")}
                      aria-current={active ? "page" : undefined}
                    >
                      {tabLabel(k)}
                    </button>
                  )
                })}
              </nav>
              <ThemeToggle />
            </div>
          </div>
        </div>
      </header>

      {showMatchFilters && (
        <StickyFiltersBar left={filtersLeft} right={filtersRight} bottom={filtersBottom} />
      )}

      <div className="mt-4">
        {tab === "pred" ? (
          <StatisticalPredictionsDashboard />
        ) : tab === "live" ? (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
            <div className="lg:col-span-8">
              <LiveMatchCenter />
            </div>
            <div className="lg:col-span-4">
              <Card>
                <div className="text-sm font-semibold tracking-tight">Suggerimenti</div>
                <ul className="mt-2 space-y-2 text-xs text-zinc-600 dark:text-zinc-300">
                  <li>• Se vedi “In attesa dei dati live…”, avvia prima una partita o verifica il WS nel backend.</li>
                  <li>• In reti aziendali alcuni WebSocket sono bloccati: considera una fallback SSE.</li>
                </ul>
              </Card>
            </div>
          </div>
        ) : tab === "acc" ? (
          <PredictionAccuracyTracker />
        ) : (
          <ChampionshipComparator />
        )}
      </div>
    </main>
  )
}
