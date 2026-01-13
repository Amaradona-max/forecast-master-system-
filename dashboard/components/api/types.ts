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
