"use client"

import { useMemo } from "react"

import { Card } from "@/components/widgets/Card"
import { type OverviewMatch } from "@/components/widgets/MatchCard"
import { FragilityBadge, type Fragility } from "@/components/widgets/FragilityBadge"

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

function fmtKickoff(k: number | null) {
  if (!k) return "n/d"
  const d = new Date(k * 1000)
  return d.toLocaleString(undefined, { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
}

function pillClass(tone: "green" | "yellow" | "red" | "blue" | "zinc") {
  if (tone === "green") return "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
  if (tone === "yellow") return "border-amber-500/20 bg-amber-500/15 text-amber-700 dark:text-amber-300"
  if (tone === "red") return "border-red-500/20 bg-red-500/15 text-red-700 dark:text-red-300"
  if (tone === "blue") return "border-sky-500/20 bg-sky-500/15 text-sky-700 dark:text-sky-300"
  return "border-zinc-500/20 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
}

function chaosBadge(idx: number) {
  if (idx >= 85) return { label: "CHAOS🔥", tone: "red" as const }
  if (idx >= 70) return { label: "CHAOS↑", tone: "yellow" as const }
  if (idx >= 55) return { label: "CHAOS", tone: "blue" as const }
  return { label: "CHAOS", tone: "zinc" as const }
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
  const hiCand =
    base
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
      .filter((x) => x.upset || (x.bestProb >= 0.45 && x.bestProb <= 0.60))
      .filter((x) => x.chaos >= 55)
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

  const allPicks = useMemo(() => {
    const out: Array<{ championship: string; label: string; pick: PickRow }> = []
    grouped.forEach(({ championship, picks }) => {
      const label = champLabels?.[championship] ?? championship
      picks.forEach((pick) => out.push({ championship, label, pick }))
    })
    return out.sort((a, b) => {
      const ak = a.pick.kind === "LOW" || a.pick.kind === "PLAY" ? 0 : 1
      const bk = b.pick.kind === "LOW" || b.pick.kind === "PLAY" ? 0 : 1
      if (ak !== bk) return ak - bk
      if (b.pick.bestProb !== a.pick.bestProb) return b.pick.bestProb - a.pick.bestProb
      return a.pick.chaos - b.pick.chaos
    })
  }, [grouped, champLabels])

  const featured = useMemo(() => allPicks.slice(0, 2), [allPicks])
  const rest = useMemo(() => allPicks.slice(2), [allPicks])

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

      <div className="mt-4 bento-grid">
        {featured.map(({ label, pick }) => {
          const m = pick.match
          const cb = chaosBadge(pick.chaos)
          const kindTone = pick.kind === "LOW" || pick.kind === "PLAY" ? "green" : "red"
          return (
            <button
              key={String(m.match_id)}
              type="button"
              onClick={() => onOpenMatch(String(m.match_id))}
              className="bento-col-8 card-wow text-left hover:shadow-medium"
              title="Click per aprire i dettagli (Explain)"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[11px] font-semibold text-zinc-600 dark:text-zinc-300">{label}</div>
                  <div className="mt-1 text-base font-extrabold tracking-tight text-zinc-900 dark:text-zinc-50">
                    {m.home_team} <span className="text-zinc-400">vs</span> {m.away_team}
                  </div>
                  <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">{fmtKickoff(m.kickoff_unix ?? null)}</div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full border px-2 py-1 text-[10px] font-extrabold ${pillClass(kindTone)}`}>
                    {pick.kind === "PLAY" ? "PLAY" : pick.kind}
                  </span>
                  <span className={`rounded-full border px-2 py-1 text-[10px] font-extrabold ${pillClass(cb.tone)}`}>
                    {cb.label}
                  </span>
                  {pick.upset ? (
                    <span className={`rounded-full border px-2 py-1 text-[10px] font-extrabold ${pillClass("red")}`}>UPSET</span>
                  ) : null}
                  <span className={`rounded-full border px-2 py-1 text-[10px] font-extrabold ${pillClass("zinc")}`}>
                    Best {Math.round(pick.bestProb * 100)}%
                  </span>
                  <span className={`rounded-full border px-2 py-1 text-[10px] font-extrabold ${pillClass("zinc")}`}>
                    Conf {Math.round(clamp01(Number(m.confidence ?? 0)) * 100)}%
                  </span>
                  <FragilityBadge fragility={fragilityFromExplain(m.explain)} />
                </div>
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-3">
                <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
                  <div className="text-[11px] font-semibold text-zinc-600 dark:text-zinc-300">Perché</div>
                  <div className="mt-1 line-clamp-3">
                    {pick.why?.length ? `• ${pick.why.slice(0, 3).join(" • ")}` : "• segnali standard"}
                  </div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
                  <div className="text-[11px] font-semibold text-zinc-600 dark:text-zinc-300">Riepilogo</div>
                  <div className="mt-1 space-y-1">
                    <div className="flex items-center justify-between">
                      <span>Rischio (Chaos)</span>
                      <span className="font-bold">{Math.round(pick.chaos)}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Tipo</span>
                      <span className="font-bold">{pick.kind}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Best prob</span>
                      <span className="font-bold">{Math.round(pick.bestProb * 100)}%</span>
                    </div>
                  </div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
                  <div className="text-[11px] font-semibold text-zinc-600 dark:text-zinc-300">Azione</div>
                  <div className="mt-2 text-[11px] text-zinc-600 dark:text-zinc-300">
                    Apri “Perché?” per Decision Gate, EV, Drift e Simili.
                  </div>
                  <div className="mt-2 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-[11px] font-bold dark:bg-zinc-950/20">
                    Dettagli →
                  </div>
                </div>
              </div>
            </button>
          )
        })}

        <div className="bento-col-4 card-wow">
          <div className="text-xs font-bold text-zinc-700 dark:text-zinc-200">Quick stats</div>
          <div className="mt-2 grid gap-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-zinc-600 dark:text-zinc-300">Totale pick</span>
              <span className="font-extrabold text-zinc-900 dark:text-zinc-50">{allPicks.length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-zinc-600 dark:text-zinc-300">Featured</span>
              <span className="font-extrabold text-zinc-900 dark:text-zinc-50">{featured.length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-zinc-600 dark:text-zinc-300">Modalità</span>
              <span className="font-extrabold text-zinc-900 dark:text-zinc-50">{mode}</span>
            </div>
            <div className="h-px bg-white/10" />
            <div className="text-[11px] text-zinc-600 dark:text-zinc-300">
              Sotto trovi l’elenco per campionato (compatto).
            </div>
          </div>
        </div>

        {rest.map(({ championship, label, pick }) => {
          const m = pick.match
          const cb = chaosBadge(pick.chaos)
          const kindTone = pick.kind === "LOW" || pick.kind === "PLAY" ? "green" : "red"
          return (
            <button
              key={`${championship}-${String(m.match_id)}`}
              type="button"
              onClick={() => onOpenMatch(String(m.match_id))}
              className="bento-col-12 card-wow text-left p-4"
              title="Click per aprire i dettagli (Explain)"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-[11px] font-semibold text-zinc-600 dark:text-zinc-300">{label}</div>
                  <div className="text-sm font-extrabold text-zinc-900 dark:text-zinc-50">
                    {m.home_team} <span className="text-zinc-400">vs</span> {m.away_team}
                  </div>
                  <div className="text-[11px] text-zinc-600 dark:text-zinc-300">{fmtKickoff(m.kickoff_unix ?? null)}</div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass(kindTone)}`}>
                    {pick.kind === "PLAY" ? "PLAY" : pick.kind}
                  </span>
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass(cb.tone)}`}>
                    {cb.label}
                  </span>
                  {pick.upset ? (
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass("red")}`}>UPSET</span>
                  ) : null}
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass("zinc")}`}>
                    Best {Math.round(pick.bestProb * 100)}%
                  </span>
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass("zinc")}`}>
                    Conf {Math.round(clamp01(Number(m.confidence ?? 0)) * 100)}%
                  </span>
                  <FragilityBadge fragility={fragilityFromExplain(m.explain)} />
                </div>
              </div>

              <div className="mt-2 text-[11px] text-zinc-600 dark:text-zinc-300">
                {pick.why?.length ? (
                  <span title={pick.why.join(", ")}>
                    Perché: {pick.why.slice(0, 3).join(", ")}
                    {pick.why.length >= 4 ? "…" : ""}
                  </span>
                ) : (
                  <span>Perché: segnali standard</span>
                )}
              </div>
            </button>
          )
        })}

        <details className="bento-col-12 rounded-3xl border border-white/10 bg-white/40 p-4 text-sm dark:bg-zinc-950/15">
          <summary className="cursor-pointer select-none text-xs font-bold text-zinc-800 dark:text-zinc-100">
            Elenco per campionato (compatto)
          </summary>
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
                              <div className="text-[11px] text-zinc-600 dark:text-zinc-300">{fmtKickoff(m.kickoff_unix ?? null)}</div>
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
                  </div>
                </div>
              )
            })}
          </div>
        </details>
      </div>
    </Card>
  )
}
