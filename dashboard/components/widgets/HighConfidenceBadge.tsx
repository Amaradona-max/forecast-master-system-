"use client"

function getHighConfidenceInfo(p: Record<string, unknown> | null | undefined) {
  const c = p?.confidence ?? p?.predicted_confidence ?? (p?.explain as Record<string, unknown> | null | undefined)?.confidence
  const prob = p?.predicted_prob ?? p?.probability ?? p?.prob ?? (p?.explain as Record<string, unknown> | null | undefined)?.predicted_prob

  if (typeof c === "string") {
    const isHigh = c.toUpperCase() === "HIGH"
    return {
      isHigh,
      title: isHigh ? "Confidence = HIGH" : `Confidence = ${c}`,
      prob
    }
  }

  if (typeof c === "number") {
    const isHigh = c >= 0.7
    return {
      isHigh,
      title: isHigh ? "Confidence ≥ 0.70" : `Confidence = ${c.toFixed(2)}`,
      prob
    }
  }

  return { isHigh: false, title: "Confidence non disponibile", prob }
}

export function HighConfidenceBadge({ prediction }: { prediction: Record<string, unknown> | null | undefined }) {
  const info = getHighConfidenceInfo(prediction)
  if (!info.isHigh) return null

  const extra =
    typeof info.prob === "number"
      ? ` | p=${Math.max(0, Math.min(1, info.prob)).toFixed(2)}`
      : ""

  return (
    <span
      title={`${info.title}${extra}`}
      className="inline-flex items-center gap-1 rounded-full border border-sky-500/20 bg-sky-500/15 px-2 py-0.5 text-[10px] font-extrabold text-sky-700 dark:text-sky-300"
    >
      HC
    </span>
  )
}
