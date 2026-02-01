"use client"

import { useMemo } from "react"

import { PredictionBar } from "@/components/ui/PredictionBar"
import { FragilityBadge, type Fragility } from "@/components/widgets/FragilityBadge"

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

type EVExplain = {
  best?: {
    ev?: number
    outcome?: string
    odds?: number
  }
}

type BacktestMetricsExplain = {
  accuracy?: number
  n?: number
}

type SimilarExplain = {
  similar_reliability_pct?: number
  similar_samples?: number
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
  return new Date(k * 1000).toLocaleString(undefined, {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  })
}

function pillClass(tone: "green" | "yellow" | "red" | "blue" | "zinc") {
  if (tone === "green") return "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
  if (tone === "yellow") return "border-amber-500/20 bg-amber-500/15 text-amber-700 dark:text-amber-300"
  if (tone === "red") return "border-red-500/20 bg-red-500/15 text-red-700 dark:text-red-300"
  if (tone === "blue") return "border-sky-500/20 bg-sky-500/15 text-sky-700 dark:text-sky-300"
  return "border-zinc-500/20 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
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

function evFromExplain(explain?: Record<string, unknown>) {
  const ev0 = explain?.ev
  if (!ev0 || typeof ev0 !== "object") return null
  const best = (ev0 as EVExplain).best
  if (!best || typeof best !== "object") return null
  const bestData = best as EVExplain["best"]
  const ev = Number(bestData?.ev ?? NaN)
  const outcome = String(bestData?.outcome ?? "")
  const odds = Number(bestData?.odds ?? NaN)
  return {
    ev: Number.isFinite(ev) ? ev : null,
    outcome: outcome || null,
    odds: Number.isFinite(odds) ? odds : null
  }
}

function histFromExplain(explain?: Record<string, unknown>) {
  const bt0 = explain?.backtest_metrics
  if (!bt0 || typeof bt0 !== "object") return null
  const bt = bt0 as BacktestMetricsExplain
  const acc = Number(bt.accuracy ?? NaN)
  const n = Number(bt.n ?? NaN)
  if (!Number.isFinite(acc) || acc <= 0) return null
  return { accuracy: acc, n: Number.isFinite(n) ? n : null }
}

function similarFromExplain(explain?: Record<string, unknown>) {
  const sx = explain as SimilarExplain | undefined
  const pct = Number(sx?.similar_reliability_pct ?? NaN)
  const n = Number(sx?.similar_samples ?? NaN)
  if (!Number.isFinite(pct) || pct <= 0) return null
  return {
    pct,
    n: Number.isFinite(n) && n > 0 ? n : null
  }
}

function stakeHint({
  tier,
  chaosIdx,
  fragilityLevel,
  warnings
}: {
  tier: string | null
  chaosIdx: number | null
  fragilityLevel: string | null
  warnings: string[]
}) {
  // Base: S→alto, A→medio, B→basso, C→minimo
  let s: "minimo" | "basso" | "medio" | "alto" = "basso"
  if (tier === "S") s = "alto"
  else if (tier === "A") s = "medio"
  else if (tier === "B") s = "basso"
  else if (tier === "C") s = "minimo"

  const chaos = typeof chaosIdx === "number" && Number.isFinite(chaosIdx) ? chaosIdx : null
  const fl = (fragilityLevel || "").toLowerCase()

  const hasDrift = warnings.some((w) => /drift/i.test(String(w)))
  const risky = (chaos !== null && chaos >= 70) || fl === "high" || fl === "very_high" || hasDrift

  // Se molto rischioso, riduci di uno step
  const order: Array<typeof s> = ["minimo", "basso", "medio", "alto"]
  const idx = order.indexOf(s)
  const next = risky ? Math.max(0, idx - 1) : idx

  const out = order[next] ?? s
  const tone = out === "alto" ? ("green" as const) : out === "medio" ? ("blue" as const) : out === "basso" ? ("yellow" as const) : ("zinc" as const)
  return { label: `Stake ${out}`, tone }
}

function chaosFromExplain(explain?: Record<string, unknown>) {
  const chaos0 = explain?.chaos
  if (!chaos0 || typeof chaos0 !== "object") return { idx: null as number | null, upset: null as boolean | null }
  const chaos = chaos0 as Record<string, unknown>
  const idx = Number(chaos.index ?? NaN)
  const upset = Boolean(chaos.upset_watch)
  return { idx: Number.isFinite(idx) ? idx : null, upset }
}

function fragilityFromExplain(explain?: Record<string, unknown>): Fragility | null {
  const frag0 = explain?.fragility
  if (!frag0 || typeof frag0 !== "object") return null
  const frag = frag0 as Record<string, unknown>
  return { level: String(frag.level ?? "") }
}

function metricTone(v01: number) {
  if (v01 >= 0.85) return "red" as const
  if (v01 >= 0.7) return "yellow" as const
  if (v01 >= 0.55) return "blue" as const
  return "green" as const
}

function MetricBar({ label, value01 }: { label: string; value01: number }) {
  const v = clamp01(value01)
  const tone = metricTone(v)
  return (
    <div className="min-w-[120px]">
      <div className="flex items-center justify-between text-[11px] text-zinc-600 dark:text-zinc-300">
        <span className="font-semibold tracking-tight">{label}</span>
        <span className="num opacity-80">{Math.round(v * 100)}%</span>
      </div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-zinc-200/70 dark:bg-zinc-800/70">
        <div
          className={[
            "h-2 rounded-full",
            tone === "green" ? "bg-emerald-500/60" : "",
            tone === "blue" ? "bg-sky-500/60" : "",
            tone === "yellow" ? "bg-amber-500/60" : "",
            tone === "red" ? "bg-red-500/60" : ""
          ].join(" ")}
          style={{ width: `${Math.round(v * 100)}%` }}
        />
      </div>
    </div>
  )
}

export function MatchCard({ match, label, labelTone = "zinc", chaosIndex, upsetWatch, why, onOpen }: MatchCardProps) {
  const tier = useMemo(() => tierFromExplain(match.explain), [match.explain])
  const chaos = useMemo(() => chaosFromExplain(match.explain), [match.explain])
  const frag = useMemo(() => fragilityFromExplain(match.explain), [match.explain])

  const chaosIdx = Number.isFinite(Number(chaosIndex)) ? Number(chaosIndex) : chaos.idx
  const upset = typeof upsetWatch === "boolean" ? upsetWatch : chaos.upset

  const p1 = clamp01(Number(match?.probabilities?.home_win ?? match?.probabilities?.["1"] ?? 0))
  const px = clamp01(Number(match?.probabilities?.draw ?? match?.probabilities?.["X"] ?? 0))
  const p2 = clamp01(Number(match?.probabilities?.away_win ?? match?.probabilities?.["2"] ?? 0))

  const tierTone =
    tier?.tier === "S" ? "green" : tier?.tier === "A" ? "green" : tier?.tier === "B" ? "yellow" : tier?.tier === "C" ? "zinc" : "zinc"

  const warnings = useMemo(() => tier?.warnings?.slice(0, 2) ?? [], [tier?.warnings])
  const ev = useMemo(() => evFromExplain(match.explain), [match.explain])
  const hist = useMemo(() => histFromExplain(match.explain), [match.explain])
  const similar = useMemo(() => similarFromExplain(match.explain), [match.explain])
  const fragLevel = typeof frag?.level === "string" ? frag.level : null
  const stake = useMemo(
    () => stakeHint({ tier: tier?.tier ?? null, chaosIdx: chaosIdx ?? null, fragilityLevel: fragLevel, warnings }),
    [tier?.tier, chaosIdx, fragLevel, warnings]
  )

  return (
    <button
      type="button"
      onClick={() => onOpen(String(match.match_id))}
      className={[
        "w-full text-left rounded-3xl border border-zinc-200/70 bg-white/70 p-4 shadow-sm backdrop-blur-md transition-all duration-200",
        "hover:-translate-y-0.5 hover:bg-white hover:shadow-medium",
        "dark:border-zinc-800/70 dark:bg-zinc-950/25 dark:hover:bg-zinc-950/35"
      ].join(" ")}
      title="Apri dettagli (Explain)"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-[240px]">
          <div className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            {match.home_team} <span className="text-zinc-400">vs</span> {match.away_team}
          </div>
          <div className="mt-0.5 text-[11px] text-zinc-600 dark:text-zinc-300">
            {fmtKickoff(match.kickoff_unix)} · <span className="uppercase">{String(match.status || "").toLowerCase()}</span>
          </div>

          {warnings.length ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {warnings.map((w) => (
                <span key={w} className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("yellow")}`} title={w}>
                  {w}
                </span>
              ))}
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {label ? <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass(labelTone)}`}>{label}</span> : null}

          {tier ? (
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass(tierTone)}`}
              title={tier.score !== null ? `Confidence score ${(tier.score * 100).toFixed(0)}%` : "Tier"}
            >
              Tier {tier.tier}
            </span>
          ) : null}

          {upset ? <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass("red")}`}>UPSET</span> : null}

          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("yellow")}`} title="Confidence (modello)">
            Conf {Math.round(clamp01(Number(match.confidence ?? 0)) * 100)}%
          </span>

          {ev && ev.ev !== null ? (
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass(ev.ev > 0 ? "green" : ev.ev < 0 ? "red" : "zinc")}`}
              title={ev.outcome ? `Best EV su ${ev.outcome}${ev.odds ? ` (odds ${ev.odds.toFixed(2)})` : ""}` : "Expected Value"}
            >
              EV {ev.ev.toFixed(2)}
            </span>
          ) : null}

          {hist?.accuracy ? (
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass("blue")}`}
              title={hist.n ? `Accuratezza storica (campionato) su ${hist.n} match` : "Accuratezza storica (campionato)"}
            >
              Hist {Math.round(hist.accuracy * 100)}%
            </span>
          ) : null}

          {similar?.pct ? (
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass("zinc")}`}
              title={similar.n ? `Accuratezza in match simili (bucket) su ${similar.n} match` : "Accuratezza in match simili (bucket)"}
            >
              Simili {Math.round(similar.pct)}%
            </span>
          ) : null}

          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${pillClass(stake.tone)}`} title="Hint di stake basato su tier, caos, fragilità e drift">
            {stake.label}
          </span>

          <FragilityBadge fragility={frag} />
        </div>
      </div>

      <div className="mt-3">
        <PredictionBar p1={p1} px={px} p2={p2} compact />
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-4">
          {Number.isFinite(Number(chaosIdx)) ? <MetricBar label="Chaos" value01={clamp01(Number(chaosIdx) / 100)} /> : null}
          {frag?.score !== null && typeof frag?.score === "number" ? <MetricBar label="Fragility" value01={clamp01(Number(frag.score))} /> : null}
        </div>

        <div className="text-[11px] text-zinc-600 dark:text-zinc-300">
          {why?.length ? (
            <span title={why.join(", ")}>
              Perché: {why.slice(0, 3).join(", ")}
              {why.length > 3 ? "…" : ""}
            </span>
          ) : (
            <span className="opacity-80">Click per dettagli</span>
          )}
        </div>
      </div>
    </button>
  )
}
