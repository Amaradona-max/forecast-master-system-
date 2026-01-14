import type { MatchUpdate, SeasonAccuracyResponse } from "@/components/api/types"

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
