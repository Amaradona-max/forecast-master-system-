"use client"

export type CompareExplainabilityDriver = {
  feature: string
  delta: number
  impact_pct: number
  winner: "A" | "B"
}

export type CompareExplainabilityPayload = {
  drivers: CompareExplainabilityDriver[]
  summary_text?: string | null
} & Record<string, unknown>

export function CompareExplainabilityCard({ compare }: { compare?: CompareExplainabilityPayload | null }) {
  if (!compare) return null
  const drivers = Array.isArray(compare.drivers) ? compare.drivers : []

  return (
    <div className="rounded-2xl border border-white/10 bg-white/10 p-4 backdrop-blur-md">
      <h3 className="mb-3 text-sm font-bold">Perché il Match A è migliore del Match B?</h3>

      {compare.summary_text ? (
        <p className="mb-3 text-sm text-zinc-700 dark:text-zinc-200">{compare.summary_text}</p>
      ) : null}

      <div className="space-y-2">
        {drivers.map((d) => (
          <div key={d.feature} className="flex items-center gap-2 text-xs">
            <div className="w-28 truncate">{human(d.feature)}</div>

            <div className="flex-1 h-2 rounded bg-white/10 overflow-hidden">
              <div
                className={`h-full ${d.winner === "A" ? "bg-emerald-500/70" : "bg-sky-500/70"}`}
                style={{ width: `${d.impact_pct.toFixed(0)}%` }}
              />
            </div>

            <div className="w-8 text-right num">{d.impact_pct.toFixed(0)}%</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function human(f: string) {
  return f.replace("home_", "Casa ").replace("away_", "Trasferta ").replace("_", " ")
}
