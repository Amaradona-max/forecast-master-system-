"use client"

import React from "react"

type NextMatch = { home_team: string; away_team: string } & Record<string, unknown>

export const NextMatchItem = React.memo(function NextMatchItem({
  m,
  matchKey,
  titleRight,
  onToggleWatch,
  watched,
  children
}: {
  m: NextMatch
  matchKey: string
  titleRight?: React.ReactNode
  onToggleWatch: () => void
  watched: boolean
  children?: React.ReactNode
}) {
  return (
    <section
      key={matchKey}
      className="rounded-3xl border border-white/10 bg-white/10 p-4 shadow-sm backdrop-blur-md dark:bg-zinc-950/25"
    >
      <header className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto] sm:items-start">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">
            Match
          </div>
          <div className="mt-1 text-base font-extrabold tracking-tight text-zinc-900 dark:text-zinc-50">
            <span className="break-words">{m.home_team}</span>
            <span className="mx-1 text-zinc-400 dark:text-zinc-500">vs</span>
            <span className="break-words">{m.away_team}</span>
          </div>
        </div>

        <div className="flex items-start justify-between gap-2 sm:justify-end">
          <div className="min-w-0">{titleRight}</div>
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
