"use client"

import { useEffect, useMemo, useState } from "react"
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts"

import { apiUrl, fetchSeasonProgress } from "@/components/api/client"
import { Card } from "@/components/widgets/Card"

type OverviewMatch = {
  match_id: string
  championship: string
  home_team: string
  away_team: string
  status: string
  matchday?: number | null
  kickoff_unix?: number | null
  updated_at_unix: number
  probabilities: Record<string, number>
  confidence: number
  explain?: Record<string, unknown>
  final_score?: { home: number; away: number } | null
}

type MatchdayBlock = { matchday_number?: number | null; matchday_label: string; matches: OverviewMatch[] }

type ChampionshipOverview = {
  championship: string
  title: string
  matchdays: MatchdayBlock[]
  finished?: OverviewMatch[]
}

type ChampionshipsOverviewResponse = { generated_at_utc: string; championships: ChampionshipOverview[] }

const CHAMP_LABELS: Record<string, string> = {
  serie_a: "Serie A",
  premier_league: "Premier",
  la_liga: "La Liga",
  bundesliga: "Bundesliga",
  eliteserien: "Eliteserien"
}

const CHAMP_COLORS: Record<string, string> = {
  serie_a: "#22c55e",
  premier_league: "#a855f7",
  la_liga: "#3b82f6",
  bundesliga: "#ef4444",
  eliteserien: "#f59e0b"
}

function clamp01(x: number) {
  if (Number.isNaN(x)) return 0
  return x < 0 ? 0 : x > 1 ? 1 : x
}

function fmtPct(x: number) {
  return `${Math.round(clamp01(x) * 100)}%`
}

function shortTeam(s: string) {
  const v = String(s || "").trim()
  if (!v) return "Team"
  return v.length > 13 ? `${v.slice(0, 12)}…` : v
}

function safeProb(m: OverviewMatch, k: "home_win" | "draw" | "away_win") {
  return clamp01(Number((m.probabilities ?? {})[k] ?? 0))
}

function bestProb(m: OverviewMatch) {
  return Math.max(safeProb(m, "home_win"), safeProb(m, "draw"), safeProb(m, "away_win"))
}

function sortKickoff(a: OverviewMatch, b: OverviewMatch) {
  const ka = Number(a.kickoff_unix ?? 0)
  const kb = Number(b.kickoff_unix ?? 0)
  return ka - kb
}

function formatKickoff(kickoffUnix?: number | null) {
  const v = Number(kickoffUnix)
  if (!Number.isFinite(v) || v <= 0) return null
  const dt = new Date(v * 1000)
  if (Number.isNaN(dt.getTime())) return null
  return new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(dt)
}

function teamForm(finished: OverviewMatch[], team: string) {
  const t = String(team || "").trim()
  if (!t) return []
  const rel = finished
    .filter((m) => (m.final_score && (m.home_team === t || m.away_team === t)))
    .slice()
    .sort((a, b) => Number(b.kickoff_unix ?? 0) - Number(a.kickoff_unix ?? 0))
    .slice(0, 5)
  const out: ("W" | "D" | "L")[] = []
  for (const m of rel) {
    const fs = m.final_score
    if (!fs) continue
    const hg = Number(fs.home)
    const ag = Number(fs.away)
    if (Number.isNaN(hg) || Number.isNaN(ag)) continue
    if (hg === ag) out.push("D")
    else if (m.home_team === t) out.push(hg > ag ? "W" : "L")
    else out.push(ag > hg ? "W" : "L")
  }
  return out
}

function derivedStats(matches: OverviewMatch[]) {
  const active = matches.length ? matches : []
  let xgSum = 0
  let bttsSum = 0
  let overSum = 0
  let used = 0
  for (const m of active) {
    const exp = (m.explain ?? {}) as Record<string, unknown>
    const comps = (exp.components ?? {}) as Record<string, unknown>
    const d = (exp.derived_markets ?? {}) as Record<string, unknown>
    const lh = Number(comps.lam_home ?? 0)
    const la = Number(comps.lam_away ?? 0)
    const btts = Number(d.btts ?? 0)
    const over = Number(d.over_2_5 ?? 0)
    if (Number.isFinite(lh) && Number.isFinite(la)) xgSum += Math.max(0, lh + la)
    if (Number.isFinite(btts)) bttsSum += clamp01(btts)
    if (Number.isFinite(over)) overSum += clamp01(over)
    used += 1
  }
  if (!used) return { xg: 0, btts: 0, over25: 0 }
  return { xg: xgSum / used, btts: bttsSum / used, over25: overSum / used }
}

function expectedPointsTable(matches: OverviewMatch[]) {
  const points: Record<string, number> = {}
  for (const m of matches) {
    const p1 = safeProb(m, "home_win")
    const px = safeProb(m, "draw")
    const p2 = safeProb(m, "away_win")
    const homePts = (3 * p1) + (1 * px)
    const awayPts = (3 * p2) + (1 * px)
    const h = String(m.home_team || "").trim() || "Home"
    const a = String(m.away_team || "").trim() || "Away"
    points[h] = (points[h] ?? 0) + homePts
    points[a] = (points[a] ?? 0) + awayPts
  }
  return Object.entries(points)
    .map(([team, v]) => ({ team, teamShort: shortTeam(team), pts: v }))
    .sort((a, b) => b.pts - a.pts)
}

function probabilityTrend(matchdays: MatchdayBlock[]) {
  return matchdays
    .filter((md) => (md.matches ?? []).length > 0)
    .map((md) => {
      const ms = (md.matches ?? []).filter((m) => m.status !== "FINISHED")
      const base = ms.length ? ms : (md.matches ?? [])
      const n = base.length || 1
      const p1 = base.reduce((acc, m) => acc + safeProb(m, "home_win"), 0) / n
      const px = base.reduce((acc, m) => acc + safeProb(m, "draw"), 0) / n
      const p2 = base.reduce((acc, m) => acc + safeProb(m, "away_win"), 0) / n
      return { md: md.matchday_label, p1, px, p2 }
    })
}

function champOrderKey(champ: string) {
  const order = ["serie_a", "premier_league", "la_liga", "bundesliga", "eliteserien"]
  const i = order.indexOf(champ)
  return i === -1 ? 999 : i
}

export function StatisticalPredictionsDashboard() {
  const [overview, setOverview] = useState<ChampionshipOverview[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedChamp, setSelectedChamp] = useState<string>("serie_a")
  const [selectedMdKey, setSelectedMdKey] = useState<string>("")
  const [seasonAuc, setSeasonAuc] = useState<number | null>(null)

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const res = await fetch(apiUrl("/api/v1/overview/championships"), { cache: "no-store" })
        if (!res.ok) throw new Error(`overview_failed:${res.status}`)
        const json = (await res.json()) as ChampionshipsOverviewResponse
        if (!active) return
        const list = [...(json.championships ?? [])].sort((a, b) => champOrderKey(a.championship) - champOrderKey(b.championship))
        setOverview(list)
      } catch (e) {
        if (!active) return
        setError(String((e as Error)?.message ?? e))
      }
    }
    load()
    const t = window.setInterval(load, 30_000)
    return () => {
      active = false
      window.clearInterval(t)
    }
  }, [])

  useEffect(() => {
    let active = true
    fetchSeasonProgress(selectedChamp)
      .then((r) => {
        const pts = r.points ?? []
        const last = pts.length ? pts[pts.length - 1] : null
        if (!active) return
        setSeasonAuc(typeof last?.roc_auc === "number" ? last.roc_auc : null)
      })
      .catch(() => {
        if (!active) return
        setSeasonAuc(null)
      })
    return () => {
      active = false
    }
  }, [selectedChamp])

  const champ = useMemo(() => {
    const list = overview ?? []
    const found = list.find((c) => c.championship === selectedChamp)
    return found ?? list[0] ?? null
  }, [overview, selectedChamp])

  const matchdays = useMemo(() => champ?.matchdays ?? [], [champ])
  const matchdayKeys = useMemo(() => matchdays.map((m) => `${m.matchday_number ?? "md"}:${m.matchday_label}`), [matchdays])
  const finished = useMemo(() => champ?.finished ?? [], [champ])

  useEffect(() => {
    if (!matchdays.length) return
    if (!selectedMdKey || !matchdayKeys.includes(selectedMdKey)) {
      setSelectedMdKey(matchdayKeys[0] ?? "")
    }
  }, [matchdayKeys, matchdays.length, selectedMdKey])

  const selectedMd = useMemo(() => {
    if (!selectedMdKey) return matchdays[0] ?? null
    const idx = matchdayKeys.indexOf(selectedMdKey)
    return idx >= 0 ? matchdays[idx] : (matchdays[0] ?? null)
  }, [matchdayKeys, matchdays, selectedMdKey])

  const toPlay = useMemo(() => (selectedMd?.matches ?? []).filter((m) => m.status !== "FINISHED"), [selectedMd])

  const nextMatches = useMemo(() => {
    return toPlay
      .slice()
      .sort((a, b) => bestProb(b) - bestProb(a))
      .slice(0, 4)
  }, [toPlay])

  const stats = useMemo(() => derivedStats(toPlay), [toPlay])
  const trend = useMemo(() => probabilityTrend(matchdays), [matchdays])
  const power = useMemo(() => expectedPointsTable(toPlay).slice(0, 5), [toPlay])

  const topFormTeams = useMemo(() => {
    const list = expectedPointsTable(toPlay).slice(0, 5)
    return list.map((r) => ({ team: r.team, form: teamForm(finished, r.team) }))
  }, [finished, toPlay])

  const title = (champ?.title ?? CHAMP_LABELS[selectedChamp] ?? "Dashboard").toUpperCase()
  const activeColor = CHAMP_COLORS[selectedChamp] ?? "#22c55e"
  const matchesCount = toPlay.length
  const avgBest = matchesCount ? toPlay.reduce((acc, m) => acc + bestProb(m), 0) / matchesCount : 0
  const gaugeValue = avgBest

  if (error) {
    return (
      <Card>
        <div className="text-sm font-semibold tracking-tight">Dashboard</div>
        <div className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">{error}</div>
      </Card>
    )
  }

  if (!overview || !champ) {
    return (
      <Card>
        <div className="text-sm font-semibold tracking-tight">Dashboard</div>
        <div className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">Caricamento dati…</div>
      </Card>
    )
  }

  return (
    <div className="relative rounded-[28px] border border-zinc-200/40 bg-[radial-gradient(circle_at_top,rgba(30,58,138,0.18),transparent_55%),radial-gradient(circle_at_top_right,rgba(190,18,60,0.14),transparent_55%),linear-gradient(180deg,rgba(24,24,27,0.25),rgba(24,24,27,0.05))] p-5 shadow-sm backdrop-blur-md dark:border-zinc-800/50 dark:bg-[radial-gradient(circle_at_top,rgba(59,130,246,0.18),transparent_55%),radial-gradient(circle_at_top_right,rgba(244,63,94,0.16),transparent_55%),linear-gradient(180deg,rgba(9,9,11,0.72),rgba(9,9,11,0.45))]">
      <div className="pointer-events-none absolute inset-0 rounded-[28px] ring-1 ring-white/10 dark:ring-white/10" />

      <div className="flex items-center justify-between gap-4 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 backdrop-blur-md dark:bg-zinc-950/25">
        <div className="min-w-0">
          <div className="text-xs font-semibold tracking-[0.18em] text-zinc-700 dark:text-zinc-200">
            FOOTBALL LEAGUE ANALYTICS & FORECASTS
          </div>
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
            {title} · {selectedMd?.matchday_label ?? "Giornata"} · ROC-AUC {seasonAuc == null ? "n/d" : seasonAuc.toFixed(3)}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {overview.map((c) => {
            const isActive = c.championship === selectedChamp
            const col = CHAMP_COLORS[c.championship] ?? "#3b82f6"
            return (
              <button
                key={c.championship}
                type="button"
                onClick={() => setSelectedChamp(c.championship)}
                className={[
                  "flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold shadow-sm backdrop-blur-md transition",
                  isActive
                    ? "border-white/20 bg-white/20 text-zinc-900 dark:bg-white/10 dark:text-zinc-50"
                    : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:text-zinc-200"
                ].join(" ")}
                aria-pressed={isActive}
              >
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: col }} />
                <span>{CHAMP_LABELS[c.championship] ?? c.title}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
        <Card className="lg:col-span-3 !bg-white/10 !p-4 dark:!bg-zinc-950/25">
          <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">League Overview</div>
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Seleziona giornata e vista rapida</div>
          <div className="mt-4">
            <div className="text-[11px] text-zinc-600 dark:text-zinc-300">Giornata</div>
            <select
              value={selectedMdKey}
              onChange={(e) => setSelectedMdKey(e.target.value)}
              className="mt-2 w-full rounded-xl border border-white/10 bg-white/10 px-3 py-2 text-xs text-zinc-900 shadow-sm backdrop-blur-md dark:bg-zinc-950/35 dark:text-zinc-50"
              aria-label="Seleziona giornata"
            >
              {matchdays.map((m) => {
                const key = `${m.matchday_number ?? "md"}:${m.matchday_label}`
                return (
                  <option key={key} value={key}>
                    {m.matchday_label}
                  </option>
                )
              })}
            </select>
          </div>

          <div className="mt-5 rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
            <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">Top Teams Form</div>
            <div className="mt-2 space-y-2">
              {topFormTeams.length ? (
                topFormTeams.map((r) => (
                  <div key={r.team} className="flex items-center justify-between gap-3 text-xs">
                    <div className="min-w-0 truncate text-zinc-800 dark:text-zinc-100">{r.team}</div>
                    <div className="shrink-0 flex items-center gap-1">
                      {r.form.length ? (
                        r.form.map((x, i) => (
                          <span
                            key={`${r.team}-${i}`}
                            className={[
                              "grid h-5 w-5 place-items-center rounded-md border border-white/10 text-[10px] font-semibold",
                              x === "W" ? "bg-emerald-500/20 text-emerald-200" : x === "D" ? "bg-amber-500/20 text-amber-200" : "bg-red-500/20 text-red-200"
                            ].join(" ")}
                          >
                            {x}
                          </span>
                        ))
                      ) : (
                        <span className="text-[11px] text-zinc-600 dark:text-zinc-300">n/d</span>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-xs text-zinc-600 dark:text-zinc-300">n/d</div>
              )}
            </div>
          </div>
        </Card>

        <div className="lg:col-span-6 space-y-4">
          <Card className="!bg-white/10 dark:!bg-zinc-950/25">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Next Match Predictions</div>
                <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Top 4 per probabilità massima</div>
              </div>
              <div className="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-[11px] text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
                Gare: {matchesCount} · Media: {fmtPct(avgBest)}
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {nextMatches.length ? (
                nextMatches.slice().sort(sortKickoff).map((m) => {
                  const p1 = safeProb(m, "home_win")
                  const px = safeProb(m, "draw")
                  const p2 = safeProb(m, "away_win")
                  const kickoffLabel = formatKickoff(m.kickoff_unix)
                  return (
                    <div
                      key={m.match_id}
                      className="rounded-2xl border border-white/10 bg-white/10 px-3 py-3 backdrop-blur-md dark:bg-zinc-950/20"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                            {m.home_team} <span className="text-zinc-500 dark:text-zinc-400">vs</span> {m.away_team}
                          </div>
                          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
                            {kickoffLabel ? <span>{kickoffLabel} · </span> : null}
                            Conf {fmtPct(bestProb(m))} · {m.status}
                          </div>
                        </div>
                        <div className="shrink-0 text-right text-xs font-semibold text-zinc-900 dark:text-zinc-50">
                          {Math.round(p1 * 100)}% / {Math.round(px * 100)}% / {Math.round(p2 * 100)}%
                        </div>
                      </div>
                      <div className="mt-3 overflow-hidden rounded-xl border border-white/10 bg-zinc-950/30">
                        <div className="flex h-7 w-full text-[11px] font-semibold text-white">
                          <div className="grid place-items-center bg-blue-500/70" style={{ width: `${Math.round(p1 * 100)}%` }}>1</div>
                          <div className="grid place-items-center bg-violet-500/70" style={{ width: `${Math.round(px * 100)}%` }}>X</div>
                          <div className="grid place-items-center bg-rose-500/70" style={{ width: `${Math.round(p2 * 100)}%` }}>2</div>
                        </div>
                      </div>
                    </div>
                  )
                })
              ) : (
                <div className="text-sm text-zinc-600 dark:text-zinc-300">Nessuna gara disponibile.</div>
              )}
            </div>
          </Card>

          <Card className="!bg-white/10 dark:!bg-zinc-950/25">
            <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Win Probability Chart</div>
            <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Trend medio 1 / X / 2 per giornata</div>
            <div className="mt-4 h-52 rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend}>
                  <XAxis dataKey="md" hide />
                  <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(Number(v) * 100)}%`} />
                  <Tooltip formatter={(v) => fmtPct(Number(v))} />
                  <Line type="monotone" dataKey="p1" stroke="#3b82f6" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="px" stroke="#a855f7" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="p2" stroke="#f43f5e" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>

        <Card className="lg:col-span-3 !bg-white/10 !p-4 dark:!bg-zinc-950/25">
          <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Stats & Trends</div>
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Metriche derivate dal modello</div>

          <div className="mt-4 space-y-3">
            <MetricRow label="Goal Averages" value={`${stats.xg.toFixed(2)} goals/match`} accent={activeColor} />
            <MetricRow label="BTTS" value={fmtPct(stats.btts)} accent="#3b82f6" />
            <MetricRow label="Over 2.5 Goals" value={fmtPct(stats.over25)} accent="#f59e0b" />
          </div>

          <div className="mt-5 rounded-2xl border border-white/10 bg-white/10 p-4 dark:bg-zinc-950/20">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">Confidence Index</div>
              <div className="text-[11px] text-zinc-600 dark:text-zinc-300">{selectedMd?.matchday_label ?? "Giornata"}</div>
            </div>
            <div className="mt-4 flex items-center justify-center">
              <Gauge value={gaugeValue} />
            </div>
          </div>

          <div className="mt-5 rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
            <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">Power Rankings</div>
            <div className="mt-2 space-y-2">
              {power.length ? (
                power.map((r, idx) => (
                  <div key={r.team} className="flex items-center justify-between gap-3 text-xs">
                    <div className="min-w-0 truncate text-zinc-800 dark:text-zinc-100">
                      {idx + 1}. {r.team}
                    </div>
                    <div className="shrink-0 rounded-full border border-white/10 bg-white/10 px-2 py-1 text-[11px] text-zinc-700 dark:bg-zinc-950/15 dark:text-zinc-200">
                      {r.pts.toFixed(2)}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-xs text-zinc-600 dark:text-zinc-300">n/d</div>
              )}
            </div>
          </div>
        </Card>
      </div>

      <div className="mt-4">
        <Card className="!bg-white/10 dark:!bg-zinc-950/25">
          <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Performance Comparison</div>
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Confronto rapido tra leghe (giornata selezionata)</div>
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-5">
            {overview.map((c) => {
              const md0 = (c.matchdays ?? [])[0]
              const toPlay0 = (md0?.matches ?? []).filter((m) => m.status !== "FINISHED")
              const s0 = derivedStats(toPlay0)
              const col = CHAMP_COLORS[c.championship] ?? "#22c55e"
              return (
                <Card key={c.championship} className="!bg-white/10 !p-3 dark:!bg-zinc-950/20">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">{CHAMP_LABELS[c.championship] ?? c.title}</div>
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: col }} />
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-zinc-600 dark:text-zinc-300">
                    <div className="rounded-xl border border-white/10 bg-white/10 px-2 py-2 dark:bg-zinc-950/15">
                      <div className="text-[10px] uppercase tracking-wide">Goals</div>
                      <div className="mt-1 text-xs font-semibold text-zinc-900 dark:text-zinc-50">{s0.xg.toFixed(2)}</div>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/10 px-2 py-2 dark:bg-zinc-950/15">
                      <div className="text-[10px] uppercase tracking-wide">BTTS</div>
                      <div className="mt-1 text-xs font-semibold text-zinc-900 dark:text-zinc-50">{fmtPct(s0.btts)}</div>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/10 px-2 py-2 dark:bg-zinc-950/15">
                      <div className="text-[10px] uppercase tracking-wide">Over 2.5</div>
                      <div className="mt-1 text-xs font-semibold text-zinc-900 dark:text-zinc-50">{fmtPct(s0.over25)}</div>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/10 px-2 py-2 dark:bg-zinc-950/15">
                      <div className="text-[10px] uppercase tracking-wide">Matches</div>
                      <div className="mt-1 text-xs font-semibold text-zinc-900 dark:text-zinc-50">{toPlay0.length}</div>
                    </div>
                  </div>
                </Card>
              )
            })}
          </div>
        </Card>
      </div>
    </div>
  )
}

function MetricRow({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs text-zinc-600 dark:text-zinc-300">{label}</div>
        <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">{value}</div>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-zinc-950/40">
        <div className="h-1.5" style={{ width: "70%", backgroundColor: accent }} />
      </div>
    </div>
  )
}

function Gauge({ value }: { value: number }) {
  const v = clamp01(value)
  const r = 42
  const c = 2 * Math.PI * r
  const dash = c * v
  const gap = c - dash
  const pct = Math.round(v * 100)
  return (
    <div className="relative h-40 w-40">
      <svg viewBox="0 0 120 120" className="h-full w-full">
        <defs>
          <linearGradient id="gaugeGradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#22c55e" />
            <stop offset="55%" stopColor="#f59e0b" />
            <stop offset="100%" stopColor="#ef4444" />
          </linearGradient>
        </defs>
        <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(255,255,255,0.10)" strokeWidth="14" />
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke="url(#gaugeGradient)"
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${gap}`}
          transform="rotate(-90 60 60)"
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <div className="text-center">
          <div className="text-4xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">{pct}%</div>
          <div className="mt-1 text-[11px] text-zinc-600 dark:text-zinc-300">confidence</div>
        </div>
      </div>
    </div>
  )
}
