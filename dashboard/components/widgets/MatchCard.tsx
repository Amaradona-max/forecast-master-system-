"use client"

import { useMemo } from "react"

import { Badge } from "@/components/ui/Badge"
import { PredictionBar } from "@/components/ui/PredictionBar"

export type OverviewMatch = {
  match_id: string
  championship: string
  home_team: string
  away_team: string
  status: string
  kickoff_unix?: number | null
  updated_at_unix: number
  probabilities: Record<string, number>
  confidence: number
  explain?: Record<string, unknown>
}

type DecisionGateExplain = {
  confidence_tier?: string
  confidence_score?: number
  warnings?: string[]
}

export type MatchCardProps = {
  match: OverviewMatch
  label?: string | null
  labelTone?: "green" | "red" | "yellow" | "blue" | "zinc"
  chaosIndex?: number | null
  upsetWatch?: boolean | null
  why?: string[] | null
  onOpen: (matchId: string) => void
}

function clamp01(x: number) {
  if (Number.isNaN(x)) return 0
  return x < 0 ? 0 : x > 1 ? 1 : x
}

function fmtKickoff(unix: number | null | undefined) {
  const k = Number(unix ?? 0)
  if (!Number.isFinite(k) || k <= 0) return "n/d"
  return new Date(k * 1000).toLocaleString("it-IT", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  })
}

function tierFromExplain(explain?: Record<string, unknown>) {
  const d0 = explain?.decision_gate ?? explain?.decision
  if (!d0 || typeof d0 !== "object") return null
  const d = d0 as DecisionGateExplain
  const t = String(d.confidence_tier ?? "")
  const score = Number(d.confidence_score ?? NaN)
  const warnings = Array.isArray(d.warnings) ? d.warnings.map((x) => String(x)) : []
  return t ? { tier: t, score: Number.isFinite(score) ? score : null, warnings } : null
}

function getTierBadgeVariant(tier: string): "success" | "info" | "warning" | "default" {
  if (tier === "S" || tier === "A") return "success"
  if (tier === "B") return "info"
  if (tier === "C") return "warning"
  return "default"
}

function getConfidenceBadgeVariant(confidence: number): "success" | "info" | "warning" {
  if (confidence >= 0.8) return "success"
  if (confidence >= 0.6) return "info"
  return "warning"
}

function labelVariant(tone: "green" | "red" | "yellow" | "blue" | "zinc") {
  if (tone === "green") return "success"
  if (tone === "red") return "danger"
  if (tone === "yellow") return "warning"
  if (tone === "blue") return "info"
  return "default"
}

export function MatchCard({ match, label, labelTone = "zinc", chaosIndex, upsetWatch, why, onOpen }: MatchCardProps) {
  const tier = useMemo(() => tierFromExplain(match.explain), [match.explain])

  const p1 = clamp01(Number(match?.probabilities?.home_win ?? match?.probabilities?.["1"] ?? 0))
  const px = clamp01(Number(match?.probabilities?.draw ?? match?.probabilities?.["X"] ?? 0))
  const p2 = clamp01(Number(match?.probabilities?.away_win ?? match?.probabilities?.["2"] ?? 0))

  const confidence = clamp01(Number(match.confidence ?? 0))
  const chaos = Number.isFinite(Number(chaosIndex)) ? Number(chaosIndex) : null

  const maxProb = Math.max(p1, px, p2)
  let mainPrediction = ""
  if (maxProb === p1) mainPrediction = "1"
  else if (maxProb === px) mainPrediction = "X"
  else mainPrediction = "2"

  const isLive = match.status?.toLowerCase() === "live"

  return (
    <button
      type="button"
      onClick={() => onOpen(String(match.match_id))}
      className="card-modern w-full text-left p-6 group"
    >
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {isLive && (
          <Badge variant="danger" size="sm" pulse>
            🔴 LIVE
          </Badge>
        )}
        {label && (
          <Badge variant={labelVariant(labelTone)} size="sm">
            {label}
          </Badge>
        )}
        {tier && (
          <Badge variant={getTierBadgeVariant(tier.tier)} size="sm">
            Tier {tier.tier}
          </Badge>
        )}
        {upsetWatch && (
          <Badge variant="danger" size="sm">
            ⚠️ UPSET
          </Badge>
        )}
      </div>

      <div className="mb-4">
        <h3 className="text-lg sm:text-xl font-bold text-neutral-900 dark:text-dark-text-primary mb-1 group-hover:text-accent-blue transition-colors">
          ⚽ {match.home_team} <span className="text-neutral-400 mx-2">vs</span> {match.away_team}
        </h3>
        <p className="text-xs sm:text-sm text-neutral-600 dark:text-dark-text-secondary">
          📍 {match.championship} • {fmtKickoff(match.kickoff_unix)}
        </p>
      </div>

      <div className="mb-4">
        <div className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">📊 Probabilità Vittoria</div>
        <PredictionBar p1={p1} px={px} p2={p2} compact={false} />
      </div>

      {why && why.length > 0 && (
        <div className="mb-4 p-3 rounded-2xl bg-pastel-blue/30 dark:bg-pastel-blue-dark/20 border border-pastel-blue dark:border-pastel-blue-dark">
          <div className="text-xs font-semibold text-neutral-700 dark:text-neutral-300 mb-1">💡 Insights</div>
          <p className="text-xs text-neutral-600 dark:text-neutral-400">{why.slice(0, 2).join(" • ")}</p>
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <div className="text-center p-3 rounded-xl bg-white/50 dark:bg-dark-bg/30 border border-neutral-200 dark:border-dark-border">
          <div className="text-xs text-neutral-600 dark:text-neutral-400 mb-1">Confidence</div>
          <div className="flex items-center justify-center gap-1">
            <Badge variant={getConfidenceBadgeVariant(confidence)} size="sm">
              {Math.round(confidence * 100)}%
            </Badge>
          </div>
        </div>

        <div className="text-center p-3 rounded-xl bg-white/50 dark:bg-dark-bg/30 border border-neutral-200 dark:border-dark-border">
          <div className="text-xs text-neutral-600 dark:text-neutral-400 mb-1">Chaos Index</div>
          <div className="text-sm font-bold text-neutral-900 dark:text-dark-text-primary">
            {chaos !== null ? `${Math.round(chaos)}` : "n/d"}
          </div>
        </div>

        <div className="text-center p-3 rounded-xl bg-white/50 dark:bg-dark-bg/30 border border-neutral-200 dark:border-dark-border">
          <div className="text-xs text-neutral-600 dark:text-neutral-400 mb-1">Pronostico</div>
          <div className="text-sm font-bold text-accent-emerald dark:text-pastel-mint">{mainPrediction}</div>
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-neutral-200 dark:border-dark-border">
        <p className="text-xs text-neutral-500 dark:text-neutral-400 text-center">👆 Click per dettagli completi</p>
      </div>
    </button>
  )
}
