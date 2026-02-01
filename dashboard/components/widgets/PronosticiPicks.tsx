"use client"

import { useMemo } from "react"

import { Card } from "@/components/widgets/Card"
import { FragilityBadge, type Fragility } from "@/components/widgets/FragilityBadge"

type OverviewMatch = {
  match_id: string
  championship: string
  home_team: string
  away_team: string
  status: string
  kickoff_unix?: number | null
  updated_at_unix: number
  probabilities: Record<string, number>
  confidence: number
  explain?: Record<string, unknown>
}

type Mode = "play" | "recover"

type PickRow = {
  match: OverviewMatch
  kind: "PLAY" | "LOW" | "HIGH"
  bestProb: number
  chaos: number
  upset: boolean
  score: number
  why: string[]
}

function clamp01(x: number) {
  if (Number.isNaN(x)) return 0
  return x < 0 ? 0 : x > 1 ? 1 : x
}

function bestProb(m: OverviewMatch) {
  const vals = Object.values(m?.probabilities ?? {})
    .map((v) => Number(v ?? 0))
    .filter((v) => Number.isFinite(v))
  return vals.length ? Math.max(...vals) : 0
}

function chaosFromExplain(explain?: Record<string, unknown>) {
  const chaos0 = explain?.chaos
  if (!chaos0 || typeof chaos0 !== "object") return { idx: 50, upset: false, flags: [] as string[] }
  const chaos = chaos0 as Record<string, unknown>
  const idx = Number(chaos.index ?? NaN)
  const upset = Boolean(chaos.upset_watch)
  const flags0 = chaos.flags
  const flags = Array.isArray(flags0) ? flags0.map((x) => String(x)) : []
  return { idx: Number.isFinite(idx) ? idx : 50, upset, flags }
}

function fragilityFromExplain(explain?: Record<string, unknown>): Fragility | null {
  const frag0 = explain?.fragility
  if (!frag0 || typeof frag0 !== "object") return null
  const frag = frag0 as Record<string, unknown>
  return { level: String(frag.level ?? "") }
}

function fmtKickoff(unix: number | null | undefined) {
  const k = Number(unix ?? 0)
  if (!Number.isFinite(k) || k <= 0) return "n/d"
  return new Date(k * 1000).toLocaleString(undefined, { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
}

function pillClass(tone: "green" | "yellow" | "red" | "blue" | "zinc") {
  if (tone === "green") return "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
  if (tone === "yellow") return "border-amber-500/20 bg-amber-500/15 text-amber-700 dark:text-amber-300"
  if (tone === "red") return "border-red-500/20 bg-red-500/15 text-red-700 dark:text-red-300"
  if (tone === "blue") return "border-sky-500/20 bg-sky-500/15 text-sky-700 dark:text-sky-300"
  return "border-zinc-500/20 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
}

function chaosBadge(idx: number) {
  if (idx >= 85) return { label: `CHAOS🔥 ${idx.toFixed(0)}`, tone: "red" as const }
  if (idx >= 70) return { label: `CHAOS↑ ${idx.toFixed(0)}`, tone: "yellow" as const }
  if (idx >= 55) return { label: `CHAOS ${idx.toFixed(0)}`, tone: "blue" as const }
  return { label: `CHAOS ${idx.toFixed(0)}`, tone: "zinc" as const }
}

function isPlayableBase(m: OverviewMatch) {
  const s = String(m.status || "").toUpperCase()
  return s !== "FINISHED" && s !== "FT" && s !== "AET" && s !== "PEN"
}

function pickPlayForLeague(matches: OverviewMatch[]): PickRow[] {
  const scored = matches
    .filter(isPlayableBase)
    .map((m) => {
      const bp = clamp01(bestProb(m))
      const conf = clamp01(Number(m.confidence ?? 0))
      const c = chaosFromExplain(m.explain)
      const chaos = Math.max(0, Math.min(100, Number(c.idx)))
      const chaosN = chaos / 100

      // Filtri prudenziali
      const score = 0.55 * bp + 0.35 * conf + 0.10 * (1 - chaosN)

      return {
        match: m,
        kind: "PLAY" as const,
        bestProb: bp,
        chaos,
        upset: c.upset,
        score,
        why: c.flags.slice(0, 4)
      }
    })
    .filter((x) => x.kind === "PLAY" && x.chaos < 70 && x.bestProb >= 0.55 && clamp01(Number(x.match.confidence ?? 0)) >= 0.60)
    .sort((a, b) => b.score - a.score)

  return scored.slice(0, 2)
}

function pickRecoverForLeague(matches: OverviewMatch[]): PickRow[] {
  const base = matches.filter(isPlayableBase)

  // LOW = migliore prudenziale
  const low = pickPlayForLeague(base)[0] || null

  // HIGH = più varianza (senza quote): preferiamo partite “tirate” + caos/UPSET
  const hiCand = base
    .map((m) => {
      const bp = clamp01(bestProb(m))
      const conf = clamp01(Number(m.confidence ?? 0))
      const c = chaosFromExplain(m.explain)
      const chaos = Math.max(0, Math.min(100, Number(c.idx)))
      const chaosN = chaos / 100

      const riskScore = 0.55 * (1 - bp) + 0.35 * chaosN + 0.10 * (1 - conf)

      return {
        match: m,
        kind: "HIGH" as const,
        bestProb: bp,
        chaos,
        upset: c.upset,
        score: riskScore,
        why: c.flags.slice(0, 4)
      }
    })
    .filter((x) => x.match.match_id !== low?.match.match_id)
    .filter((x) => clamp01(Number(x.match.confidence ?? 0)) >= 0.40)
    .filter((x) => (x.upset || (x.bestProb >= 0.45 && x.bestProb <= 0.60)) && x.chaos >= 55)
    .sort((a, b) => b.score - a.score)[0] || null

  // fallback HIGH = secondo migliore prudenziale, se non troviamo candidati “volatili”
  const fallbackHigh = (() => {
    const alt = pickPlayForLeague(base).slice(1, 2)[0]
    if (!alt) return null
    return { ...alt, kind: "HIGH" as const }
  })()

  const high = hiCand ?? fallbackHigh

  const out: PickRow[] = []
  if (low) out.push({ ...low, kind: "LOW" })
  if (high) out.push(high)
  return out
}

export function PronosticiPicks({
  matches,
  mode,
  champLabels,
  onOpenMatch
}: {
  matches: OverviewMatch[]
  mode: Mode
  champLabels: Record<string, string>
  onOpenMatch: (matchId: string) => void
}) {
  const grouped = useMemo(() => {
    const by: Record<string, OverviewMatch[]> = {}
    for (const m of matches ?? []) {
      const c = String(m.championship || "")
      if (!c) continue
      ;(by[c] ||= []).push(m)
    }

    const rows = Object.entries(by).map(([championship, ms]) => {
      const picks = mode === "play" ? pickPlayForLeague(ms) : pickRecoverForLeague(ms)
      return { championship, picks }
    })

    // Ordina campionati: prima quelli con picks “migliori”
    rows.sort((a, b) => {
      const sa = a.picks.reduce((s, x) => s + x.score, 0)
      const sb = b.picks.reduce((s, x) => s + x.score, 0)
      return sb - sa
    })

    return rows
  }, [matches, mode])

  return (
    <Card className="mt-4">
      <div>
        <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          {mode === "play" ? "Pronostici da giocare" : "Pronostici per recuperare"}
        </div>
        <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
          {mode === "play"
            ? "2 gare per campionato: profilo prudente (Chaos basso, conf alta, best-prob alta)."
            : "2 gare per campionato: 1 low-risk + 1 high-risk (più varianza/UPSET)."}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 xl:grid-cols-2 gap-3">
        {grouped.map(({ championship, picks }) => {
          const label = champLabels?.[championship] ?? championship
          return (
            <div
              key={championship}
              className="rounded-3xl border border-zinc-200/70 bg-white/55 p-3 dark:border-zinc-800/70 dark:bg-zinc-950/25"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">{label}</div>
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(picks.length ? "green" : "zinc")}`}>
                  {picks.length ? `${picks.length} pick` : "n/d"}
                </span>
              </div>

              <div className="mt-2 space-y-2">
                {picks.map((p) => {
                  const m = p.match
                  const cb = chaosBadge(p.chaos)
                  const kindTone = p.kind === "LOW" || p.kind === "PLAY" ? "green" : "red"
                  return (
                    <button
                      key={m.match_id}
                      type="button"
                      onClick={() => onOpenMatch(String(m.match_id))}
                      className="w-full text-left rounded-2xl border border-zinc-200/70 bg-white/70 px-3 py-2 hover:bg-white dark:border-zinc-800/70 dark:bg-zinc-950/25"
                      title="Click per aprire i dettagli (Explain)"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">
                            {m.home_team} <span className="text-zinc-400">vs</span> {m.away_team}
                          </div>
                          <div className="text-[11px] text-zinc-600 dark:text-zinc-300">{fmtKickoff(m.kickoff_unix)}</div>
                        </div>

                        <div className="flex items-center gap-2">
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(kindTone)}`}>
                            {p.kind === "PLAY" ? "PLAY" : p.kind}
                          </span>

                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(cb.tone)}`}>
                            {cb.label}
                          </span>

                          {p.upset ? (
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("red")}`}>
                              UPSET
                            </span>
                          ) : null}

                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("zinc")}`}>
                            Best {Math.round(p.bestProb * 100)}%
                          </span>

                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("zinc")}`}>
                            Conf {Math.round(clamp01(Number(m.confidence ?? 0)) * 100)}%
                          </span>

                          <FragilityBadge fragility={fragilityFromExplain(m.explain)} />
                        </div>
                      </div>

                      <div className="mt-1 text-[11px] text-zinc-600 dark:text-zinc-300">
                        {p.why?.length ? (
                          <span title={p.why.join(", ")}>
                            Perché: {p.why.join(", ")}
                            {p.why.length >= 4 ? "…" : ""}
                          </span>
                        ) : (
                          <span>Perché: segnali standard</span>
                        )}
                      </div>
                    </button>
                  )
                })}

                {!picks.length ? (
                  <div className="text-xs text-zinc-600 dark:text-zinc-300">
                    Nessuna selezione disponibile con i filtri attuali (es. Chaos alto o confidence bassa).
                  </div>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
