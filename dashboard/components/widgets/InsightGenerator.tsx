"use client"

import type { MatchUpdate } from "@/components/api/types"

export function InsightGenerator({ match }: { match: MatchUpdate }) {
  const explain = (match.meta?.explain ?? {}) as Record<string, unknown>
  const key = Array.isArray(explain?.championship_key_features) ? (explain.championship_key_features as unknown[]) : []
  const derived = (explain?.derived_markets ?? {}) as Record<string, unknown>

  return (
    <div className="rounded-2xl border border-zinc-200/70 bg-white/55 p-3 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/25">
      <div className="text-xs font-semibold tracking-tight">Insight</div>
      <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-300">
        Feature chiave: {key.length ? key.join(", ") : "n/d"}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-xl border border-zinc-200/70 bg-white/55 px-3 py-2 dark:border-zinc-800/70 dark:bg-zinc-900/25">
          Over 2.5: {typeof derived?.over_2_5 === "number" ? `${Math.round((derived.over_2_5 as number) * 100)}%` : "n/d"}
        </div>
        <div className="rounded-xl border border-zinc-200/70 bg-white/55 px-3 py-2 dark:border-zinc-800/70 dark:bg-zinc-900/25">
          BTTS: {typeof derived?.btts === "number" ? `${Math.round((derived.btts as number) * 100)}%` : "n/d"}
        </div>
      </div>
    </div>
  )
}
