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

export type MarketConfidence = {
  probability: number
  confidence: number
  risk: string
}

export type MultiMarketConfidenceResponse = {
  generated_at_utc: string
  match_id: string
  match: string
  markets: Record<string, MarketConfidence>
}

export type ValuePickItem = {
  match_id: string
  championship: string
  home_team: string
  away_team: string
  kickoff_unix?: number | null
  market: string
  success_pct: number
  odds: number
  implied_pct: number
  value_index: number
  value_level: "LOW" | "MEDIUM" | "HIGH"
  source?: string | null
}

export type ValuePickResponse = {
  generated_at_utc: string
  items: ValuePickItem[]
}

export type UserProfile = {
  user_id: string
  profile: "PRUDENT" | "BALANCED" | "AGGRESSIVE"
  bankroll_reference: number
  preferred_markets: string[]
  preferred_championships: string[]
  notifications_enabled: boolean
  notifications_min_confidence: "LOW" | "MEDIUM" | "HIGH"
  updated_at_unix: number
}

export type UserProfileUpdate = Partial<Omit<UserProfile, "user_id" | "updated_at_unix">>

export type TenantBranding = {
  app_name: string
  tagline?: string | null
  logo_url?: string | null
  primary_color?: string | null
}

export type TenantFilters = {
  visible_championships: string[]
  active_markets: string[]
  min_confidence: "LOW" | "MEDIUM" | "HIGH"
}

export type TenantCompliance = {
  disclaimer_text: string
  educational_only: boolean
  allowed_countries: string[]
  blocked_countries: string[]
}

export type TenantFeatures = {
  disabled_profiles: Array<"PRUDENT" | "BALANCED" | "AGGRESSIVE">
}

export type TenantConfig = {
  tenant_id: string
  branding: TenantBranding
  filters: TenantFilters
  compliance: TenantCompliance
  features: TenantFeatures
  updated_at_unix: number
}

export type SystemStatusResponse = {
  data_provider: string
  real_data_only: boolean
  data_error?: string | null
  matches_loaded: number
  api_football_key_present: boolean
  api_football_leagues_configured: number
  api_football_seasons_configured: number
  football_data_key_present: boolean
  football_data_competitions_configured: number
  now_utc: string
}
