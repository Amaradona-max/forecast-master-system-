export type Championship = "serie_a" | "premier_league" | "la_liga" | "bundesliga" | "eliteserien"

export type MatchProbabilities = {
  home_win: number
  draw: number
  away_win: number
}

export type MatchUpdate = {
  match_id: string
  championship: Championship
  home_team: string
  away_team: string
  status: string
  kickoff_unix?: number | null
  updated_at_unix: number
  probabilities: MatchProbabilities
  meta?: Record<string, unknown>
}

export type SeasonAccuracyPoint = {
  date_utc: string
  brier: number
  log_loss: number
  roc_auc: number
  roi_simulated: number
}

export type SeasonAccuracyResponse = {
  championship: string
  points: SeasonAccuracyPoint[]
}

export type TeamToPlay = {
  team: string
  success_pct: number
  strength_pct: number
  form_pct: number
}

export type TeamsToPlayItem = {
  championship: string
  top3: TeamToPlay[]
}

export type TeamsToPlayResponse = {
  generated_at_utc: string
  items: TeamsToPlayItem[]
}

export type TrackBucket = {
  n: number
  accuracy: number
  roi_avg: number
}

export type TrackSummary = {
  n: number
  accuracy: number
  roi_total: number
  roi_avg: number
  by_confidence: Record<string, TrackBucket>
}

export type TrackPoint = {
  date_utc: string
  n: number
  accuracy: number
  roi_total: number
}

export type TrackRecordResponse = {
  generated_at_utc: string
  championship: string
  days: number
  summary: TrackSummary
  points: TrackPoint[]
}

export type ExplainResponse = {
  generated_at_utc: string
  championship: string
  match_id?: string | null
  team: string
  pick?: string | null
  why: string[]
  risks: string[]
}
