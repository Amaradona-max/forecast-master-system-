"use client"

import type { ReactNode } from "react"

export function BestCountsHeader({
  bestCount,
  topCount,
  showHint
}: {
  bestCount: number
  topCount: number
  showHint?: boolean
}) {
  const hint =
    showHint && bestCount === 0
      ? "Nessun BEST: prova ad alzare la soglia TOP o disattivare High Conf."
      : null

  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="best">
          BEST picks <span className="num">({bestCount})</span>
        </Pill>
        <Pill tone="top">
          TOP <span className="num">({topCount})</span>
        </Pill>
      </div>

      {hint ? (
        <div className="text-xs text-zinc-500 dark:text-zinc-300">
          {hint}
        </div>
      ) : null}
    </div>
  )
}

function Pill({ children, tone }: { children: ReactNode; tone: "best" | "top" }) {
  const cls =
    tone === "best"
      ? "border-emerald-500/25 bg-gradient-to-r from-emerald-500/15 to-sky-500/15 text-emerald-800 dark:text-emerald-300"
      : "border-emerald-500/15 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300"

  return (
    <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-extrabold ${cls}`}>
      {children}
    </span>
  )
}
