import type { ExplainResponse, MatchUpdate, SeasonAccuracyResponse, TeamsToPlayResponse, TrackRecordResponse } from "@/components/api/types"

function normalizeApiBaseUrl(raw: string | undefined | null) {
  const base = String(raw ?? "").trim()
  if (!base) return ""
  return base.endsWith("/") ? base.slice(0, -1) : base
}

function readRuntimeApiBaseUrl(): string | null {
  if (typeof window === "undefined") return null
  try {
    const url = new URL(window.location.href)
    const qp = url.searchParams.get("api") ?? url.searchParams.get("api_base_url")
    if (qp) {
      const v = qp.trim()
      if (/^https?:\/\//i.test(v)) {
        window.localStorage.setItem("api_base_url", v)
        return v
      }
    }
  } catch {}

  try {
    const v = window.localStorage.getItem("api_base_url")
    if (v && /^https?:\/\//i.test(v.trim())) return v.trim()
  } catch {}

  return null
}

export function getApiBaseUrl() {
  const runtime = readRuntimeApiBaseUrl()
  if (runtime) return normalizeApiBaseUrl(runtime)
  const env = process.env.NEXT_PUBLIC_API_BASE_URL
  const normalizedEnv = normalizeApiBaseUrl(env)
  if (normalizedEnv) return normalizedEnv
  return process.env.NODE_ENV === "production" ? "" : "http://localhost:8000"
}

export function apiUrl(path: string) {
  const p = path.startsWith("/") ? path : `/${path}`
  return `${getApiBaseUrl()}${p}`
}

export async function fetchSeasonProgress(championship: string = "all"): Promise<SeasonAccuracyResponse> {
  const res = await fetch(apiUrl(`/api/v1/accuracy/season-progress?championship=${encodeURIComponent(championship)}`), {
    cache: "no-store"
  })
  if (!res.ok) throw new Error(`season_progress_failed:${res.status}`)
  return res.json()
}

export async function fetchLiveProbabilities(matchId: string): Promise<MatchUpdate> {
  const res = await fetch(apiUrl(`/api/v1/live/${encodeURIComponent(matchId)}/probabilities`), { cache: "no-store" })
  if (!res.ok) throw new Error(`live_probabilities_failed:${res.status}`)
  return res.json()
}

export async function fetchTeamsToPlay(): Promise<TeamsToPlayResponse> {
  const res = await fetch(apiUrl("/api/v1/insights/teams-to-play"), { cache: "no-store" })
  if (!res.ok) throw new Error(`teams_to_play_failed:${res.status}`)
  return res.json()
}

export async function fetchTrackRecord(championship: string = "all", days: number = 120): Promise<TrackRecordResponse> {
  const res = await fetch(
    apiUrl(`/api/v1/history/track-record?championship=${encodeURIComponent(championship)}&days=${encodeURIComponent(String(days))}`),
    { cache: "no-store" }
  )
  if (!res.ok) throw new Error(`track_record_failed:${res.status}`)
  return res.json()
}

export async function fetchExplainTeam(championship: string, team: string): Promise<ExplainResponse> {
  const res = await fetch(
    apiUrl(`/api/v1/explain/team?championship=${encodeURIComponent(championship)}&team=${encodeURIComponent(team)}`),
    { cache: "no-store" }
  )
  if (!res.ok) throw new Error(`explain_team_failed:${res.status}`)
  return res.json()
}

export async function fetchExplainMatch(matchId: string): Promise<ExplainResponse> {
  const res = await fetch(apiUrl(`/api/v1/explain/match?match_id=${encodeURIComponent(matchId)}`), { cache: "no-store" })
  if (!res.ok) throw new Error(`explain_match_failed:${res.status}`)
  return res.json()
}
