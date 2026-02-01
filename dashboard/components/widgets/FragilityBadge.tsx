"use client"

export type Fragility = {
  level?: "low" | "medium" | "high" | string | null
  score?: number | null
  margin?: number | null
  entropy?: number | null
}

export function FragilityBadge({ fragility }: { fragility?: Fragility | null }) {
  if (!fragility) return null

  const lvl = String(fragility.level ?? "low")
  const score = typeof fragility.score === "number" ? fragility.score : null
  const margin = typeof fragility.margin === "number" ? fragility.margin : 0
  const entropy = typeof fragility.entropy === "number" ? fragility.entropy : 0

  const map: Record<string, string> = {
    low: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
    medium: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
    high: "bg-red-500/15 text-red-700 dark:text-red-400"
  }

  const label = lvl === "high" ? "Fragile" : lvl === "medium" ? "Moderata" : "Stabile"
  const title = score !== null ? `Fragility ${(score * 100).toFixed(0)}% | margin ${margin} | entropy ${entropy}` : "Fragility"

  return (
    <span title={title} className={`inline-flex items-center gap-2 rounded-full px-2 py-0.5 text-xs font-bold ${map[lvl] || map.low}`}>
      <span>{label}</span>
      {score !== null ? <span className="num opacity-80">{(score * 100).toFixed(0)}%</span> : null}
    </span>
  )
}
