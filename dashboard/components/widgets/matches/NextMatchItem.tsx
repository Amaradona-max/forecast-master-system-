"use client"

import React from "react"

import { BestPickBadge } from "@/components/widgets/BestPickBadge"
import { HighConfidenceBadge } from "@/components/widgets/HighConfidenceBadge"

type NextMatch = { home_team: string; away_team: string } & Record<string, unknown>

export const NextMatchItem = React.memo(function NextMatchItem({
  m,
  matchKey,
  titleRight,
  isTop,
  isBest,
  onToggleWatch,
  watched,
  children
}: {
  m: NextMatch
  matchKey: string
  titleRight?: React.ReactNode
  isTop?: boolean
  isBest?: boolean
  onToggleWatch: () => void
  watched: boolean
  children?: React.ReactNode
}) {
  const bestCls = isBest
    ? "border-emerald-500/20 ring-1 ring-sky-500/25 dark:shadow-[0_0_0_1px_rgba(16,185,129,0.25),0_0_18px_rgba(56,189,248,0.10)]"
    : ""
  return (
    <section
      key={matchKey}
      className={`rounded-2xl border border-white/10 bg-white/10 p-4 shadow-sm backdrop-blur-md dark:bg-zinc-950/25 ${bestCls}`}
    >
      <header className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">
            Match
          </div>
          <div className="mt-1 text-base font-extrabold tracking-tight text-zinc-900 dark:text-zinc-50">
            <span>{m.home_team}</span>
            <span className="mx-1 text-zinc-400 dark:text-zinc-500">vs</span>
            <span>{m.away_team}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-start justify-between gap-2 md:justify-end">
          <div className="min-w-0">{titleRight}</div>
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
      </header>

      <div className="mt-3">{children}</div>
    </section>
  )
})
