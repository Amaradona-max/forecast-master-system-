"use client"

type ExplainabilityItem = [string, number, number]

type ExplainabilityPayload = {
  target?: string
  top_positive?: ExplainabilityItem[]
  top_negative?: ExplainabilityItem[]
}

export function ExplainabilityCard({ why }: { why?: unknown | null }) {
  const payload = parsePayload(why)
  if (!payload) return null
  const topPositive = normalizeItems(payload.top_positive)
  const topNegative = normalizeItems(payload.top_negative)

  return (
    <div className="rounded-2xl border border-white/10 bg-white/10 p-4 backdrop-blur-md">
      <h3 className="mb-2 text-sm font-bold">Perché {label(payload.target)}?</h3>

      <Section title="Fattori a favore" items={topPositive} positive />
      <Section title="Fattori contro" items={topNegative} />
    </div>
  )
}

function Section({
  title,
  items,
  positive
}: {
  title: string
  items?: ExplainabilityItem[]
  positive?: boolean
}) {
  if (!items?.length) return null
  return (
    <div className="mt-3">
      <div className="mb-1 text-xs uppercase text-zinc-500">{title}</div>
      {items.map(([name, , pct]) => (
        <div key={name} className="flex items-center gap-2 text-xs">
          <div className="w-32 truncate">{human(name)}</div>
          <div className="flex-1 h-2 rounded bg-white/10">
            <div
              className={`h-full ${positive ? "bg-emerald-500/70" : "bg-red-500/60"}`}
              style={{ width: `${pct.toFixed(0)}%` }}
            />
          </div>
          <div className="w-10 text-right num">{pct.toFixed(0)}%</div>
        </div>
      ))}
    </div>
  )
}

function label(t?: string) {
  return t === "home_win" ? "vince la casa" : t === "away_win" ? "vince la trasferta" : "pareggio"
}

function human(f: string) {
  return f.replace("home_", "Casa ").replace("away_", "Trasferta ").replace("_", " ")
}

function normalizeItems(value: unknown): ExplainabilityItem[] {
  if (!Array.isArray(value)) return []
  return value
    .map((row) => {
      if (!Array.isArray(row) || row.length < 3) return null
      const [name, , pct] = row
      if (typeof name !== "string") return null
      const p = Number(pct)
      if (!Number.isFinite(p)) return null
      return [name, 0, p] as ExplainabilityItem
    })
    .filter((row): row is ExplainabilityItem => Boolean(row))
}

function parsePayload(value: unknown): ExplainabilityPayload | null {
  if (!value || typeof value !== "object") return null
  const v = value as Record<string, unknown>
  return {
    target: typeof v.target === "string" ? v.target : undefined,
    top_positive: Array.isArray(v.top_positive) ? (v.top_positive as ExplainabilityItem[]) : undefined,
    top_negative: Array.isArray(v.top_negative) ? (v.top_negative as ExplainabilityItem[]) : undefined
  }
}
