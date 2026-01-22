"use client"

import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react"
import dynamic from "next/dynamic"

import type { ExplainResponse, MultiMarketConfidenceResponse, TeamToPlay, TeamsToPlayResponse, TenantConfig, TrackRecordResponse, UserProfile } from "@/components/api/types"
import {
  apiFetchTenant,
  fetchTenantConfig,
  fetchSystemStatus,
  fetchExplainMatch,
  fetchExplainTeam,
  fetchMultiMarketConfidence,
  fetchSeasonProgress,
  fetchTeamsToPlay,
  fetchTrackRecord,
  fetchUserProfile,
  getApiBaseUrl,
  updateUserProfile
} from "@/components/api/client"
import { Card } from "@/components/widgets/Card"
import { LeaguePerformanceTable } from "@/components/widgets/LeaguePerformanceTable"
import { NextMatchItem } from "@/components/widgets/matches/NextMatchItem"
import { WatchlistItem } from "@/components/widgets/watchlist/WatchlistItem"
import { Modal } from "@/components/ui/Modal"
import { VirtualList } from "@/components/ui/VirtualList"
import { useLocalStorage } from "@/lib/useLocalStorage"

const WinProbabilityChart = dynamic(
  () => import("./charts/WinProbabilityChart").then((m) => m.WinProbabilityChart),
  { ssr: false, loading: () => <div className="mt-4 h-52 rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20" /> }
)
const TrackRecordChart = dynamic(
  () => import("./charts/TrackRecordChart").then((m) => m.TrackRecordChart),
  { ssr: false, loading: () => <div className="mt-4 h-56 rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20" /> }
)

type OverviewMatch = {
  match_id: string
  championship: string
  league?: string
  competition?: string
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
  _from_watchlist_only?: boolean
}

type MatchdayBlock = { matchday_number?: number | null; matchday_label: string; matches: OverviewMatch[] }

type ChampionshipOverview = {
  championship: string
  title: string
  matchdays: MatchdayBlock[]
  finished?: OverviewMatch[]
}

type ChampionshipsOverviewResponse = { generated_at_utc: string; championships: ChampionshipOverview[] }

type BacktestMetricsResponse = {
  ok: boolean
  error?: string
  meta?: Record<string, unknown>
  generated_at_unix?: number | null
  championships: Record<string, Record<string, unknown>>
}

type BacktestTrendsResponse = {
  ok: boolean
  error?: string
  meta?: Record<string, unknown>
  generated_at_unix?: number | null
  championships: Record<string, Record<string, unknown>>
}

const CHAMP_LABELS: Record<string, string> = {
  serie_a: "Serie A",
  premier_league: "Premier League",
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

function fmtPct100(x: number) {
  const n = Number(x)
  if (!Number.isFinite(n)) return "n/d"
  const v = n < 0 ? 0 : n > 100 ? 100 : n
  return `${v.toFixed(1)}%`
}

function fmtSigned(x: number) {
  const n = Number(x)
  if (!Number.isFinite(n)) return "n/d"
  const s = n >= 0 ? "+" : ""
  return `${s}${n.toFixed(2)}`
}

function confidenceLabel(score: number) {
  const v = clamp01(Number(score ?? 0))
  if (v >= 0.7) return "HIGH"
  if (v >= 0.4) return "MEDIUM"
  return "LOW"
}

function confidenceRank(label: string) {
  const v = String(label || "").toUpperCase()
  if (v === "HIGH") return 2
  if (v === "MEDIUM") return 1
  return 0
}

function riskLevel(explain?: Record<string, unknown>) {
  const e = (explain ?? {}) as Record<string, unknown>
  const safeMode = Boolean(e.safe_mode)
  const missing = e.missing_flags
  const missingCount = Array.isArray(missing) ? missing.length : 0
  return safeMode || missingCount > 0 ? "MEDIUM" : "LOW"
}

function marketDisplayName(key: string) {
  const k = String(key || "").toUpperCase()
  if (k === "OVER_2_5") return "Over 2.5"
  if (k === "BTTS") return "BTTS"
  if (k === "1X2") return "1X2"
  return k || "Market"
}

function riskRank(risk: string) {
  const r = String(risk || "").toUpperCase()
  if (r === "LOW") return 2
  if (r === "MEDIUM") return 1
  return 0
}

function normalizeMarketKey(v: unknown) {
  return String(v ?? "").trim().toUpperCase()
}

type MarketLite = { confidence: number; risk: string; probability?: number }

function bestMarketKey(markets: Record<string, MarketLite>) {
  const entries = Object.entries(markets ?? {})
  if (!entries.length) return ""
  entries.sort((a, b) => {
    const ac = Number(a[1]?.confidence ?? 0)
    const bc = Number(b[1]?.confidence ?? 0)
    if (bc !== ac) return bc - ac
    return riskRank(String(b[1]?.risk ?? "")) - riskRank(String(a[1]?.risk ?? ""))
  })
  return String(entries[0]?.[0] ?? "")
}

function isUnstableMarket(m: MarketLite) {
  const c = Number(m?.confidence ?? 0)
  const r = String(m?.risk ?? "").toUpperCase()
  return r === "HIGH" || c < 45
}

type ProfileKey = "PRUDENT" | "BALANCED" | "AGGRESSIVE"

function filterMarketsByTenant(markets: Record<string, MarketLite>, activeMarkets: unknown) {
  const allow0 = Array.isArray(activeMarkets) ? activeMarkets : []
  const allow = allow0.map((x) => normalizeMarketKey(x)).filter(Boolean)
  if (!allow.length) return markets
  const out: Record<string, MarketLite> = {}
  for (const k of allow) {
    const mk = markets[k]
    if (mk) out[k] = mk
  }
  return out
}

function normalizeProfileKey(v: unknown): ProfileKey {
  const s = String(v ?? "").trim().toUpperCase()
  if (s === "PRUDENTE") return "PRUDENT"
  if (s === "AGGRESSIVO") return "AGGRESSIVE"
  if (s === "PRUDENT" || s === "BALANCED" || s === "AGGRESSIVE") return s
  return "BALANCED"
}

function profileTooltip(p: ProfileKey) {
  if (p === "PRUDENT") return "Mostra solo confidence alta e risk LOW. Stake ridotto."
  if (p === "AGGRESSIVE") return "Include anche risk MEDIUM/HIGH. Stake più flessibile."
  return "Default: confidence media-alta e risk LOW/MEDIUM."
}

function matchRisk(m: OverviewMatch) {
  const conf = confidenceLabel(Number(m.confidence ?? 0))
  const base = riskLevel(m.explain ?? undefined)
  if (conf === "LOW") return "HIGH"
  if (String(base).toUpperCase() === "MEDIUM") return "MEDIUM"
  return "LOW"
}

function matchAllowedByProfile(m: OverviewMatch, profile: ProfileKey) {
  const conf = confidenceLabel(Number(m.confidence ?? 0))
  const risk = matchRisk(m)
  if (profile === "PRUDENT") return conf === "HIGH" && risk === "LOW"
  if (profile === "BALANCED") return conf !== "LOW" && risk !== "HIGH"
  return true
}

function stakePctForProfile(profile: ProfileKey, conf: string, risk: string) {
  const base = stakePct(conf, risk)
  if (profile === "PRUDENT") return Math.min(2.0, Math.max(0.5, base * 0.7))
  if (profile === "AGGRESSIVE") return Math.min(6.0, Math.max(0.5, base * 1.2))
  return base
}

function readLocalProfile(): ProfileKey | null {
  if (typeof window === "undefined") return null
  try {
    const v = window.localStorage.getItem("user_profile")
    if (!v) return null
    return normalizeProfileKey(v)
  } catch {
    return null
  }
}

function writeLocalProfile(p: ProfileKey) {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem("user_profile", p)
  } catch {}
}

function stakePct(conf: string, risk: string) {
  const c = String(conf || "").toUpperCase()
  const r = String(risk || "").toUpperCase()
  if (c === "LOW") return 1.0
  if (c === "HIGH" && r === "LOW") return 4.5
  if (c === "HIGH" && r === "MEDIUM") return 3.0
  if (c === "MEDIUM" && r === "LOW") return 2.0
  return 1.25
}

function stakeUnits(bankroll: number, pct: number) {
  const br = Number(bankroll)
  const p = Number(pct)
  if (!Number.isFinite(br) || br <= 0) return 0
  if (!Number.isFinite(p) || p <= 0) return 0
  return Math.max(0, Math.round(br * p / 100))
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
  type WatchItem = {
    id: string
    home: string
    away: string
    kickoff_unix?: number
    league?: string
    pinned?: boolean
  }

  const [watchlist, setWatchlist] = useLocalStorage<WatchItem[]>("fm_watchlist_v1", [])
  const [overview, setOverview] = useState<ChampionshipOverview[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [systemStatus, setSystemStatus] = useState<{ data_provider: string; data_error?: string | null; football_data_key_present: boolean; api_football_key_present: boolean } | null>(null)
  const [selectedChamp, setSelectedChamp] = useState<string>("serie_a")
  const [selectedMdKey, setSelectedMdKey] = useState<string>("")
  const [seasonAuc, setSeasonAuc] = useState<number | null>(null)
  const [backtestMetrics, setBacktestMetrics] = useState<BacktestMetricsResponse | null>(null)
  const [backtestTrends, setBacktestTrends] = useState<BacktestTrendsResponse | null>(null)
  const [leagueMetrics, setLeagueMetrics] = useState<Record<string, unknown>>({})
  const [leagueTrends, setLeagueTrends] = useState<Record<string, unknown>>({})
  const [teamsToPlay, setTeamsToPlay] = useState<TeamsToPlayResponse | null>(null)
  const [teamsToPlayError, setTeamsToPlayError] = useState<string | null>(null)
  const [trackDays, setTrackDays] = useState<number>(120)
  const [trackRecord, setTrackRecord] = useState<TrackRecordResponse | null>(null)
  const [trackError, setTrackError] = useState<string | null>(null)
  const [bankroll, setBankroll] = useState<number>(100)
  const [profile, setProfile] = useState<ProfileKey>("BALANCED")
  const [tenantConfig, setTenantConfig] = useState<TenantConfig | null>(null)
  const [profileLoaded, setProfileLoaded] = useState<boolean>(false)
  const [mobileControlsOpen, setMobileControlsOpen] = useState<boolean>(false)
  const [matchQuery, setMatchQuery] = useState<string>("")
  const [sortMode, setSortMode] = useState<"kickoff" | "prob" | "confidence">("prob")
  const [onlyGood, setOnlyGood] = useState<boolean>(false)
  const [hideNoBet, setHideNoBet] = useState<boolean>(false)
  const [performanceOpen, setPerformanceOpen] = useState<boolean>(false)
  const [detailOpen, setDetailOpen] = useState<boolean>(false)
  const [detailMatch, setDetailMatch] = useState<(OverviewMatch & { p1: number; px: number; p2: number }) | null>(null)
  const [watchSearch, setWatchSearch] = useState<string>("")
  const [watchShowAll, setWatchShowAll] = useState<boolean>(false)
  const [watchModalOpen, setWatchModalOpen] = useState<boolean>(false)
  const [uiNotice, setUiNotice] = useState<string>("")
  const [pageVisible, setPageVisible] = useState(true)
  const deferredMatchQuery = useDeferredValue(matchQuery)
  const deferredWatchSearch = useDeferredValue(watchSearch)

  const showUINotice = useCallback((msg: string) => {
    setUiNotice(msg)
    window.setTimeout(() => {
      setUiNotice("")
    }, 2500)
  }, [])

  const [openTeamExplain, setOpenTeamExplain] = useState<string>("")
  const [teamExplain, setTeamExplain] = useState<ExplainResponse | null>(null)
  const [teamExplainError, setTeamExplainError] = useState<string | null>(null)
  const [teamExplainLoading, setTeamExplainLoading] = useState<boolean>(false)

  const [openMatchExplainId, setOpenMatchExplainId] = useState<string>("")
  const [expandedMatchId, setExpandedMatchId] = useState<string>("")
  const [matchExplain, setMatchExplain] = useState<ExplainResponse | null>(null)
  const [matchExplainError, setMatchExplainError] = useState<string | null>(null)
  const [matchExplainLoading, setMatchExplainLoading] = useState<boolean>(false)
  const [multiMarket, setMultiMarket] = useState<MultiMarketConfidenceResponse | null>(null)
  const [multiMarketError, setMultiMarketError] = useState<string | null>(null)
  const [multiMarketLoading, setMultiMarketLoading] = useState<boolean>(false)
  const [selectedMarketKey, setSelectedMarketKey] = useState<string>("")
  const openMatchExplainIdRef = useRef<string>("")

  type WatchMatchLike = {
    home_team?: unknown
    away_team?: unknown
    kickoff_unix?: unknown
    kickoff?: unknown
    league?: unknown
    competition?: unknown
    championship?: unknown
  }

  const matchId = useCallback((m: WatchMatchLike) => {
    const home = String(m?.home_team ?? "")
    const away = String(m?.away_team ?? "")
    const ko = m?.kickoff_unix ?? m?.kickoff ?? ""
    if (!home && !away && !ko) return ""
    return `${home}__${away}__${ko}`
  }, [])

  const toFallbackMatch = useCallback((w: WatchItem): OverviewMatch & { _from_watchlist_only: true } => {
    return {
      match_id: w.id,
      championship: "",
      league: w.league,
      competition: w.league,
      home_team: w.home,
      away_team: w.away,
      status: "SAVED",
      matchday: null,
      kickoff_unix: w.kickoff_unix ?? null,
      updated_at_unix: Math.floor(Date.now() / 1000),
      probabilities: {},
      confidence: 0,
      final_score: null,
      _from_watchlist_only: true
    }
  }, [])

  const isHistorical = (m: unknown) => {
    const obj = m as { _from_watchlist_only?: unknown } | null | undefined
    return Boolean(obj?._from_watchlist_only)
  }

  const isWatched = useCallback((m: WatchMatchLike) => watchlist.some((w) => w.id === matchId(m)), [matchId, watchlist])

  const toggleWatch = useCallback(
    (m: WatchMatchLike) => {
      const id = matchId(m)
      if (!id) return

      setWatchlist((prev) => {
        if (prev.some((w) => w.id === id)) return prev.filter((w) => w.id !== id)
        const item: WatchItem = {
          id,
          home: String(m.home_team ?? ""),
          away: String(m.away_team ?? ""),
          kickoff_unix: Number(m.kickoff_unix ?? NaN),
          league: String(m.league ?? m.competition ?? m.championship ?? ""),
          pinned: false
        }
        return [item, ...prev].slice(0, 20)
      })
    },
    [matchId, setWatchlist]
  )

  const pinnedCount = watchlist.filter((w) => w.pinned).length

  const isPinned = useCallback((m: WatchMatchLike) => {
    const id = matchId(m)
    return watchlist.some((w) => w.id === id && w.pinned)
  }, [matchId, watchlist])

  const togglePin = useCallback(
    (m: WatchMatchLike) => {
      const id = matchId(m)
      if (!id) return

      setWatchlist((prev) => {
        const currentlyPinned = prev.some((w) => w.id === id && w.pinned)
        const pinnedCountNow = prev.filter((w) => w.pinned).length
        if (!currentlyPinned && pinnedCountNow >= 3) {
          showUINotice("Hai già 3 PIN attivi. Rimuovine uno per aggiungerne un altro.")
          return prev
        }
        return prev.map((w) => (w.id === id ? { ...w, pinned: !currentlyPinned } : w))
      })
    },
    [matchId, setWatchlist, showUINotice]
  )

  const onToggleWatch = useCallback((m: WatchMatchLike) => toggleWatch(m), [toggleWatch])
  const onTogglePin = useCallback((m: WatchMatchLike) => togglePin(m), [togglePin])

  const isLiveMatch = useCallback((m: unknown) => {
    const obj = m as Record<string, unknown> | null | undefined
    if (obj?.is_live === true) return true
    const s = String(obj?.status ?? obj?.match_status ?? "").toLowerCase()
    if (["live", "inplay", "in_play", "in-play", "playing"].includes(s)) return true
    const minute = Number(obj?.minute ?? obj?.match_minute ?? 0)
    if (Number.isFinite(minute) && minute > 0) return true
    return false
  }, [])

  const confValue = useCallback((m: unknown) => {
    const obj = m as Record<string, unknown> | null | undefined
    const c = obj?.confidence ?? obj?.model_confidence ?? obj?.prediction_confidence
    return typeof c === "number" ? clamp01(c) : 0
  }, [])

  const qualityScore = useCallback((m: unknown) => {
    const p = clamp01(bestProb(m as OverviewMatch))
    const c = clamp01(confValue(m))
    const score = 0.65 * p + 0.35 * c
    if (score >= 0.8) return { grade: "A" as const, score }
    if (score >= 0.7) return { grade: "B" as const, score }
    if (score >= 0.6) return { grade: "C" as const, score }
    return { grade: "D" as const, score }
  }, [confValue])

  const riskLabel = (m: unknown) => {
    const p = clamp01(bestProb(m as OverviewMatch))
    const c = clamp01(confValue(m))
    if (p >= 0.7 && c >= 0.7) return { label: "Basso", tone: "green" as const }
    if (p >= 0.6 && c >= 0.6) return { label: "Medio", tone: "yellow" as const }
    return { label: "Alto", tone: "red" as const }
  }

  const leagueReliability = (championship: string) => {
    const row0 = leagueMetrics?.[String(championship)]
    if (!row0 || typeof row0 !== "object") return { label: "n/d", tone: "zinc" as const }
    const row = row0 as Record<string, unknown>

    const ece = Number(row?.ece ?? 0)
    const acc = Number(row?.accuracy ?? 0)
    const n = Number(row?.n ?? 0)

    if (!Number.isFinite(n) || n < 80) return { label: "n/d", tone: "zinc" as const }

    if (ece <= 0.06 && acc >= 0.5) return { label: "Affidabile", tone: "green" as const }
    if (ece <= 0.09) return { label: "Medio", tone: "yellow" as const }
    return { label: "Instabile", tone: "red" as const }
  }

  const leagueTrend = (championship: string) => {
    if (!backtestTrends?.ok) return { label: "n/d", tone: "zinc" as const, title: "" }
    const row0 = leagueTrends?.[String(championship)]
    if (!row0 || typeof row0 !== "object") return { label: "n/d", tone: "zinc" as const, title: "" }
    const row = row0 as Record<string, unknown>
    if (row.ok !== true) return { label: "n/d", tone: "zinc" as const, title: "" }

    const dAcc = Number(row.delta_accuracy ?? NaN)
    const dEce = Number(row.delta_ece ?? NaN)
    if (!Number.isFinite(dAcc) || !Number.isFinite(dEce)) return { label: "n/d", tone: "zinc" as const, title: "" }

    const epsAcc = 0.01
    const epsEce = 0.005
    const betterAcc = dAcc >= epsAcc
    const worseAcc = dAcc <= -epsAcc
    const betterEce = dEce <= -epsEce
    const worseEce = dEce >= epsEce
    const title = `7g vs 30g · ΔAcc ${(dAcc * 100).toFixed(1)}pp · ΔECE ${dEce.toFixed(3)}`

    if (betterAcc && betterEce) return { label: "↑", tone: "green" as const, title }
    if (worseAcc && worseEce) return { label: "↓", tone: "red" as const, title }
    return { label: "→", tone: "zinc" as const, title }
  }

  const noBetReason = (m: unknown) => {
    const p = clamp01(bestProb(m as OverviewMatch))
    const c = clamp01(confValue(m))
    if (p < 0.55) return "Probabilità troppo bassa"
    if (c < 0.55) return "Affidabilità (confidence) bassa"
    return "Segnali non abbastanza forti"
  }

  const isNoBet = useCallback((m: unknown) => {
    const q = qualityScore(m)
    const p = clamp01(bestProb(m as OverviewMatch))
    const c = clamp01(confValue(m))
    return q.grade === "D" || p < 0.5 || c < 0.5
  }, [confValue, qualityScore])

  const pillClass = (tone: "green" | "yellow" | "red" | "zinc" | "blue") => {
    if (tone === "green") return "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
    if (tone === "yellow") return "border-amber-500/20 bg-amber-500/15 text-amber-700 dark:text-amber-300"
    if (tone === "red") return "border-red-500/20 bg-red-500/15 text-red-700 dark:text-red-300"
    if (tone === "blue") return "border-sky-500/20 bg-sky-500/15 text-sky-700 dark:text-sky-300"
    return "border-zinc-500/20 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
  }

  type Pick = { key: string; label: string; prob: number }

  const picksFromMatch = (m: unknown): Pick[] => {
    const obj = m as Record<string, unknown> | null | undefined

    const rawPicks = obj?.picks
    if (Array.isArray(rawPicks)) {
      return (rawPicks as unknown[])
        .map((p) => {
          const pp = p as Record<string, unknown> | null | undefined
          return {
            key: String(pp?.key ?? pp?.market ?? ""),
            label: String(pp?.label ?? pp?.name ?? pp?.key ?? ""),
            prob: Number(pp?.prob ?? pp?.probability ?? 0)
          }
        })
        .filter((p) => p.key && Number.isFinite(p.prob))
    }

    const p1 = Number(obj?.p1 ?? obj?.home_win_prob ?? obj?.prob_home ?? 0)
    const px = Number(obj?.px ?? obj?.draw_prob ?? obj?.prob_draw ?? 0)
    const p2 = Number(obj?.p2 ?? obj?.away_win_prob ?? obj?.prob_away ?? 0)
    const arr: Pick[] = []
    if (Number.isFinite(p1) && p1 > 0) arr.push({ key: "1", label: "1 (Casa)", prob: p1 })
    if (Number.isFinite(px) && px > 0) arr.push({ key: "X", label: "X (Pareggio)", prob: px })
    if (Number.isFinite(p2) && p2 > 0) arr.push({ key: "2", label: "2 (Trasferta)", prob: p2 })
    return arr
  }

  const topTwoPicks = (m: unknown) => {
    const ps = picksFromMatch(m).slice().sort((a, b) => b.prob - a.prob)
    const best = ps[0] ?? null
    const alt = ps[1] ?? null
    return { best, alt }
  }

  const adviceLine = (m: unknown) => {
    if (isNoBet(m)) return `Consiglio: NO BET — ${noBetReason(m)}.`

    const { best, alt } = topTwoPicks(m)
    const q = qualityScore(m)
    const r = riskLabel(m)

    if (!best) return "Consiglio: n/d."

    const gap = alt ? Math.max(0, best.prob - alt.prob) : best.prob
    const gapTxt = gap >= 0.10 ? "distacco netto" : gap >= 0.05 ? "distacco discreto" : "distacco basso"

    return `Consiglio: ${best.label} — Qualità ${q.grade}, Rischio ${r.label} (${gapTxt}).`
  }

  const reliabilityBadge = (m: unknown) => {
    const obj = m as { championship?: unknown; league?: unknown; competition?: unknown } | null | undefined
    const champ = String(obj?.championship ?? obj?.league ?? obj?.competition ?? "").trim()
    if (!champ) return null

    const rel = leagueReliability(champ)
    if (rel.label !== "n/d") {
      if (rel.tone === "green") return { label: "AFFIDABILE", kind: "rel_good" as const }
      if (rel.tone === "yellow") return { label: "MEDIO", kind: "rel_mid" as const }
      if (rel.tone === "red") return { label: "INSTABILE", kind: "rel_bad" as const }
    }

    const row0 = backtestMetrics?.championships?.[champ]
    if (!row0 || typeof row0 !== "object") return null
    const row = row0 as Record<string, unknown>
    const ece0 = Number(row.ece ?? row.expected_calibration_error ?? row.calibration_error ?? NaN)
    const acc0 = Number(row.accuracy ?? row.acc ?? NaN)
    if (!Number.isFinite(ece0) && !Number.isFinite(acc0)) return null
    const ece = Number.isFinite(ece0) ? ece0 : 1
    const acc = Number.isFinite(acc0) ? acc0 : 0
    if (ece <= 0.07 && acc >= 0.56) return { label: "AFFIDABILE", kind: "rel_good" as const }
    if (ece <= 0.10 && acc >= 0.52) return { label: "MEDIO", kind: "rel_mid" as const }
    return { label: "INSTABILE", kind: "rel_bad" as const }
  }

  const trendBadge = (m: unknown) => {
    const obj = m as { championship?: unknown; league?: unknown; competition?: unknown } | null | undefined
    const champ = String(obj?.championship ?? obj?.league ?? obj?.competition ?? "").trim()
    if (!champ) return null
    const t = leagueTrend(champ)
    if (t.label === "n/d") return null
    if (t.label === "↑") return { label: "↑", kind: "rel_good" as const }
    if (t.label === "↓") return { label: "↓", kind: "rel_bad" as const }
    return { label: "→", kind: "rel_mid" as const }
  }

  const badgeList = (m: unknown) => {
    const badges: { label: string; kind: "live" | "top" | "conf" | "rel_good" | "rel_mid" | "rel_bad" }[] = []

    const rb = reliabilityBadge(m)
    if (rb) badges.unshift(rb)

    const tb = trendBadge(m)
    if (tb) badges.unshift(tb)

    const db = dayBadge(m)
    if (db) badges.unshift({ label: db, kind: "top" })

    if (isLiveMatch(m)) badges.push({ label: "LIVE", kind: "live" })

    const p = bestProb(m as OverviewMatch)
    if (p >= 0.7) badges.push({ label: "TOP", kind: "top" })

    const c = confValue(m)
    if (c >= 0.75) badges.push({ label: "CONF", kind: "conf" })

    if (isNoBet(m)) badges.push({ label: "NO BET", kind: "conf" })

    const sb = soonBadge(m)
    if (sb) badges.push({ label: sb, kind: "live" })

    const kb = kickoffBadge(m)
    if (kb) badges.push({ label: kb, kind: "conf" })

    return badges
  }

  const kickoffUnix = (m: unknown) => {
    const obj = m as Record<string, unknown> | null | undefined
    const k = obj?.kickoff_unix ?? obj?.kickoff ?? obj?.start_time_unix ?? null
    const n = Number(k)
    return Number.isFinite(n) && n > 0 ? n : null
  }

  const minutesToKickoff = (m: unknown) => {
    const k = kickoffUnix(m)
    if (!k) return null
    const nowSec = Math.floor(Date.now() / 1000)
    return Math.floor((k - nowSec) / 60)
  }

  const formatKickoffTime = (m: unknown) => {
    const k = kickoffUnix(m)
    if (!k) return ""
    try {
      return new Intl.DateTimeFormat("it-IT", {
        hour: "2-digit",
        minute: "2-digit"
      }).format(new Date(k * 1000))
    } catch {
      return ""
    }
  }

  const dayBadge = (m: unknown) => {
    const k = kickoffUnix(m)
    if (!k) return null
    try {
      const d = new Date(k * 1000)
      const now = new Date()

      const a = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
      const b = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
      const diffDays = Math.round((b - a) / (1000 * 60 * 60 * 24))

      if (diffDays === 0) return "OGGI"
      if (diffDays === 1) return "DOMANI"

      const dd = String(d.getDate()).padStart(2, "0")
      const mm = String(d.getMonth() + 1).padStart(2, "0")
      return `${dd}/${mm}`
    } catch {
      return null
    }
  }

  const soonBadge = (m: unknown) => {
    if (isLiveMatch(m)) return null
    const mins = minutesToKickoff(m)
    if (mins === null) return null
    if (mins >= 0 && mins <= 15) return "TRA POCO"
    return null
  }

  const kickoffBadge = (m: unknown) => {
    if (isLiveMatch(m)) return null
    const mins = minutesToKickoff(m)
    if (mins === null) return null
    if (mins < 0) return null
    if (mins < 60) return `+${mins}m`
    const h = Math.floor(mins / 60)
    const r = mins % 60
    if (r === 0) return `+${h}h`
    return `+${h}h${r}`
  }

  useEffect(() => {
    openMatchExplainIdRef.current = openMatchExplainId
  }, [openMatchExplainId])

  useEffect(() => {
    const handler = () => setPageVisible(!document.hidden)
    handler()
    document.addEventListener("visibilitychange", handler)
    return () => document.removeEventListener("visibilitychange", handler)
  }, [])

  useEffect(() => {
    let active = true
    fetchTenantConfig()
      .then((cfg) => {
        if (!active) return
        setTenantConfig(cfg)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const brandName = String(tenantConfig?.branding?.app_name ?? "").trim()
    const champLabel = String(CHAMP_LABELS[selectedChamp] ?? selectedChamp).trim()
    if (typeof document !== "undefined") {
      document.title = brandName ? `${brandName} · ${champLabel}` : champLabel || "Dashboard"
    }
  }, [selectedChamp, tenantConfig?.branding?.app_name])

  useEffect(() => {
    if (!error || systemStatus) return
    let active = true
    fetchSystemStatus()
      .then((s) => {
        if (!active) return
        setSystemStatus({
          data_provider: String(s.data_provider ?? ""),
          data_error: s.data_error ?? null,
          football_data_key_present: Boolean(s.football_data_key_present),
          api_football_key_present: Boolean(s.api_football_key_present)
        })
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [error, systemStatus])

  useEffect(() => {
    const disabled = tenantConfig?.features?.disabled_profiles ?? []
    const disabledSet = new Set(disabled.map((p) => String(p ?? "").trim().toUpperCase()))
    if (!disabledSet.has(profile)) return
    const ordered: ProfileKey[] = ["BALANCED", "PRUDENT", "AGGRESSIVE"]
    const next = ordered.find((p) => !disabledSet.has(p)) ?? "BALANCED"
    setProfile(next)
  }, [profile, tenantConfig?.features?.disabled_profiles])

  useEffect(() => {
    if (profileLoaded) return
    const local = readLocalProfile()
    if (local) setProfile(local)
    setProfileLoaded(true)
    fetchUserProfile()
      .then((p: UserProfile) => {
        setProfile(normalizeProfileKey(p.profile))
        const br = Number(p.bankroll_reference ?? NaN)
        if (Number.isFinite(br) && br > 0) setBankroll(br)
        writeLocalProfile(normalizeProfileKey(p.profile))
      })
      .catch(() => {})
  }, [profileLoaded])

  useEffect(() => {
    if (!profileLoaded) return
    writeLocalProfile(profile)
    const t = window.setTimeout(() => {
      updateUserProfile({ profile, bankroll_reference: bankroll })
        .then(() => {})
        .catch(() => {})
    }, 350)
    return () => window.clearTimeout(t)
  }, [bankroll, profile, profileLoaded])

  useEffect(() => {
    if (!multiMarket || selectedMarketKey) return
    const mid = String(multiMarket.match_id ?? "").trim()
    if (!mid || mid !== openMatchExplainId) return
    const best = bestMarketKey(filterMarketsByTenant(multiMarket.markets ?? {}, tenantConfig?.filters?.active_markets))
    if (best) setSelectedMarketKey(best)
  }, [multiMarket, openMatchExplainId, selectedMarketKey, tenantConfig?.filters?.active_markets])

  useEffect(() => {
    let active = true
    async function load() {
      if (!pageVisible) return
      try {
        setError(null)
        const res = await apiFetchTenant("/api/v1/overview/championships", { cache: "no-store" })
        if (!res.ok) {
          let detail = ""
          try {
            const body = (await res.json()) as { detail?: unknown }
            if (body?.detail) detail = String(body.detail)
          } catch {}
          throw new Error(detail ? `overview_failed:${res.status}:${detail}` : `overview_failed:${res.status}`)
        }
        const json = (await res.json()) as ChampionshipsOverviewResponse
        if (!active) return
        const list = [...(json.championships ?? [])].sort((a, b) => champOrderKey(a.championship) - champOrderKey(b.championship))
        setOverview(list)
        setSystemStatus(null)
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
  }, [pageVisible])

  useEffect(() => {
    let active = true
    async function load() {
      if (!pageVisible) return
      try {
        let res = await apiFetchTenant("/api/backtest-metrics", { cache: "no-store" })
        if (!res.ok) res = await apiFetchTenant("/api/v1/backtest-metrics", { cache: "no-store" })
        if (!res.ok) throw new Error(`backtest_metrics_failed:${res.status}`)
        const json = (await res.json()) as BacktestMetricsResponse
        if (!active) return
        if (json?.ok && json?.championships) setLeagueMetrics(json.championships)
        setBacktestMetrics(json?.ok ? json : null)
      } catch {
        if (!active) return
        setBacktestMetrics(null)
      }

      try {
        let res = await apiFetchTenant("/api/backtest-trends", { cache: "no-store" })
        if (!res.ok) res = await apiFetchTenant("/api/v1/backtest-trends", { cache: "no-store" })
        if (!res.ok) throw new Error(`backtest_trends_failed:${res.status}`)
        const json = (await res.json()) as BacktestTrendsResponse
        if (!active) return
        if (json?.ok && json?.championships) setLeagueTrends(json.championships)
        setBacktestTrends(json?.ok ? json : null)
      } catch {
        if (!active) return
        setLeagueTrends({})
        setBacktestTrends(null)
      }
    }
    load()
    const t = window.setInterval(load, 60_000)
    return () => {
      active = false
      window.clearInterval(t)
    }
  }, [pageVisible])

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

  useEffect(() => {
    let active = true
    async function loadTeamsToPlay() {
      if (!pageVisible) return
      try {
        const res = await fetchTeamsToPlay()
        if (!active) return
        setTeamsToPlay(res)
        setTeamsToPlayError(null)
      } catch (e) {
        if (!active) return
        setTeamsToPlayError(String((e as Error)?.message ?? e))
      }
    }
    loadTeamsToPlay()
    const t = window.setInterval(loadTeamsToPlay, 60_000)
    return () => {
      active = false
      window.clearInterval(t)
    }
  }, [pageVisible])

  useEffect(() => {
    let active = true
    async function loadTrackRecord() {
      try {
        const res = await fetchTrackRecord(selectedChamp, trackDays)
        if (!active) return
        setTrackRecord(res)
        setTrackError(null)
      } catch (e) {
        if (!active) return
        setTrackError(String((e as Error)?.message ?? e))
        setTrackRecord(null)
      }
    }
    loadTrackRecord()
    return () => {
      active = false
    }
  }, [selectedChamp, trackDays])

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
  const tenantMinConfidence = String(tenantConfig?.filters?.min_confidence ?? "LOW").toUpperCase()
  const visibleToPlay = useMemo(() => {
    const minRank = confidenceRank(tenantMinConfidence)
    const base = toPlay.filter((m) => confidenceRank(confidenceLabel(Number(m.confidence ?? 0))) >= minRank)
    const filtered = base.filter((m) => matchAllowedByProfile(m, profile))
    if (profile === "BALANCED" && base.length && filtered.length === 0) return base
    return filtered
  }, [profile, tenantMinConfidence, toPlay])
  const watchlistMatches = useMemo(() => {
    if (!watchlist.length) return []
    const map = new Map<string, OverviewMatch>()
    for (const m of visibleToPlay) map.set(matchId(m), m)
    const list = watchlist.map((w) => {
      const liveMatch = map.get(w.id)
      return liveMatch ? liveMatch : toFallbackMatch(w)
    })
    const dayScore = (m: unknown) => {
      const k = kickoffUnix(m)
      if (!k) return 999
      const d = new Date(k * 1000)
      const now = new Date()
      const a = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
      const b = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
      const diffDays = Math.round((b - a) / (1000 * 60 * 60 * 24))
      if (diffDays < 0) return 998
      return diffDays
    }

    list.sort((a, b) => {
      const ap = isPinned(a) ? 1 : 0
      const bp = isPinned(b) ? 1 : 0
      if (ap !== bp) return bp - ap

      const al = isLiveMatch(a) ? 1 : 0
      const bl = isLiveMatch(b) ? 1 : 0
      if (al !== bl) return bl - al

      const ad = dayScore(a)
      const bd = dayScore(b)
      if (ad !== bd) return ad - bd

      const ak = Number(kickoffUnix(a) ?? 0)
      const bk = Number(kickoffUnix(b) ?? 0)
      return ak - bk
    })
    return list
  }, [isLiveMatch, isPinned, matchId, toFallbackMatch, watchlist, visibleToPlay])

  const clearHistorical = () => {
    const historicalIds = new Set(watchlistMatches.filter(isHistorical).map((m) => matchId(m)))
    if (historicalIds.size === 0) return

    const ok = window.confirm(`Vuoi rimuovere ${historicalIds.size} preferiti non più in calendario?`)
    if (!ok) return

    setWatchlist(watchlist.filter((w) => !historicalIds.has(w.id)))
    showUINotice(historicalIds.size === 1 ? "Pulito 1 storico ✅" : `Puliti ${historicalIds.size} storici ✅`)
  }

  const filteredWatchlistMatches = useMemo(() => {
    const q = String(deferredWatchSearch ?? "").trim().toLowerCase()
    if (!q) return watchlistMatches
    return watchlistMatches.filter((m) => `${m.home_team ?? ""} ${m.away_team ?? ""}`.toLowerCase().includes(q))
  }, [deferredWatchSearch, watchlistMatches])

  const passesDecisionFilters = useCallback((m: unknown) => {
    const q = qualityScore(m)
    if (hideNoBet && isNoBet(m)) return false
    if (onlyGood && !(q.grade === "A" || q.grade === "B")) return false
    return true
  }, [hideNoBet, isNoBet, onlyGood, qualityScore])

  const filteredBaseToPlay = useMemo(() => {
    return visibleToPlay.filter(passesDecisionFilters)
  }, [passesDecisionFilters, visibleToPlay])

  const filteredToPlay = useMemo(() => {
    const q = String(deferredMatchQuery ?? "").trim().toLowerCase()
    if (!q) return filteredBaseToPlay
    return filteredBaseToPlay.filter((m) => `${m.home_team} ${m.away_team}`.toLowerCase().includes(q))
  }, [deferredMatchQuery, filteredBaseToPlay])

  const nextMatches = useMemo(() => {
    const list = filteredToPlay.slice()
    list.sort((a, b) => {
      if (sortMode === "kickoff") return Number(a.kickoff_unix ?? 0) - Number(b.kickoff_unix ?? 0)
      if (sortMode === "confidence") return Number(b.confidence ?? 0) - Number(a.confidence ?? 0)
      return bestProb(b) - bestProb(a)
    })
    const filtered = list.filter(passesDecisionFilters)
    return filtered.slice(0, 12)
  }, [filteredToPlay, passesDecisionFilters, sortMode])

  const stats = useMemo(() => derivedStats(visibleToPlay), [visibleToPlay])
  const trend = useMemo(() => probabilityTrend(matchdays), [matchdays])
  const power = useMemo(() => expectedPointsTable(visibleToPlay).slice(0, 5), [visibleToPlay])

  const topFormTeams = useMemo(() => {
    const list = expectedPointsTable(visibleToPlay).slice(0, 5)
    return list.map((r) => ({ team: r.team, form: teamForm(finished, r.team) }))
  }, [finished, visibleToPlay])

  const title = (champ?.title ?? CHAMP_LABELS[selectedChamp] ?? "Dashboard").toUpperCase()
  const brandPrimaryColor = String(tenantConfig?.branding?.primary_color ?? "").trim()
  const activeColor = brandPrimaryColor || (CHAMP_COLORS[selectedChamp] ?? "#22c55e")
  const educationalOnly = Boolean(tenantConfig?.compliance?.educational_only)
  const disclaimerText = String(tenantConfig?.compliance?.disclaimer_text ?? "").trim()
  const brandName = String(tenantConfig?.branding?.app_name ?? "").trim() || "Forecast Master System"
  const brandTagline = String(tenantConfig?.branding?.tagline ?? "").trim()
  const brandLogoUrl = String(tenantConfig?.branding?.logo_url ?? "").trim()
  const disabledProfiles = (tenantConfig?.features?.disabled_profiles ?? []) as ProfileKey[]
  const matchesCount = filteredBaseToPlay.length
  const avgBest = matchesCount ? filteredBaseToPlay.reduce((acc, m) => acc + bestProb(m), 0) / matchesCount : 0
  const gaugeValue = avgBest
  const teamsToPlayItem = useMemo(() => {
    const items = teamsToPlay?.items ?? []
    const target = String(champ?.title ?? CHAMP_LABELS[selectedChamp] ?? "").trim().toLowerCase()
    if (!target) return null
    return items.find((i) => String(i.championship ?? "").trim().toLowerCase() === target) ?? null
  }, [champ?.title, selectedChamp, teamsToPlay?.items])

  const trackSeries = useMemo(() => {
    const pts = trackRecord?.points ?? []
    return pts.map((p) => {
      const dt = new Date(String(p.date_utc))
      const label = Number.isNaN(dt.getTime())
        ? String(p.date_utc)
        : dt.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" })
      return { date: label, accuracy: clamp01(Number(p.accuracy ?? 0)), roi_total: Number(p.roi_total ?? 0), n: Number(p.n ?? 0) }
    })
  }, [trackRecord?.points])

  async function toggleExplainTeam(team: string) {
    const key = String(team ?? "").trim()
    if (!key) return
    if (openTeamExplain === key) {
      setOpenTeamExplain("")
      setTeamExplain(null)
      setTeamExplainError(null)
      setTeamExplainLoading(false)
      return
    }
    setOpenTeamExplain(key)
    setTeamExplain(null)
    setTeamExplainError(null)
    setTeamExplainLoading(true)
    try {
      const res = await fetchExplainTeam(selectedChamp, key)
      setTeamExplain(res)
    } catch (e) {
      setTeamExplainError(String((e as Error)?.message ?? e))
    } finally {
      setTeamExplainLoading(false)
    }
  }

  async function loadMatchDetails(matchId: string) {
    const key = String(matchId ?? "").trim()
    if (!key) return
    openMatchExplainIdRef.current = key
    setOpenMatchExplainId(key)
    setMatchExplain(null)
    setMatchExplainError(null)
    setMatchExplainLoading(true)
    setMultiMarket(null)
    setMultiMarketError(null)
    setMultiMarketLoading(true)
    setSelectedMarketKey("")
    try {
      const [explainRes, marketsRes] = await Promise.allSettled([fetchExplainMatch(key), fetchMultiMarketConfidence(key)])
      if (openMatchExplainIdRef.current !== key) return
      if (explainRes.status === "fulfilled") {
        setMatchExplain(explainRes.value)
      } else {
        setMatchExplainError(String((explainRes.reason as Error)?.message ?? explainRes.reason))
      }
      if (marketsRes.status === "fulfilled") {
        setMultiMarket(marketsRes.value)
      } else {
        setMultiMarketError(String((marketsRes.reason as Error)?.message ?? marketsRes.reason))
      }
    } finally {
      if (openMatchExplainIdRef.current === key) {
        setMatchExplainLoading(false)
        setMultiMarketLoading(false)
      }
    }
  }

  async function toggleExplainMatch(matchId: string) {
    const key = String(matchId ?? "").trim()
    if (!key) return
    if (expandedMatchId === key) {
      setExpandedMatchId("")
      return
    }
    setExpandedMatchId(key)
    if (openMatchExplainId !== key) void loadMatchDetails(key)
  }

  const apiErrorLabel =
    error === "api_unreachable" || error === "api_disabled"
      ? "API non raggiungibile (backend offline)."
      : String(error ?? "")

  if (error && !overview) {
    const apiLabel = getApiBaseUrl() || "same-origin"
    return (
      <Card>
        <div className="text-sm font-semibold tracking-tight">Dashboard</div>
        <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-300">API: {apiLabel}</div>
        <div className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">{apiErrorLabel}</div>
        {systemStatus ? (
          <div className="mt-3 rounded-2xl border border-zinc-200/70 bg-white/55 p-3 text-xs text-zinc-700 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/25 dark:text-zinc-200">
            <div className="font-semibold">Stato API</div>
            <div className="mt-1">Provider: {systemStatus.data_provider}</div>
            <div className="mt-1">Errore: {String(systemStatus.data_error ?? "n/d")}</div>
            <div className="mt-1">FOOTBALL_DATA_KEY presente: {systemStatus.football_data_key_present ? "sì" : "no"}</div>
            <div className="mt-1">API_FOOTBALL_KEY presente: {systemStatus.api_football_key_present ? "sì" : "no"}</div>
            {String(systemStatus.data_error ?? "").includes("football_data_http_400") ? (
              <div className="mt-2 font-semibold">
                Token Football-Data non valido: aggiorna la chiave oppure usa un provider diverso (mock/api_football).
              </div>
            ) : String(systemStatus.data_error ?? "").includes("football_data_http_401") || String(systemStatus.data_error ?? "").includes("football_data_http_403") ? (
              <div className="mt-2 font-semibold">
                Accesso Football-Data non autorizzato: verifica la chiave e i permessi oppure usa un provider diverso (mock/api_football).
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="mt-4 rounded-2xl border border-zinc-200/70 bg-white/55 p-3 text-xs text-zinc-700 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/25 dark:text-zinc-200">
          Puoi impostare la base API anche senza rebuild aprendo il sito con <span className="font-mono">?api=https://TUO-TUNNEL</span>.
        </div>
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

      {error ? (
        <div className="mb-4 rounded-2xl border border-amber-200/50 bg-amber-50/60 px-4 py-3 text-xs text-amber-900 shadow-sm backdrop-blur-md dark:border-amber-900/35 dark:bg-amber-950/30 dark:text-amber-100">
          <div className="font-semibold">Dati non aggiornati</div>
          <div className="mt-1">{apiErrorLabel}</div>
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-4 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 backdrop-blur-md dark:bg-zinc-950/25">
        <div className="min-w-0 flex items-center gap-3">
          {brandLogoUrl ? (
            <img
              src={brandLogoUrl}
              alt={brandName}
              className="h-8 w-8 rounded-lg border border-white/10 bg-white/10 object-cover"
            />
          ) : null}
          <div className="min-w-0">
            <div className="text-xs font-semibold tracking-[0.18em] text-zinc-700 dark:text-zinc-200">
              {brandName.toUpperCase()}
            </div>
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
            {brandTagline ? `${brandTagline} · ` : ""}
            {title} · {selectedMd?.matchday_label ?? "Giornata"} · ROC-AUC {seasonAuc == null ? "n/d" : seasonAuc.toFixed(3)} · Track{" "}
            {trackRecord?.summary?.n
              ? `${fmtPct(Number(trackRecord.summary.accuracy ?? 0))} · ROI avg ${fmtSigned(Number(trackRecord.summary.roi_avg ?? 0))}`
              : "n/d"}
          </div>
          {disclaimerText ? (
            <div className="mt-2 text-[11px] text-zinc-600 dark:text-zinc-300">{disclaimerText}</div>
          ) : null}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {educationalOnly ? (
            <div className="rounded-full border border-violet-400/20 bg-violet-500/15 px-3 py-1 text-[11px] font-semibold text-violet-200">
              Educational only
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => setMobileControlsOpen((v) => !v)}
            className="md:hidden rounded-full border border-white/10 bg-white/10 px-3 py-2 text-xs font-semibold text-zinc-700 shadow-sm backdrop-blur-md transition hover:bg-white/15 dark:bg-zinc-950/20 dark:text-zinc-200"
            aria-expanded={mobileControlsOpen}
          >
            Impostazioni
          </button>

          <div className="hidden sm:flex items-center gap-2 rounded-xl border border-white/10 bg-white/10 px-3 py-2 shadow-sm backdrop-blur-md dark:bg-zinc-950/20">
            <label className="sr-only" htmlFor="match-search">
              Cerca match
            </label>
            <input
              id="match-search"
              value={matchQuery}
              onChange={(e) => setMatchQuery(e.target.value)}
              placeholder="Cerca team…"
              className="w-40 bg-transparent text-xs text-zinc-900 placeholder:text-zinc-500 outline-none dark:text-zinc-50 dark:placeholder:text-zinc-400"
            />
            <select
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value as "kickoff" | "prob" | "confidence")}
              className="rounded-lg border border-white/10 bg-white/10 px-2 py-1 text-[11px] text-zinc-700 shadow-sm backdrop-blur-md dark:bg-zinc-950/25 dark:text-zinc-200"
              aria-label="Ordina"
            >
              <option value="prob">Top prob.</option>
              <option value="confidence">Confidence</option>
              <option value="kickoff">Kickoff</option>
            </select>
          </div>
          <div className="hidden md:flex items-center gap-2 rounded-xl border border-white/10 bg-white/10 px-3 py-2 shadow-sm backdrop-blur-md dark:bg-zinc-950/20">
            <div className="text-[11px] font-semibold text-zinc-700 dark:text-zinc-200">Profilo</div>
            {(["PRUDENT", "BALANCED", "AGGRESSIVE"] as const).filter((p) => !disabledProfiles.includes(p)).map((p) => {
              const active = profile === p
              const label = p === "PRUDENT" ? "Prudente" : p === "AGGRESSIVE" ? "Aggressivo" : "Bilanciato"
              const tint =
                p === "PRUDENT"
                  ? "border-emerald-400/20 bg-emerald-500/15 text-emerald-200"
                  : p === "AGGRESSIVE"
                    ? "border-rose-400/20 bg-rose-500/15 text-rose-200"
                    : "border-amber-400/20 bg-amber-500/15 text-amber-200"
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => setProfile(p)}
                  title={profileTooltip(p)}
                  className={[
                    "rounded-full border px-2.5 py-1 text-[11px] font-semibold shadow-sm backdrop-blur-md transition",
                    active ? tint : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:text-zinc-200"
                  ].join(" ")}
                  aria-pressed={active}
                >
                  {label}
                </button>
              )
            })}
          </div>
          <div className="hidden md:flex items-center gap-2 rounded-xl border border-white/10 bg-white/10 px-3 py-2 shadow-sm backdrop-blur-md dark:bg-zinc-950/20">
            <div className="text-[11px] font-semibold text-zinc-700 dark:text-zinc-200">Bankroll</div>
            <input
              type="range"
              min={50}
              max={1000}
              step={10}
              value={bankroll}
              onChange={(e) => setBankroll(Number(e.target.value))}
              className="w-28 accent-emerald-500"
              aria-label="Bankroll"
            />
            <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">{bankroll}u</div>
          </div>
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

      {mobileControlsOpen ? (
        <div className="mt-3 grid grid-cols-1 gap-3 rounded-2xl border border-white/10 bg-white/10 p-4 backdrop-blur-md dark:bg-zinc-950/25 md:hidden">
          <div className="grid grid-cols-1 gap-2">
            <div className="text-[11px] font-semibold text-zinc-700 dark:text-zinc-200">Profilo</div>
            <div className="flex flex-wrap gap-2">
              {(["PRUDENT", "BALANCED", "AGGRESSIVE"] as const).filter((p) => !disabledProfiles.includes(p)).map((p) => {
                const active = profile === p
                const label = p === "PRUDENT" ? "Prudente" : p === "AGGRESSIVE" ? "Aggressivo" : "Bilanciato"
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setProfile(p)}
                    className={[
                      "rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm transition",
                      active
                        ? "border-white/20 bg-white/20 text-zinc-900 dark:bg-white/10 dark:text-zinc-50"
                        : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:text-zinc-200"
                    ].join(" ")}
                    aria-pressed={active}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-2">
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-semibold text-zinc-700 dark:text-zinc-200">Bankroll</div>
              <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">{bankroll}u</div>
            </div>
            <input
              type="range"
              min={50}
              max={1000}
              step={10}
              value={bankroll}
              onChange={(e) => setBankroll(Number(e.target.value))}
              className="w-full accent-emerald-500"
              aria-label="Bankroll"
            />
          </div>
        </div>
      ) : null}

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
          <div className="rounded-2xl border border-white/10 bg-white/10 p-4 shadow-sm backdrop-blur-md dark:bg-zinc-950/25">
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Preferiti ⭐</div>
                <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
                  Salva qui le partite che vuoi seguire più spesso.
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">
                  {watchlist.length}/20 · PIN {pinnedCount}/3
                </div>
                <button
                  type="button"
                  onClick={() => setWatchModalOpen(true)}
                  className="md:hidden rounded-full border border-white/10 bg-white/10 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
                >
                  Apri Preferiti
                </button>
                {watchlistMatches.some(isHistorical) ? (
                  <button
                    type="button"
                    onClick={clearHistorical}
                    className="rounded-full border border-white/10 bg-white/10 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
                    title="Rimuovi solo i preferiti non più in calendario"
                  >
                    Pulisci storici
                  </button>
                ) : null}
                {watchlist.length > 0 ? (
                  <button
                    type="button"
                    onClick={() => setWatchlist([])}
                    className="rounded-full border border-white/10 bg-white/10 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
                    title="Svuota preferiti"
                  >
                    Svuota
                  </button>
                ) : null}
              </div>
            </div>

            <div className="mt-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <label className="w-full md:max-w-sm">
                <span className="sr-only">Cerca nei preferiti</span>
                <input
                  value={watchSearch}
                  onChange={(e) => setWatchSearch(e.target.value)}
                  placeholder="Cerca nei preferiti (es. Inter, Milan...)"
                  className="w-full rounded-xl border border-white/10 bg-white/10 px-3 py-2 text-sm text-zinc-900 shadow-sm backdrop-blur-md placeholder:text-zinc-500 dark:bg-zinc-950/35 dark:text-zinc-50"
                />
              </label>

              {watchlist.length > 6 ? (
                <button
                  type="button"
                  onClick={() => setWatchShowAll((v) => !v)}
                  className="rounded-full border border-white/10 bg-white/10 px-4 py-2 text-sm font-semibold text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
                >
                  {watchShowAll ? "Mostra meno" : "Mostra tutti"}
                </button>
              ) : null}
            </div>

            {uiNotice ? (
              <div className="mt-2 rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-700 dark:text-amber-300">
                {uiNotice}
              </div>
            ) : null}

            <div className="mt-3">
              {filteredWatchlistMatches.length ? (
                <>
                  <div className="grid grid-cols-1 gap-2 md:hidden">
                    {(watchShowAll ? filteredWatchlistMatches : filteredWatchlistMatches.slice(0, 3)).map((m) => {
                      return (
                        <WatchlistItem
                          key={matchId(m)}
                          m={m}
                          matchKey={matchId(m)}
                          badges={badgeList(m)}
                          metaLine={`${m.league ?? m.competition ?? m.championship ?? "Match"}${formatKickoffTime(m) ? ` · ${formatKickoffTime(m)}` : ""}`}
                          pinned={isPinned(m)}
                          onTogglePin={() => onTogglePin(m)}
                          onRemove={() => onToggleWatch(m)}
                          showHistoricalBadge={Boolean(m?._from_watchlist_only)}
                        />
                      )
                    })}
                  </div>

                  <div className="hidden md:grid grid-cols-1 gap-2 md:grid-cols-2">
                    {(watchShowAll ? filteredWatchlistMatches : filteredWatchlistMatches.slice(0, 6)).map((m) => {
                      return (
                        <WatchlistItem
                          key={matchId(m)}
                          m={m}
                          matchKey={matchId(m)}
                          badges={badgeList(m)}
                          metaLine={`${m.league ?? m.competition ?? m.championship ?? "Match"}${formatKickoffTime(m) ? ` · ${formatKickoffTime(m)}` : ""}`}
                          pinned={isPinned(m)}
                          onTogglePin={() => onTogglePin(m)}
                          onRemove={() => onToggleWatch(m)}
                          showHistoricalBadge={Boolean(m?._from_watchlist_only)}
                        />
                      )
                    })}
                  </div>
                </>
              ) : watchlist.length ? (
                <div className="text-sm text-zinc-600 dark:text-zinc-300">
                  {watchSearch
                    ? "Nessun preferito corrisponde alla ricerca."
                    : "Nessun preferito disponibile."}
                </div>
              ) : (
                <div className="text-xs text-zinc-600 dark:text-zinc-300">
                  Nessun preferito: aggiungi una ⭐ dalle partite qui sotto.
                </div>
              )}
            </div>
          </div>

          {watchModalOpen ? (
            <div className="fixed inset-0 z-[60] md:hidden">
              <div className="absolute inset-0 bg-black/40" onClick={() => setWatchModalOpen(false)} aria-hidden="true" />
              <div className="absolute inset-x-0 bottom-0 max-h-[85vh] rounded-t-3xl border border-white/10 bg-white/90 p-4 shadow-2xl backdrop-blur-md dark:bg-zinc-950/90">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold tracking-tight">Preferiti ⭐</div>
                    <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Ricerca e gestisci tutti i preferiti</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setWatchModalOpen(false)}
                    className="rounded-full border border-white/10 bg-white/10 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
                  >
                    Chiudi
                  </button>
                </div>

                <div className="mt-3 flex items-center gap-2">
                  <input
                    value={watchSearch}
                    onChange={(e) => setWatchSearch(e.target.value)}
                    placeholder="Cerca nei preferiti…"
                    className="w-full rounded-xl border border-white/10 bg-white/10 px-3 py-2 text-sm text-zinc-900 shadow-sm backdrop-blur-md placeholder:text-zinc-500 dark:bg-zinc-950/35 dark:text-zinc-50"
                  />
                  <div className="shrink-0 flex items-center gap-2">
                    {watchlistMatches.some(isHistorical) ? (
                      <button
                        type="button"
                        onClick={clearHistorical}
                        className="shrink-0 rounded-full border border-white/10 bg-white/10 px-3 py-2 text-xs font-semibold text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
                        title="Rimuovi solo i preferiti non più in calendario"
                      >
                        Pulisci storici
                      </button>
                    ) : null}
                    {watchlist.length > 0 ? (
                      <button
                        type="button"
                        onClick={() => setWatchlist([])}
                        className="rounded-full border border-white/10 bg-white/10 px-3 py-2 text-xs font-semibold text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
                        title="Svuota preferiti"
                      >
                        Svuota
                      </button>
                    ) : null}
                  </div>
                </div>

                {uiNotice ? (
                  <div className="mt-2 rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-700 dark:text-amber-300">
                    {uiNotice}
                  </div>
                ) : null}

                <div className="mt-3 pb-6">
                  {filteredWatchlistMatches.length > 0 ? (
                    <VirtualList
                      items={filteredWatchlistMatches}
                      height={420}
                      itemSize={92}
                      renderRow={(m) => (
                        <div className="px-0 py-1">
                          <div
                            key={matchId(m)}
                            className="flex items-center justify-between rounded-xl border border-white/10 bg-white/10 px-3 py-2 dark:bg-zinc-950/20"
                          >
                            <div className="min-w-0">
                              <div className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                                {m.home_team} – {m.away_team}
                              </div>
                              <div className="mt-1 flex flex-wrap items-center gap-2">
                                {m._from_watchlist_only ? (
                                  <span className="rounded-full border border-zinc-500/20 bg-zinc-500/10 px-2 py-0.5 text-[10px] font-bold tracking-wide text-zinc-700 dark:text-zinc-300">
                                    NON IN CALENDARIO
                                  </span>
                                ) : null}
                                {badgeList(m).map((b) => (
                                  <span
                                    key={b.label}
                                    className={[
                                      "rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-wide",
                                      b.label === "NO BET"
                                        ? "border-zinc-500/20 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
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
                              <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
                                {`${m.league ?? m.competition ?? m.championship ?? "Match"}${
                                  formatKickoffTime(m) ? ` · ${formatKickoffTime(m)}` : ""
                                }`}
                              </div>
                            </div>

                            <div className="ml-3 flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => togglePin(m)}
                                className={[
                                  "rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm transition",
                                  isPinned(m)
                                    ? "border-amber-500/20 bg-amber-500/15 text-amber-700 dark:text-amber-300"
                                    : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
                                ].join(" ")}
                                title={isPinned(m) ? "Rimuovi PIN" : "Metti in PIN (max 3)"}
                                aria-pressed={isPinned(m)}
                              >
                                📌
                              </button>
                              <button
                                type="button"
                                onClick={() => toggleWatch(m)}
                                className="rounded-full border border-white/10 bg-white/10 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
                                aria-label="Rimuovi dai preferiti"
                                title="Rimuovi dai preferiti"
                              >
                                ★
                              </button>
                            </div>
                          </div>
                        </div>
                      )}
                    />
                  ) : (
                    <div className="text-sm text-zinc-600 dark:text-zinc-300">
                      {watchSearch ? "Nessun preferito corrisponde alla ricerca." : "Nessun preferito. Tocca ☆ su una partita per aggiungerla."}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : null}

          <Card className="!bg-white/10 dark:!bg-zinc-950/25">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Next Match Predictions</div>
                <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Filtra per squadra e ordina al volo</div>
              </div>
              <div className="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-[11px] text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
                Gare: {filteredToPlay.length}/{matchesCount} · Media: {fmtPct(avgBest)}
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
              <label className="md:col-span-2">
                <span className="sr-only">Cerca squadra</span>
                <input
                  value={matchQuery}
                  onChange={(e) => setMatchQuery(e.target.value)}
                  placeholder="Cerca squadra (es. Inter, Milan, Juventus…)"
                  className="w-full rounded-xl border border-white/10 bg-white/10 px-3 py-2 text-sm text-zinc-900 shadow-sm backdrop-blur-md placeholder:text-zinc-500 dark:bg-zinc-950/35 dark:text-zinc-50"
                />
              </label>
              <label>
                <span className="sr-only">Ordina</span>
                <select
                  value={sortMode}
                  onChange={(e) => setSortMode(e.target.value as "kickoff" | "prob" | "confidence")}
                  className="w-full rounded-xl border border-white/10 bg-white/10 px-3 py-2 text-sm text-zinc-900 shadow-sm backdrop-blur-md dark:bg-zinc-950/35 dark:text-zinc-50"
                >
                  <option value="prob">Ordina: Probabilità</option>
                  <option value="confidence">Ordina: Confidence</option>
                  <option value="kickoff">Ordina: Orario</option>
                </select>
              </label>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setOnlyGood((v) => !v)}
                className={[
                  "rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm transition",
                  onlyGood
                    ? "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                    : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200",
                ].join(" ")}
                aria-pressed={onlyGood}
              >
                Solo Qualità A/B
              </button>
              <button
                type="button"
                onClick={() => setHideNoBet((v) => !v)}
                className={[
                  "rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm transition",
                  hideNoBet
                    ? "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                    : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200",
                ].join(" ")}
                aria-pressed={hideNoBet}
              >
                {hideNoBet ? "Mostra NO BET" : "Nascondi NO BET"}
              </button>
              <button
                type="button"
                onClick={() => setPerformanceOpen(true)}
                className={[
                  "rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm transition",
                  performanceOpen
                    ? "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                    : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200",
                ].join(" ")}
                aria-pressed={performanceOpen}
              >
                Performance
              </button>
            </div>

            <div className="mt-4 space-y-3">
              {nextMatches.length ? (
                nextMatches.map((m) => {
                  const p1 = safeProb(m, "home_win")
                  const px = safeProb(m, "draw")
                  const p2 = safeProb(m, "away_win")
                  const mWithP = { ...m, p1, px, p2 }
                  const { best: bestPick } = topTwoPicks(mWithP)
                  const kickoffLabel = formatKickoff(m.kickoff_unix)
                  const open = expandedMatchId === m.match_id
                  const watched = isWatched(m)
                  const conf = confidenceLabel(Number(m.confidence ?? 0))
                  const risk = matchRisk(m)
                  const pct = educationalOnly ? 0 : stakePctForProfile(profile, conf, risk)
                  const units = educationalOnly ? 0 : stakeUnits(bankroll, pct)
                  const q = qualityScore(m)
                  const r = riskLabel(m)
                  const noBet = isNoBet(m)
                  const advice = adviceLine(mWithP)
                  const marketOk = !!multiMarket && String(multiMarket.match_id ?? "") === String(m.match_id ?? "")
                  const markets0 = marketOk ? (multiMarket?.markets ?? {}) : {}
                  const markets = marketOk ? filterMarketsByTenant(markets0, tenantConfig?.filters?.active_markets) : {}
                  const bestMk = marketOk ? bestMarketKey(markets) : ""
                  const selectedMk = (selectedMarketKey && markets[selectedMarketKey]) ? selectedMarketKey : bestMk
                  const selectedMarket = selectedMk ? markets[selectedMk] : undefined
                  const marketKeys = Object.keys(markets)
                  const tenantOrder0 = Array.isArray(tenantConfig?.filters?.active_markets) ? tenantConfig?.filters?.active_markets : []
                  const tenantOrder = tenantOrder0.map((x) => normalizeMarketKey(x)).filter(Boolean)
                  const orderedMarketKeys = tenantOrder.length
                    ? tenantOrder.filter((k) => marketKeys.includes(k))
                    : [
                        ...["1X2", "OVER_2_5", "BTTS"].filter((k) => marketKeys.includes(k)),
                        ...marketKeys.filter((k) => !["1X2", "OVER_2_5", "BTTS"].includes(k))
                      ]
                  return (
                    <NextMatchItem
                      key={m.match_id}
                      m={m}
                      matchKey={matchId(m)}
                      watched={watched}
                      onToggleWatch={() => onToggleWatch(m)}
                      titleRight={
                        <div className="shrink-0 flex flex-col items-end gap-2 text-right">
                          <div className="flex items-center justify-end gap-2">
                            {(() => {
                              const t = leagueTrend(String((m as { championship?: unknown } | null | undefined)?.championship ?? ""))
                              if (t.label === "n/d") return null
                              return (
                                <span
                                  className={[
                                    "rounded-full border px-2 py-0.5 text-[10px] font-bold",
                                    pillClass(t.tone === "green" ? "green" : t.tone === "red" ? "red" : "zinc")
                                  ].join(" ")}
                                  title={t.title}
                                >
                                  {t.label}
                                </span>
                              )
                            })()}
                            <span
                              className={[
                                "rounded-full border px-2 py-0.5 text-[10px] font-bold",
                                pillClass(q.grade === "A" ? "green" : q.grade === "B" ? "blue" : q.grade === "C" ? "yellow" : "red")
                              ].join(" ")}
                              title={[advice, bestPick ? `Pick: ${bestPick.label}` : ""].filter(Boolean).join(" ")}
                            >
                              {q.grade}
                            </span>
                          </div>
                          <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">
                            {Math.round(p1 * 100)}% / {Math.round(px * 100)}% / {Math.round(p2 * 100)}%
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="text-[11px] text-zinc-600 dark:text-zinc-300">
                              {educationalOnly ? "Educational only" : noBet ? "NO BET" : `Stake ${units}u (${pct.toFixed(2)}%)`}
                            </div>
                            {profile === "PRUDENT" || pct <= 2.0 ? (
                              <span className="rounded-full border border-emerald-400/20 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-200">
                                gestione prudente
                              </span>
                            ) : null}
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                setDetailMatch(mWithP)
                                setDetailOpen(true)
                              }}
                              className="rounded-full border border-white/10 bg-white/10 px-2.5 py-1 text-[11px] font-semibold text-zinc-700 shadow-sm backdrop-blur-md transition hover:bg-white/15 dark:text-zinc-200"
                            >
                              Dettagli
                            </button>
                            <button
                              type="button"
                              onClick={() => toggleExplainMatch(m.match_id)}
                              className={[
                                "rounded-full border px-2.5 py-1 text-[11px] font-semibold shadow-sm backdrop-blur-md transition",
                                open
                                  ? "border-white/20 bg-white/20 text-zinc-900 dark:bg-white/10 dark:text-zinc-50"
                                  : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:text-zinc-200"
                              ].join(" ")}
                            >
                              Perché?
                            </button>
                          </div>
                        </div>
                      }
                    >
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span
                          className={[
                            "rounded-full border px-2 py-0.5 text-[10px] font-bold",
                            pillClass(q.grade === "A" ? "green" : q.grade === "B" ? "blue" : q.grade === "C" ? "yellow" : "red")
                          ].join(" ")}
                        >
                          Qualità {q.grade}
                        </span>
                        <span
                          className={[
                            "rounded-full border px-2 py-0.5 text-[10px] font-bold",
                            pillClass(r.tone === "green" ? "green" : r.tone === "yellow" ? "yellow" : "red")
                          ].join(" ")}
                        >
                          Rischio {r.label}
                        </span>
                        {(() => {
                          const t = leagueTrend(String((m as { championship?: unknown } | null | undefined)?.championship ?? ""))
                          if (t.label === "n/d") return null
                          return (
                            <span
                              className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(
                                t.tone === "green" ? "green" : t.tone === "red" ? "red" : "zinc"
                              )}`}
                              title={t.title}
                            >
                              {t.label}
                            </span>
                          )
                        })()}
                        {(() => {
                          const rel = leagueReliability(String((m as { championship?: unknown } | null | undefined)?.championship ?? ""))
                          if (rel.label === "n/d") return null
                          return (
                            <span
                              className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(
                                rel.tone === "green" ? "green" : rel.tone === "yellow" ? "yellow" : "red"
                              )}`}
                            >
                              {rel.label}
                            </span>
                          )
                        })()}
                        {noBet ? (
                          <span className={["rounded-full border px-2 py-0.5 text-[10px] font-bold", pillClass("zinc")].join(" ")}>
                            NO BET
                          </span>
                        ) : null}
                      </div>
                      <div className="mt-2 rounded-xl border border-white/10 bg-white/10 px-3 py-2 text-sm text-zinc-900 dark:bg-zinc-950/20 dark:text-zinc-50">
                        {advice}
                      </div>
                      {(() => {
                        const { best, alt } = topTwoPicks(mWithP)
                        if (!best) return null
                        if (isNoBet(m)) return null

                        const bestPct = fmtPct(Number(best.prob))
                        const altPct = alt ? fmtPct(Number(alt.prob)) : null

                        return (
                          <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-3">
                              <div className="text-xs font-bold text-emerald-700 dark:text-emerald-300">Migliore</div>
                              <div className="mt-1 text-sm font-semibold text-zinc-900 dark:text-zinc-50">{best.label}</div>
                              <div className="mt-1 text-xs text-zinc-700 dark:text-zinc-200">
                                Probabilità: <span className="font-bold">{bestPct}</span>
                              </div>
                            </div>

                            {alt ? (
                              <div className="rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
                                <div className="text-xs font-bold text-zinc-700 dark:text-zinc-200">Alternativa</div>
                                <div className="mt-1 text-sm font-semibold text-zinc-900 dark:text-zinc-50">{alt.label}</div>
                                <div className="mt-1 text-xs text-zinc-700 dark:text-zinc-200">
                                  Probabilità: <span className="font-bold">{altPct}</span>
                                </div>
                              </div>
                            ) : (
                              <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-sm text-zinc-600 dark:bg-zinc-950/20 dark:text-zinc-300">
                                Nessuna alternativa disponibile.
                              </div>
                            )}
                          </div>
                        )
                      })()}
                      <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
                        {kickoffLabel ? <span>{kickoffLabel} · </span> : null}
                        Conf {fmtPct(bestProb(m))} · {m.status}
                      </div>
                      {(() => {
                        const r = riskLabel(m)
                        const nobet = isNoBet(m)
                        if (!nobet && r.tone !== "red") return null
                        return (
                          <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-300">
                            <span className="font-semibold">Perché:</span>{" "}
                            {nobet ? noBetReason(m) : "Rischio alto: segnali non allineati"}
                          </div>
                        )
                      })()}
                      {!noBet ? (
                        <>
                          <div className="mt-3 overflow-hidden rounded-xl border border-white/10 bg-zinc-950/30">
                            <div className="flex h-7 w-full text-[11px] font-semibold text-white">
                              <div className="grid place-items-center bg-blue-500/70" style={{ width: `${Math.round(p1 * 100)}%` }}>1</div>
                              <div className="grid place-items-center bg-violet-500/70" style={{ width: `${Math.round(px * 100)}%` }}>X</div>
                              <div className="grid place-items-center bg-rose-500/70" style={{ width: `${Math.round(p2 * 100)}%` }}>2</div>
                            </div>
                          </div>
                          {open ? (
                            <div className="mt-3 rounded-xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
                              <div className="space-y-3">
                                <div className="space-y-2">
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="font-semibold text-zinc-900 dark:text-zinc-50">Mercati</div>
                                    {bestMk && markets[bestMk] ? (
                                      <div className="text-[11px] text-zinc-600 dark:text-zinc-300">
                                        Migliore: {marketDisplayName(bestMk)} · Conf {Number(markets[bestMk].confidence ?? 0)}% · Risk {String(markets[bestMk].risk ?? "")}
                                      </div>
                                    ) : null}
                                  </div>

                                  {multiMarketLoading ? (
                                    <div>Caricamento…</div>
                                  ) : multiMarketError && !marketOk ? (
                                    <div>{multiMarketError}</div>
                                  ) : !marketOk ? (
                                    <div>n/d</div>
                                  ) : (
                                    <div className="space-y-2">
                                      <div className="flex flex-wrap gap-2">
                                        {orderedMarketKeys.map((k) => {
                                          const mk = markets[k]
                                          const active = selectedMk === k
                                          const best = bestMk === k
                                          const unstable = mk ? isUnstableMarket(mk) : false
                                          return (
                                            <button
                                              key={`mk-${m.match_id}-${k}`}
                                              type="button"
                                              onClick={() => setSelectedMarketKey(k)}
                                              className={[
                                                "flex items-center gap-2 rounded-full border px-2.5 py-1 text-[11px] font-semibold shadow-sm backdrop-blur-md transition",
                                                active
                                                  ? "border-white/20 bg-white/20 text-zinc-900 dark:bg-white/10 dark:text-zinc-50"
                                                  : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:text-zinc-200"
                                              ].join(" ")}
                                            >
                                              <span>{marketDisplayName(k)}</span>
                                              {mk ? (
                                                <span className="text-[10px] text-zinc-600 dark:text-zinc-300">
                                                  {Number(mk.confidence ?? 0)}% · {String(mk.risk ?? "")}
                                                </span>
                                              ) : null}
                                              {best ? (
                                                <span className="rounded-full border border-emerald-400/20 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-200">
                                                  migliore
                                                </span>
                                              ) : null}
                                              {unstable ? (
                                                <span className="rounded-full border border-amber-400/20 bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-200">
                                                  instabile
                                                </span>
                                              ) : null}
                                            </button>
                                          )
                                        })}
                                      </div>

                                      {selectedMarket ? (
                                        <div className="rounded-xl border border-white/10 bg-white/10 p-3 text-[11px] text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
                                          <div className="flex items-center justify-between gap-2">
                                            <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">{marketDisplayName(selectedMk)}</div>
                                            <div className="text-[11px] text-zinc-600 dark:text-zinc-300">
                                              Prob {fmtPct(Number(selectedMarket.probability ?? 0))} · Conf {Number(selectedMarket.confidence ?? 0)}% · Risk {String(selectedMarket.risk ?? "")}
                                            </div>
                                          </div>
                                          {isUnstableMarket(selectedMarket) ? (
                                            <div className="mt-2 rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
                                              Warning: mercato instabile (confidence bassa o rischio HIGH)
                                            </div>
                                          ) : null}
                                        </div>
                                      ) : null}
                                    </div>
                                  )}
                                </div>

                                <div>
                                  {matchExplainLoading ? (
                                    <div>Caricamento…</div>
                                  ) : matchExplainError ? (
                                    <div>{matchExplainError}</div>
                                  ) : !matchExplain ? (
                                    <div>n/d</div>
                                  ) : (
                                    <div className="space-y-2">
                                      <div className="font-semibold text-zinc-900 dark:text-zinc-50">
                                        {matchExplain.team ? `Perché ${matchExplain.team}` : "Perché"}
                                        {matchExplain.pick ? <span className="ml-2 text-[11px] font-semibold text-zinc-600 dark:text-zinc-300">{matchExplain.pick}</span> : null}
                                      </div>
                                      <div className="space-y-1">
                                        {(matchExplain.why ?? []).map((t, i) => (
                                          <div key={`why-${i}`}>• {t}</div>
                                        ))}
                                      </div>
                                      {(matchExplain.risks ?? []).length ? (
                                        <div className="space-y-1">
                                          <div className="text-[11px] font-semibold text-zinc-600 dark:text-zinc-300">Rischi</div>
                                          {(matchExplain.risks ?? []).map((t, i) => (
                                            <div key={`risk-${i}`}>• {t}</div>
                                          ))}
                                        </div>
                                      ) : null}
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          ) : null}
                        </>
                      ) : (
                        <div className="mt-3 text-xs text-zinc-600 dark:text-zinc-300">
                          Match mostrato solo per completezza: segnali deboli (NO BET).
                        </div>
                      )}
                    </NextMatchItem>
                  )
                })
              ) : (
                <div className="rounded-2xl border border-white/10 bg-white/10 p-4 text-sm text-zinc-700 backdrop-blur-md dark:bg-zinc-950/25 dark:text-zinc-200">
                  <div className="font-semibold text-zinc-900 dark:text-zinc-50">Nessuna gara visibile.</div>
                  <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
                    {visibleToPlay.length
                      ? "I filtri attivi stanno escludendo tutte le partite. Disattiva “Solo Qualità A/B”, “Nascondi NO BET” o svuota la ricerca."
                      : "Nessuna partita disponibile per il profilo/tenant selezionato."}
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setOnlyGood(false)
                        setHideNoBet(false)
                        setMatchQuery("")
                      }}
                      className="rounded-full border border-white/10 bg-white/10 px-3 py-1.5 text-xs font-semibold text-zinc-700 shadow-sm transition hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
                    >
                      Reset filtri
                    </button>
                    {hideNoBet ? (
                      <button
                        type="button"
                        onClick={() => setHideNoBet(false)}
                        className="rounded-full border border-emerald-500/20 bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-700 shadow-sm transition dark:text-emerald-300"
                      >
                        Mostra NO BET
                      </button>
                    ) : null}
                  </div>
                </div>
              )}
            </div>
          </Card>

          <LeaguePerformanceTable defaultOpen />

          <Card className="!bg-white/10 dark:!bg-zinc-950/25">
            <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Win Probability Chart</div>
            <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Trend medio 1 / X / 2 per giornata</div>
            <WinProbabilityChart trend={trend} fmtPct={fmtPct} />
          </Card>
        </div>

        <div className="lg:col-span-3 space-y-4">
          <Card className="!bg-white/10 !p-4 dark:!bg-zinc-950/25">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Squadre da giocare</div>
                <div className="mt-1 flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-300">
                  <span
                    className="inline-flex items-center gap-1"
                    title="success_score = 65% forza squadra (Elo) + 35% forma recente (ultimi 8 match FINISHED)"
                  >
                    Top 3 per % successo <span className="text-[11px] text-zinc-500 dark:text-zinc-400">ⓘ</span>
                  </span>
                </div>
              </div>
              <div className="shrink-0 text-right text-[11px] text-zinc-600 dark:text-zinc-300">
                {teamsToPlay?.generated_at_utc ? new Date(String(teamsToPlay.generated_at_utc)).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }) : ""}
              </div>
            </div>

            <div className="mt-4 space-y-2">
              {teamsToPlayItem?.top3?.length ? (
                [...teamsToPlayItem.top3]
                  .slice()
                  .sort((a: TeamToPlay, b: TeamToPlay) => Number(b.success_pct ?? 0) - Number(a.success_pct ?? 0))
                  .map((t: TeamToPlay, idx: number) => {
                    const teamKey = String(t.team ?? "").trim()
                    const open = openTeamExplain === teamKey
                    const explainOk = !!teamExplain && String(teamExplain.team ?? "").trim() === teamKey
                    return (
                    <div
                      key={`${teamKey}-${idx}`}
                      className="rounded-2xl border border-white/10 bg-white/10 px-3 py-3 backdrop-blur-md dark:bg-zinc-950/20"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <div className="truncate text-xs font-semibold text-zinc-900 dark:text-zinc-50">{teamKey}</div>
                            {idx === 0 ? (
                              <span className="shrink-0 rounded-full border border-emerald-400/20 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-200">
                                Top pick
                              </span>
                            ) : null}
                          </div>
                          <div className="mt-1 text-[11px] text-zinc-600 dark:text-zinc-300">
                            Forza {fmtPct100(t.strength_pct)} · Forma {fmtPct100(t.form_pct)}
                          </div>
                        </div>
                        <div className="shrink-0 flex flex-col items-end gap-2">
                          <div className="rounded-full border border-white/10 bg-white/10 px-2.5 py-1 text-xs font-semibold text-zinc-900 dark:bg-zinc-950/15 dark:text-zinc-50">
                            {fmtPct100(t.success_pct)}
                          </div>
                          <button
                            type="button"
                            onClick={() => toggleExplainTeam(teamKey)}
                            className={[
                              "rounded-full border px-2.5 py-1 text-[11px] font-semibold shadow-sm backdrop-blur-md transition",
                              open
                                ? "border-white/20 bg-white/20 text-zinc-900 dark:bg-white/10 dark:text-zinc-50"
                                : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:text-zinc-200"
                            ].join(" ")}
                          >
                            Perché?
                          </button>
                        </div>
                      </div>
                      {open ? (
                        <div className="mt-3 rounded-xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
                          {teamExplainLoading ? (
                            <div>Caricamento…</div>
                          ) : teamExplainError ? (
                            <div>{teamExplainError}</div>
                          ) : !explainOk ? (
                            <div>n/d</div>
                          ) : (
                            <div className="space-y-2">
                              <div className="font-semibold text-zinc-900 dark:text-zinc-50">
                                {teamExplain.team ? `Perché ${teamExplain.team}` : "Perché"}
                              </div>
                              <div className="space-y-1">
                                {(teamExplain.why ?? []).map((x, i) => (
                                  <div key={`t-why-${i}`}>• {x}</div>
                                ))}
                              </div>
                              {(teamExplain.risks ?? []).length ? (
                                <div className="space-y-1">
                                  <div className="text-[11px] font-semibold text-zinc-600 dark:text-zinc-300">Rischi</div>
                                  {(teamExplain.risks ?? []).map((x, i) => (
                                    <div key={`t-risk-${i}`}>• {x}</div>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                          )}
                        </div>
                      ) : null}
                    </div>
                    )
                  })
              ) : teamsToPlayError ? (
                <div className="text-xs text-zinc-600 dark:text-zinc-300">{teamsToPlayError}</div>
              ) : (
                <div className="text-xs text-zinc-600 dark:text-zinc-300">n/d</div>
              )}
            </div>
          </Card>

          <Card className="!bg-white/10 !p-4 dark:!bg-zinc-950/25">
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
      </div>

      <div className="mt-4">
        <Card className="!bg-white/10 dark:!bg-zinc-950/25">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Track Record</div>
              <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Accuracy e ROI simulato nel tempo</div>
            </div>
            <div className="flex items-center gap-2">
              <select
                value={String(trackDays)}
                onChange={(e) => setTrackDays(Number(e.target.value))}
                className="rounded-xl border border-white/10 bg-white/10 px-3 py-2 text-xs text-zinc-900 shadow-sm backdrop-blur-md dark:bg-zinc-950/35 dark:text-zinc-50"
                aria-label="Finestra storico"
              >
                <option value="30">30g</option>
                <option value="90">90g</option>
                <option value="120">120g</option>
                <option value="180">180g</option>
                <option value="365">365g</option>
              </select>
              <div className="rounded-full border border-white/10 bg-white/10 px-3 py-2 text-[11px] text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
                {trackRecord?.summary?.n ? (
                  <span>
                    N {trackRecord.summary.n} · Acc {fmtPct(Number(trackRecord.summary.accuracy ?? 0))} · ROI tot {fmtSigned(Number(trackRecord.summary.roi_total ?? 0))}
                  </span>
                ) : trackError ? (
                  <span>{trackError}</span>
                ) : (
                  <span>n/d</span>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
              <div className="text-[10px] uppercase tracking-wide text-zinc-600 dark:text-zinc-300">High confidence</div>
              <div className="mt-1 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                {trackRecord?.summary?.by_confidence?.high?.n
                  ? `${fmtPct(Number(trackRecord.summary.by_confidence.high.accuracy ?? 0))} · ROI ${fmtSigned(Number(trackRecord.summary.by_confidence.high.roi_avg ?? 0))}`
                  : "n/d"}
              </div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
              <div className="text-[10px] uppercase tracking-wide text-zinc-600 dark:text-zinc-300">Medium confidence</div>
              <div className="mt-1 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                {trackRecord?.summary?.by_confidence?.medium?.n
                  ? `${fmtPct(Number(trackRecord.summary.by_confidence.medium.accuracy ?? 0))} · ROI ${fmtSigned(Number(trackRecord.summary.by_confidence.medium.roi_avg ?? 0))}`
                  : "n/d"}
              </div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
              <div className="text-[10px] uppercase tracking-wide text-zinc-600 dark:text-zinc-300">Low confidence</div>
              <div className="mt-1 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                {trackRecord?.summary?.by_confidence?.low?.n
                  ? `${fmtPct(Number(trackRecord.summary.by_confidence.low.accuracy ?? 0))} · ROI ${fmtSigned(Number(trackRecord.summary.by_confidence.low.roi_avg ?? 0))}`
                  : "n/d"}
              </div>
            </div>
          </div>

          <TrackRecordChart trackSeries={trackSeries} fmtPct={fmtPct} fmtSigned={fmtSigned} trackError={trackError ?? undefined} />
        </Card>

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

      <Modal
        open={performanceOpen}
        title="Performance per campionato"
        onClose={() => setPerformanceOpen(false)}
      >
        <LeaguePerformanceTable defaultOpen={true} />
      </Modal>

      <Modal
        open={detailOpen}
        title={
          detailMatch
            ? `${detailMatch.home_team ?? ""} – ${detailMatch.away_team ?? ""}`
            : "Dettagli"
        }
        onClose={() => {
          setDetailOpen(false)
          setDetailMatch(null)
        }}
      >
        {detailMatch ? (
          <div className="space-y-3">
            <div className="rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
              <div className="text-xs font-bold text-zinc-700 dark:text-zinc-200">Consiglio</div>
              <div className="mt-1 text-sm text-zinc-900 dark:text-zinc-50">
                {adviceLine(detailMatch)}
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
              <div className="text-xs font-bold text-zinc-700 dark:text-zinc-200">Indicatori</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {(() => {
                  const q = qualityScore(detailMatch)
                  const r = riskLabel(detailMatch)
                  return (
                    <>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(
                          q.grade === "A" ? "green" : q.grade === "B" ? "blue" : q.grade === "C" ? "yellow" : "red"
                        )}`}
                      >
                        Qualità {q.grade}
                      </span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(
                          r.tone === "green" ? "green" : r.tone === "yellow" ? "yellow" : "red"
                        )}`}
                      >
                        Rischio {r.label}
                      </span>
                      {isNoBet(detailMatch) ? (
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("zinc")}`}
                        >
                          NO BET
                        </span>
                      ) : null}
                    </>
                  )
                })()}
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
              Dettagli avanzati: qui puoi mostrare eventuali spiegazioni estese, feature, o dati modello (se disponibili).
            </div>
          </div>
        ) : (
          <div className="text-sm text-zinc-600 dark:text-zinc-300">n/d</div>
        )}
      </Modal>
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
