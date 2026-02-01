"use client"

import React from "react"

import { PredictionBar } from "@/components/ui/PredictionBar"
import { BestPickBadge } from "@/components/widgets/BestPickBadge"
import { HighConfidenceBadge } from "@/components/widgets/HighConfidenceBadge"

type MatchLite = {
  match_id: string
  home_team: string
  away_team: string
  kickoff_unix?: number | null
  confidence: number
  probabilities: Record<string, number>
}

function fmtKickoff(unix?: number | null) {
  if (!unix) return "—"
  const d = new Date(unix * 1000)
  return d.toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
}

export const MatchRow = React.memo(function MatchRow({
  m,
  p1,
  px,
  p2,
  isTop,
  isBest,
  watched,
  onToggleWatch,
  rightSlot
}: {
  m: MatchLite
  p1: number
  px: number
  p2: number
  isTop?: boolean
  isBest?: boolean
  watched: boolean
  onToggleWatch: () => void
  rightSlot?: React.ReactNode
}) {
  const bestCls = isBest
    ? "border-emerald-500/20 ring-1 ring-sky-500/25 dark:shadow-[0_0_0_1px_rgba(16,185,129,0.20),0_0_14px_rgba(56,189,248,0.08)]"
    : ""
  return (
    <div className={`grid grid-cols-1 gap-3 rounded-2xl border border-white/10 bg-white/10 p-3 shadow-sm backdrop-blur-md dark:bg-zinc-950/25 sm:grid-cols-[1.2fr_1fr_auto] sm:items-center ${bestCls}`}>
      <div className="min-w-0">
        <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">Match</div>
        <div className="mt-1 text-sm font-extrabold tracking-tight text-zinc-900 dark:text-zinc-50">
          <span className="break-words">{m.home_team}</span>
          <span className="mx-1 text-zinc-400 dark:text-zinc-500">vs</span>
          <span className="break-words">{m.away_team}</span>
        </div>
        <div className="mt-1 flex items-center gap-2 text-[11px] text-zinc-600 dark:text-zinc-300">
          <span className="num font-semibold">{Math.round(Number(m.confidence ?? 0))}</span>
          <span className="opacity-70">conf</span>
          <span className="opacity-40">•</span>
          <span className="num">{fmtKickoff(m.kickoff_unix)}</span>
        </div>
      </div>

      <div className="sm:px-2">
        <PredictionBar p1={p1} px={px} p2={p2} compact className="mt-0" />
      </div>

      <div className="flex items-center justify-between gap-2 sm:justify-end">
        <div className="hidden sm:block">{rightSlot}</div>
        {isBest ? <BestPickBadge /> : null}
        <HighConfidenceBadge prediction={m} />
        {isTop ? (
          <span className="rounded-full border border-emerald-500/20 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-extrabold text-emerald-700 dark:text-emerald-400">
            TOP
          </span>
        ) : null}
        <button
          type="button"
          onClick={onToggleWatch}
          className={[
            "shrink-0 rounded-full border px-2.5 py-1 text-xs font-semibold shadow-sm transition",
            watched
              ? "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
              : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
          ].join(" ")}
          aria-pressed={watched}
          title={watched ? "Rimuovi dai preferiti" : "Aggiungi ai preferiti"}
        >
          {watched ? "★" : "☆"}
        </button>
      </div>

      <div className="sm:hidden">{rightSlot}</div>
    </div>
  )
})
