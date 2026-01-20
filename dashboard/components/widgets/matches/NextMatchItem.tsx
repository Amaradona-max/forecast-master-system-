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
    <div key={matchKey} className="rounded-2xl border border-white/10 bg-white/10 p-4 shadow-sm dark:bg-zinc-950/25">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 truncate text-sm font-semibold">
          {m.home_team} – {m.away_team}
        </div>
        <div className="flex items-center gap-2">
          {titleRight}
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
      </div>

      <div className="mt-3">{children}</div>
    </div>
  )
})

