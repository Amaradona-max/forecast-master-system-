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

function pillClass(tone: "green" | "yellow" | "red" | "blue" | "zinc") {
  if (tone === "green") return "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
  if (tone === "yellow") return "border-amber-500/20 bg-amber-500/15 text-amber-700 dark:text-amber-300"
  if (tone === "red") return "border-red-500/20 bg-red-500/15 text-red-700 dark:text-red-300"
  if (tone === "blue") return "border-sky-500/20 bg-sky-500/15 text-sky-700 dark:text-sky-300"
  return "border-zinc-500/20 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
}

function chaosFromExplain(explain?: Record<string, unknown>) {
  const e = (explain ?? {}) as Record<string, unknown>
  const chaos0 = e?.chaos
  if (!chaos0 || typeof chaos0 !== "object") return null
  const chaos = chaos0 as Record<string, unknown>
  const idx = Number(chaos.index ?? NaN)
  if (!Number.isFinite(idx)) return null
  const upset = Boolean(chaos.upset_watch)
  const flags = Array.isArray(chaos.flags) ? (chaos.flags as unknown[]).map(String) : []
  const f0 = chaos.features
  const f = f0 && typeof f0 === "object" ? (f0 as Record<string, unknown>) : {}
  const homeStd = Number(f.home_points_std_last10 ?? NaN)
  const awayStd = Number(f.away_points_std_last10 ?? NaN)
  const homeRest = Number(f.home_rest_days ?? NaN)
  const awayRest = Number(f.away_rest_days ?? NaN)
  const h10 = Number(f.home_matches_last10d ?? NaN)
  const a10 = Number(f.away_matches_last10d ?? NaN)

  return {
    index: idx,
    upset,
    flags,
    features: {
      homeStd: Number.isFinite(homeStd) ? homeStd : null,
      awayStd: Number.isFinite(awayStd) ? awayStd : null,
      homeRest: Number.isFinite(homeRest) ? homeRest : null,
      awayRest: Number.isFinite(awayRest) ? awayRest : null,
      home10: Number.isFinite(h10) ? h10 : null,
      away10: Number.isFinite(a10) ? a10 : null
    }
  }
}

function severity(idx: number) {
  if (idx >= 85) return { label: "Estremo", tone: "red" as const }
  if (idx >= 70) return { label: "Alto", tone: "yellow" as const }
  if (idx >= 55) return { label: "Medio", tone: "blue" as const }
  return { label: "Basso", tone: "zinc" as const }
}

function fmtPct(v: number) {
  const x = Math.max(0, Math.min(1, Number(v))) * 100
  return `${x.toFixed(0)}%`
}

export function ChaosInsights({ matches }: { matches: OverviewMatchLite[] }) {
  const [open, setOpen] = useState(true)

  const insights = useMemo(() => {
    const ms = (matches ?? [])
      .map((m) => ({ m, chaos: chaosFromExplain(m.explain) }))
      .filter((x) => x.chaos !== null)

    const total = ms.length
    const hi70 = ms.filter((x) => (x.chaos?.index ?? 0) >= 70).length
    const hi85 = ms.filter((x) => (x.chaos?.index ?? 0) >= 85).length
    const upset = ms.filter((x) => Boolean(x.chaos?.upset)).length

    const byLeague: Record<string, { n: number; sum: number; hi70: number; upset: number }> = {}
    for (const x of ms) {
      const champ = String(x.m.championship ?? "")
      if (!champ) continue
      const idx = Number(x.chaos?.index ?? 0)
      const obj = (byLeague[champ] ||= { n: 0, sum: 0, hi70: 0, upset: 0 })
      obj.n += 1
      obj.sum += idx
      if (idx >= 70) obj.hi70 += 1
      if (x.chaos?.upset) obj.upset += 1
    }

    const leagueRows = Object.entries(byLeague)
      .map(([championship, v]) => ({
        championship,
        n: v.n,
        avg: v.n ? v.sum / v.n : 0,
        hi70: v.hi70,
        upset: v.upset
      }))
      .sort((a, b) => b.avg - a.avg)
      .slice(0, 6)

    const flagCount: Record<string, number> = {}
    for (const x of ms) {
      for (const f of x.chaos?.flags ?? []) {
        flagCount[f] = (flagCount[f] || 0) + 1
      }
    }
    const topFlags = Object.entries(flagCount)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([flag, count]) => ({ flag, count }))

    const teamVol: Record<string, { n: number; sumStd: number; maxStd: number }> = {}
    for (const x of ms) {
      const c = x.chaos
      if (!c) continue
      const hs = c.features.homeStd
      const as = c.features.awayStd
      const ht = String(x.m.home_team ?? "")
      const at = String(x.m.away_team ?? "")
      if (ht && typeof hs === "number") {
        const o = (teamVol[ht] ||= { n: 0, sumStd: 0, maxStd: 0 })
        o.n += 1
        o.sumStd += hs
        o.maxStd = Math.max(o.maxStd, hs)
      }
      if (at && typeof as === "number") {
        const o = (teamVol[at] ||= { n: 0, sumStd: 0, maxStd: 0 })
        o.n += 1
        o.sumStd += as
        o.maxStd = Math.max(o.maxStd, as)
      }
    }
    const topVolTeams = Object.entries(teamVol)
      .map(([team, v]) => ({
        team,
        n: v.n,
        avgStd: v.n ? v.sumStd / v.n : 0,
        maxStd: v.maxStd
      }))
      .sort((a, b) => b.avgStd - a.avgStd)
      .slice(0, 6)

    const recs: { label: string; tone: "green" | "yellow" | "red" | "blue" | "zinc" }[] = []
    if (hi85 >= 1) recs.push({ label: `NO BET consigliato su ${hi85} match (Chaos≥85)`, tone: "red" })
    if (hi70 >= 3) recs.push({ label: `Prudenza alta: ${hi70} match con Chaos≥70`, tone: "yellow" })
    if (upset >= 1) recs.push({ label: `Upset Watch attivo su ${upset} match`, tone: "red" })
    if (!recs.length && total) recs.push({ label: "Nessun segnale di caos rilevante: condizioni stabili", tone: "green" })
    if (!total) recs.push({ label: "Chaos non disponibile: controlla che Pack SORPRESA v1 sia attivo", tone: "zinc" })

    return {
      total,
      hi70,
      hi85,
      upset,
      leagueRows,
      topFlags,
      topVolTeams,
      recs
    }
  }, [matches])

  return (
    <Card className="mt-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Chaos Insights</div>
          <div className="text-xs text-zinc-600 dark:text-zinc-300">
            Sintesi automatica: campionati pericolosi, squadre volatili, pattern frequenti. Ottimo per decidere velocemente.
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
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap gap-2">
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("zinc")}`}>
              Match con Chaos: {insights.total}
            </span>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("blue")}`}>
              Chaos≥55: {Math.max(0, insights.total)}
            </span>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("yellow")}`}>
              Chaos≥70: {insights.hi70}
            </span>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("red")}`}>
              Chaos≥85: {insights.hi85}
            </span>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("red")}`}>
              Upset Watch: {insights.upset}
            </span>
          </div>

          <div className="flex flex-wrap gap-2">
            {insights.recs.map((r, i) => (
              <span key={i} className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(r.tone)}`}>
                {r.label}
              </span>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <div className="rounded-3xl border border-zinc-200/70 bg-white/50 p-3 dark:border-zinc-800/70 dark:bg-zinc-950/25">
              <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">Campionati più instabili (Top)</div>
              <div className="mt-2 overflow-auto rounded-2xl border border-zinc-200/70 dark:border-zinc-800/70">
                <table className="min-w-[360px] w-full text-left text-xs">
                  <thead className="bg-zinc-50/70 dark:bg-zinc-950/30">
                    <tr className="text-zinc-700 dark:text-zinc-200">
                      <th className="px-2 py-2">Camp.</th>
                      <th className="px-2 py-2">N</th>
                      <th className="px-2 py-2">Chaos avg</th>
                      <th className="px-2 py-2">≥70</th>
                      <th className="px-2 py-2">Upset</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-200/70 dark:divide-zinc-800/70">
                    {insights.leagueRows.map((r) => {
                      const sev = severity(r.avg)
                      return (
                        <tr key={r.championship} className="hover:bg-zinc-50/40 dark:hover:bg-zinc-900/25">
                          <td className="px-2 py-2 font-semibold text-zinc-900 dark:text-zinc-50">{r.championship}</td>
                          <td className="px-2 py-2 text-zinc-700 dark:text-zinc-200">{r.n}</td>
                          <td className="px-2 py-2">
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(sev.tone)}`}>
                              {r.avg.toFixed(0)} ({sev.label})
                            </span>
                          </td>
                          <td
                            className="px-2 py-2 text-zinc-700 dark:text-zinc-200"
                            title={`Chaos≥70: ${r.hi70} (${fmtPct(r.n ? r.hi70 / r.n : 0)})`}
                          >
                            {r.hi70}
                          </td>
                          <td
                            className="px-2 py-2 text-zinc-700 dark:text-zinc-200"
                            title={`Upset: ${r.upset} (${fmtPct(r.n ? r.upset / r.n : 0)})`}
                          >
                            {r.upset}
                          </td>
                        </tr>
                      )
                    })}
                    {!insights.leagueRows.length ? (
                      <tr>
                        <td className="px-2 py-4 text-zinc-600 dark:text-zinc-300" colSpan={5}>
                          n/d
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="rounded-3xl border border-zinc-200/70 bg-white/50 p-3 dark:border-zinc-800/70 dark:bg-zinc-950/25">
              <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">Top squadre volatili (punti std last10)</div>
              <div className="mt-2 space-y-2">
                {insights.topVolTeams.map((t) => (
                  <div key={t.team} className="flex items-center justify-between rounded-2xl border border-zinc-200/70 bg-white/60 px-3 py-2 dark:border-zinc-800/70 dark:bg-zinc-950/25">
                    <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">{t.team}</div>
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(t.avgStd >= 1.3 ? "red" : t.avgStd >= 1.1 ? "yellow" : "zinc")}`}>
                        avg {t.avgStd.toFixed(2)}
                      </span>
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("zinc")}`}>
                        n {t.n}
                      </span>
                    </div>
                  </div>
                ))}
                {!insights.topVolTeams.length ? (
                  <div className="text-xs text-zinc-600 dark:text-zinc-300">n/d</div>
                ) : null}
              </div>
              <div className="mt-2 text-[11px] text-zinc-600 dark:text-zinc-300">
                Nota: “volatile” = rendimento altalenante → aumenta imprevedibilità.
              </div>
            </div>

            <div className="rounded-3xl border border-zinc-200/70 bg-white/50 p-3 dark:border-zinc-800/70 dark:bg-zinc-950/25">
              <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">Pattern frequenti (flags)</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {insights.topFlags.map((f) => (
                  <span
                    key={f.flag}
                    title={`${f.flag} • occorrenze: ${f.count}`}
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("blue")}`}
                  >
                    {f.flag} · {f.count}
                  </span>
                ))}
                {!insights.topFlags.length ? (
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("zinc")}`}>n/d</span>
                ) : null}
              </div>
              <div className="mt-2 text-[11px] text-zinc-600 dark:text-zinc-300">
                Suggerimento: se vedi spesso <span className="font-semibold">rest_gap</span> e <span className="font-semibold">congestion</span>, alza prudenza.
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  )
}
