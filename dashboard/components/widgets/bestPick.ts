export function isHighConfidence(p: Record<string, unknown> | null | undefined): boolean {
  const c = p?.confidence ?? p?.predicted_confidence ?? (p?.explain as Record<string, unknown> | null | undefined)?.confidence
  if (typeof c === "string") return c.toUpperCase() === "HIGH"
  if (typeof c === "number") return c >= 0.7
  return false
}

export function isTopPick(p: Record<string, unknown> | null | undefined, topMax: number): boolean {
  const explain = p?.explain as Record<string, unknown> | null | undefined
  const frag = explain?.fragility as Record<string, unknown> | null | undefined
  const s = frag?.score
  return typeof s === "number" ? s < topMax : false
}

export function isBestPick(p: Record<string, unknown> | null | undefined, topMax: number): boolean {
  return isTopPick(p, topMax) && isHighConfidence(p)
}
