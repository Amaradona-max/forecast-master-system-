"use client"

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { GlassTooltip } from "./ChartTooltip"

export function WinProbabilityChart({ trend, fmtPct }: { trend: Array<Record<string, unknown>>; fmtPct: (n: number) => string }) {
  return (
    <div className="mt-4 h-52 rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={trend}>
          <XAxis dataKey="md" hide />
          <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(Number(v) * 100)}%`} />
          <Tooltip
            formatter={(v, name) => {
              if (name === "p1") return [fmtPct(Number(v)), "1 (Casa)"]
              if (name === "px") return [fmtPct(Number(v)), "X (Pareggio)"]
              if (name === "p2") return [fmtPct(Number(v)), "2 (Trasferta)"]
              return [fmtPct(Number(v)), String(name)]
            }}
            labelFormatter={(l) => `Matchday ${String(l ?? "")}`}
            content={<GlassTooltip />}
          />
          <Line type="monotone" dataKey="p1" stroke="#3b82f6" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="px" stroke="#a855f7" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="p2" stroke="#f43f5e" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
