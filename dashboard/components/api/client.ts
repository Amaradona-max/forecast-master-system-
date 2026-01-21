import type {
  ExplainResponse,
  MatchUpdate,
  MultiMarketConfidenceResponse,
  SeasonAccuracyResponse,
  SystemStatusResponse,
  TenantConfig,
  TeamsToPlayResponse,
  TrackRecordResponse,
  UserProfile,
  UserProfileUpdate
} from "@/components/api/types"

let apiDisabledUntil = 0
let apiBackoffMs = 0
let apiLastBaseUrl = ""

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
  if (typeof window !== "undefined") {
    const host = window.location.hostname
    if (host === "localhost" || host === "127.0.0.1") return "http://localhost:8000"
  }
  if (process.env.NODE_ENV === "development") return "http://localhost:8000"
  return ""
}

export function apiUrl(path: string) {
  const p = path.startsWith("/") ? path : `/${path}`
  return `${getApiBaseUrl()}${p}`
}

function syncApiBaseUrl() {
  const base = getApiBaseUrl()
  if (base !== apiLastBaseUrl) {
    apiLastBaseUrl = base
    apiDisabledUntil = 0
    apiBackoffMs = 0
  }
  return base
}

export function isApiTemporarilyDisabled() {
  syncApiBaseUrl()
  return Date.now() < apiDisabledUntil
}

export async function apiFetch(path: string, init?: RequestInit) {
  syncApiBaseUrl()
  if (Date.now() < apiDisabledUntil) throw new Error("api_disabled")
  try {
    const res = await fetch(apiUrl(path), init)
    apiBackoffMs = 0
    return res
  } catch (e) {
    const name = String((e as { name?: unknown })?.name ?? "")
    if (name !== "AbortError") {
      const base = syncApiBaseUrl()
      if (base) {
        apiBackoffMs = Math.min(apiBackoffMs ? apiBackoffMs * 2 : 30_000, 5 * 60_000)
        apiDisabledUntil = Date.now() + apiBackoffMs
      }
    }
    throw new Error("api_unreachable")
  }
}

function readRuntimeTenantId(): string | null {
  if (typeof window === "undefined") return null
  try {
    const url = new URL(window.location.href)
    const qp = url.searchParams.get("tenant") ?? url.searchParams.get("tenant_id")
    if (qp) {
      const v = qp.trim().toLowerCase()
      if (/^[a-z0-9][a-z0-9_-]{0,63}$/i.test(v)) {
        window.localStorage.setItem("tenant_id", v)
        return v
      }
    }
  } catch {}

  try {
    const v = window.localStorage.getItem("tenant_id")
    if (v && /^[a-z0-9][a-z0-9_-]{0,63}$/i.test(v.trim())) return v.trim().toLowerCase()
  } catch {}

  return null
}

export function getTenantId() {
  const runtime = readRuntimeTenantId()
  if (runtime) return runtime
  const env = String(process.env.NEXT_PUBLIC_TENANT_ID ?? "").trim().toLowerCase()
  if (env && /^[a-z0-9][a-z0-9_-]{0,63}$/i.test(env)) return env
  return "default"
}

function withTenantHeaders(headers?: HeadersInit) {
  const h = new Headers(headers ?? {})
  h.set("x-tenant-id", getTenantId())
  return h
}

export async function apiFetchTenant(path: string, init?: RequestInit) {
  return apiFetch(path, { ...(init ?? {}), headers: withTenantHeaders(init?.headers) })
}

export async function fetchSeasonProgress(championship: string = "all"): Promise<SeasonAccuracyResponse> {
  const res = await apiFetchTenant(`/api/v1/accuracy/season-progress?championship=${encodeURIComponent(championship)}`, {
    cache: "no-store",
  })
  if (!res.ok) throw new Error(`season_progress_failed:${res.status}`)
  return res.json()
}

export async function fetchLiveProbabilities(matchId: string): Promise<MatchUpdate> {
  const res = await apiFetchTenant(`/api/v1/live/${encodeURIComponent(matchId)}/probabilities`, { cache: "no-store" })
  if (!res.ok) throw new Error(`live_probabilities_failed:${res.status}`)
  return res.json()
}

export async function fetchTeamsToPlay(): Promise<TeamsToPlayResponse> {
  const res = await apiFetchTenant("/api/v1/insights/teams-to-play", { cache: "no-store" })
  if (!res.ok) throw new Error(`teams_to_play_failed:${res.status}`)
  return res.json()
}

export async function fetchTrackRecord(championship: string = "all", days: number = 120): Promise<TrackRecordResponse> {
  const res = await apiFetchTenant(
    `/api/v1/history/track-record?championship=${encodeURIComponent(championship)}&days=${encodeURIComponent(String(days))}`,
    { cache: "no-store" }
  )
  if (!res.ok) throw new Error(`track_record_failed:${res.status}`)
  return res.json()
}

export async function fetchExplainTeam(championship: string, team: string): Promise<ExplainResponse> {
  const res = await apiFetchTenant(
    `/api/v1/explain/team?championship=${encodeURIComponent(championship)}&team=${encodeURIComponent(team)}`,
    { cache: "no-store" }
  )
  if (!res.ok) throw new Error(`explain_team_failed:${res.status}`)
  return res.json()
}

export async function fetchExplainMatch(matchId: string): Promise<ExplainResponse> {
  const res = await apiFetchTenant(`/api/v1/explain/match?match_id=${encodeURIComponent(matchId)}`, { cache: "no-store" })
  if (!res.ok) throw new Error(`explain_match_failed:${res.status}`)
  return res.json()
}

export async function fetchMultiMarketConfidence(matchId: string): Promise<MultiMarketConfidenceResponse> {
  const res = await apiFetchTenant(`/api/v1/insights/multi-market?match_id=${encodeURIComponent(matchId)}`, { cache: "no-store" })
  if (!res.ok) throw new Error(`multi_market_failed:${res.status}`)
  return res.json()
}

export async function fetchUserProfile(): Promise<UserProfile> {
  const res = await apiFetchTenant("/api/v1/user/profile", { cache: "no-store" })
  if (!res.ok) throw new Error(`user_profile_failed:${res.status}`)
  return res.json()
}

export async function updateUserProfile(update: UserProfileUpdate): Promise<UserProfile> {
  const res = await apiFetchTenant("/api/v1/user/profile", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(update ?? {})
  })
  if (!res.ok) throw new Error(`user_profile_update_failed:${res.status}`)
  return res.json()
}

export async function fetchTenantConfig(): Promise<TenantConfig> {
  const res = await apiFetchTenant("/api/v1/tenant/config", { cache: "no-store" })
  if (!res.ok) throw new Error(`tenant_config_failed:${res.status}`)
  return res.json()
}

export async function fetchSystemStatus(): Promise<SystemStatusResponse> {
  const res = await apiFetchTenant("/api/v1/system/status", { cache: "no-store" })
  if (!res.ok) throw new Error(`system_status_failed:${res.status}`)
  return res.json()
}
