"use client"

import { useMemo, useState } from "react"

import { Card } from "@/components/widgets/Card"

type OverviewMatchLite = {
  match_id: string
  championship: string
  home_team: string
  away_team: string
  status: string
  kickoff_unix?: number | null
  confidence: number
  probabilities: Record<string, number>
  explain?: Record<string, unknown>
}

function kickoffUnix(m: OverviewMatchLite) {
  const k = Number(m?.kickoff_unix ?? 0)
  return Number.isFinite(k) && k > 0 ? k : null
}

function bestProb(m: OverviewMatchLite) {
  const ps = m?.probabilities ?? {}
  const vals = Object.values(ps)
    .map((x) => Number(x ?? 0))
    .filter((x) => Number.isFinite(x))
  if (!vals.length) return 0
  return Math.max(...vals)
}

function fmtKickoff(k: number | null) {
  if (!k) return "n/d"
  const d = new Date(k * 1000)
  return d.toLocaleString(undefined, { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
}

function pillClass(tone: "blue" | "yellow" | "red" | "zinc") {
  if (tone === "blue") return "border-sky-500/20 bg-sky-500/15 text-sky-700 dark:text-sky-300"
  if (tone === "yellow") return "border-amber-500/20 bg-amber-500/15 text-amber-700 dark:text-amber-300"
  if (tone === "red") return "border-red-500/20 bg-red-500/15 text-red-700 dark:text-red-300"
  return "border-zinc-500/20 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
}

function chaosFromExplain(explain?: Record<string, unknown>) {
  const e = (explain ?? {}) as Record<string, unknown>
  const chaos0 = e?.chaos
  if (!chaos0 || typeof chaos0 !== "object") return null
  const chaos = chaos0 as Record<string, unknown>
  const idx = Number(chaos.index ?? NaN)
  if (!Number.isFinite(idx)) return null
  const flags = Array.isArray(chaos.flags) ? (chaos.flags as unknown[]).map((x) => String(x)) : []
  const upset = Boolean(chaos.upset_watch)
  return { index: idx, flags, upset }
}

function chaosBadge(idx: number) {
  if (idx >= 85) return { label: "CHAOS🔥", tone: "red" as const }
  if (idx >= 70) return { label: "CHAOS↑", tone: "yellow" as const }
  if (idx >= 55) return { label: "CHAOS", tone: "blue" as const }
  return null
}

export function ChaosLeaderboard({
  matches,
  onOpenMatch,
  limit = 10
}: {
  matches: OverviewMatchLite[]
  onOpenMatch: (matchId: string) => void
  limit?: number
}) {
  const [open, setOpen] = useState<boolean>(true)

  const ranked = useMemo(() => {
    const now = Date.now() / 1000
    const list = (matches ?? [])
      .filter((m) => {
        const k = kickoffUnix(m)
        if (!k) return false
        return k >= now - 3 * 3600
      })
      .map((m) => {
        const c = chaosFromExplain(m.explain)
        return { m, chaos: c }
      })
      .filter((x) => x.chaos && x.chaos.index >= 55)
      .sort((a, b) => (b.chaos?.index ?? 0) - (a.chaos?.index ?? 0))

    return list.slice(0, limit)
  }, [matches, limit])

  return (
    <Card className="mt-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Chaos Leaderboard</div>
          <div className="text-xs text-zinc-600 dark:text-zinc-300">
            Le partite più imprevedibili (Chaos Index alto). Ottimo per evitare trappole o attivare “Upset Watch”.
          </div>
        </div>

        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="rounded-full border border-zinc-200/70 bg-white/70 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-white dark:border-zinc-800/70 dark:bg-zinc-900/55 dark:text-zinc-200"
        >
          {open ? "Nascondi" : "Mostra"}
        </button>
      </div>

      {open ? (
        <div className="mt-3 overflow-auto rounded-2xl border border-zinc-200/70 dark:border-zinc-800/70">
          <table className="min-w-[860px] w-full text-left text-sm">
            <thead className="bg-zinc-50/70 dark:bg-zinc-950/30">
              <tr className="text-xs text-zinc-700 dark:text-zinc-200">
                <th className="px-3 py-2">Kickoff</th>
                <th className="px-3 py-2">Match</th>
                <th className="px-3 py-2">Campionato</th>
                <th className="px-3 py-2">Chaos</th>
                <th className="px-3 py-2">Info</th>
                <th className="px-3 py-2">Azione</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-zinc-200/70 dark:divide-zinc-800/70">
              {ranked.map(({ m, chaos }) => {
                const k = kickoffUnix(m)
                const idx = chaos?.index ?? 0
                const badge = chaosBadge(idx)
                const why = (chaos?.flags ?? []).slice(0, 4).join(", ")
                const upset = Boolean(chaos?.upset)
                const bp = bestProb(m)

                return (
                  <tr
                    key={m.match_id}
                    className="hover:bg-zinc-50/50 dark:hover:bg-zinc-900/30 cursor-pointer"
                    onClick={() => onOpenMatch(String(m.match_id))}
                    title="Click per aprire i dettagli del match"
                  >
                    <td className="px-3 py-2 text-zinc-700 dark:text-zinc-200">{fmtKickoff(k)}</td>

                    <td className="px-3 py-2">
                      <div className="font-semibold text-zinc-900 dark:text-zinc-50">
                        {m.home_team} <span className="text-zinc-400">vs</span> {m.away_team}
                      </div>
                      <div className="text-xs text-zinc-600 dark:text-zinc-300">
                        Best prob: {(bp * 100).toFixed(0)}% • Conf: {(Number(m.confidence ?? 0) * 100).toFixed(0)}%
                      </div>
                    </td>

                    <td className="px-3 py-2 text-zinc-700 dark:text-zinc-200">{m.championship}</td>

                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        {badge ? (
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(badge.tone)}`}>
                            {badge.label} {idx.toFixed(0)}
                          </span>
                        ) : (
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("zinc")}`}>
                            {idx.toFixed(0)}
                          </span>
                        )}

                        {upset ? (
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("red")}`}>
                            UPSET
                          </span>
                        ) : null}
                      </div>
                    </td>

                    <td className="px-3 py-2 text-xs text-zinc-600 dark:text-zinc-300">
                      {why ? (
                        <span title={why}>
                          {why}
                          {chaos && chaos.flags.length > 4 ? "…" : ""}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>

                    <td className="px-3 py-2 text-xs text-zinc-700 dark:text-zinc-200">
                      {idx >= 85 ? "NO BET consigliato" : idx >= 70 ? "Prudenza alta" : "Prudenza media"}
                    </td>
                  </tr>
                )
              })}

              {!ranked.length ? (
                <tr>
                  <td className="px-3 py-6 text-zinc-600 dark:text-zinc-300" colSpan={6}>
                    Nessun match con Chaos ≥ 55 tra quelli visibili (o Chaos non ancora calcolato).
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  )
}
