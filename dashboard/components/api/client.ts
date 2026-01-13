import type { MatchUpdate, SeasonAccuracyResponse } from "@/components/api/types"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

export function apiUrl(path: string) {
  return `${API_BASE_URL}${path}`
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

