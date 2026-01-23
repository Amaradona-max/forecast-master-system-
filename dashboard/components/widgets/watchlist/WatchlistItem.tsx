"use client"

import React from "react"

type Badge = {
  label: string
  kind: "live" | "top" | "conf" | "rel_good" | "rel_mid" | "rel_bad" | "chaos" | "upset" | "territory" | "set_pieces"
  tone?: "green" | "yellow" | "red" | "zinc" | "blue"
  title?: string
}

type WatchlistMatch = { home_team: string; away_team: string } & Record<string, unknown>

export const WatchlistItem = React.memo(function WatchlistItem({
  m,
  matchKey,
  badges,
  metaLine,
  pinned,
  onTogglePin,
  onRemove,
  showHistoricalBadge
}: {
  m: WatchlistMatch
  matchKey: string
  badges: Badge[]
  metaLine: string
  pinned: boolean
  onTogglePin: () => void
  onRemove: () => void
  showHistoricalBadge: boolean
}) {
  return (
    <div key={matchKey} className="flex items-center justify-between rounded-xl border border-white/10 bg-white/10 px-3 py-2 dark:bg-zinc-950/20">
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          {m.home_team} – {m.away_team}
        </div>

        <div className="mt-1 flex flex-wrap items-center gap-2">
          {showHistoricalBadge ? (
            <span className="rounded-full border border-zinc-500/20 bg-zinc-500/10 px-2 py-0.5 text-[10px] font-bold tracking-wide text-zinc-700 dark:text-zinc-300">
              NON IN CALENDARIO
            </span>
          ) : null}

          {badges.map((b) => (
            <span
              key={b.label}
              title={b.title}
              className={[
                "rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-wide",
                b.label === "NO BET"
                  ? "border-zinc-500/20 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
                  : b.kind === "upset"
                    ? "border-red-500/20 bg-red-500/15 text-red-700 dark:text-red-300"
                  : b.kind === "territory"
                    ? b.tone === "green"
                      ? "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                      : b.tone === "red"
                        ? "border-rose-500/20 bg-rose-500/15 text-rose-700 dark:text-rose-300"
                        : "border-zinc-500/20 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
                  : b.kind === "set_pieces"
                    ? b.tone === "green"
                      ? "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                      : b.tone === "red"
                        ? "border-rose-500/20 bg-rose-500/15 text-rose-700 dark:text-rose-300"
                        : "border-zinc-500/20 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
                  : b.kind === "chaos"
                    ? b.tone === "red"
                      ? "border-red-500/20 bg-red-500/15 text-red-700 dark:text-red-300"
                      : b.tone === "yellow"
                        ? "border-amber-500/20 bg-amber-500/15 text-amber-700 dark:text-amber-300"
                        : "border-sky-500/20 bg-sky-500/15 text-sky-700 dark:text-sky-300"
                  : b.kind === "rel_good"
                  ? "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                  : b.kind === "rel_mid"
                    ? "border-amber-500/20 bg-amber-500/15 text-amber-700 dark:text-amber-300"
                    : b.kind === "rel_bad"
                      ? "border-rose-500/20 bg-rose-500/15 text-rose-700 dark:text-rose-300"
                  : b.kind === "live"
                  ? "border-red-500/20 bg-red-500/15 text-red-700 dark:text-red-300"
                  : b.kind === "top"
                    ? "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                    : "border-sky-500/20 bg-sky-500/15 text-sky-700 dark:text-sky-300"
              ].join(" ")}
            >
              {b.label}
            </span>
          ))}
        </div>

        <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">{metaLine}</div>
      </div>

      <div className="ml-3 flex items-center gap-2">
        <button
          type="button"
          onClick={onTogglePin}
          className={[
            "rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm transition",
            pinned
              ? "border-amber-500/20 bg-amber-500/15 text-amber-700 dark:text-amber-300"
              : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
          ].join(" ")}
          title={pinned ? "Rimuovi PIN" : "Metti in PIN (max 3)"}
          aria-pressed={pinned}
        >
          📌
        </button>

        <button
          type="button"
          onClick={onRemove}
          className="rounded-full border border-white/10 bg-white/10 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
          aria-label="Rimuovi dai preferiti"
          title="Rimuovi dai preferiti"
        >
          ★
        </button>
      </div>
    </div>
  )
})
