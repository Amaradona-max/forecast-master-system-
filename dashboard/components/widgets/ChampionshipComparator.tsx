"use client"

import { useMemo } from "react"

import { Card } from "@/components/widgets/Card"
import { CompareExplainabilityCard, type CompareExplainabilityPayload } from "@/components/widgets/CompareExplainabilityCard"

const targets = [
  { c: "serie_a", a: "72–75%", k: "defensive_strength, home_advantage_strong" },
  { c: "premier_league", a: "70–73%", k: "pace_intensity, winter_fixture_congestion" },
  { c: "la_liga", a: "71–74%", k: "possession_based, technical_quality" },
  { c: "bundesliga", a: "73–76%", k: "high_scoring, gegenpress_impact" },
  { c: "eliteserien", a: "68–71%", k: "weather_impact, summer_league_timing" }
]

export function ChampionshipComparator({ compareData }: { compareData?: CompareExplainabilityPayload | null }) {
  const rows = useMemo(() => targets, [])
  return (
    <div className="space-y-4">
      <Card>
        <div className="text-sm font-semibold tracking-tight">Comparator</div>
        <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Target performance e feature chiave</div>
        <div className="mt-4 space-y-2">
          {rows.map((r: { c: string; a: string; k: string }) => (
            <div
              key={r.c}
              className="rounded-2xl border border-zinc-200/70 bg-white/55 px-3 py-2 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-900/30"
            >
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold">{r.c}</div>
                <div className="rounded-full border border-zinc-200/70 bg-white/60 px-2 py-1 text-xs text-zinc-700 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/25 dark:text-zinc-200">
                  {r.a}
                </div>
              </div>
              <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">{r.k}</div>
            </div>
          ))}
        </div>
      </Card>

      <CompareExplainabilityCard compare={compareData} />
    </div>
  )
}
