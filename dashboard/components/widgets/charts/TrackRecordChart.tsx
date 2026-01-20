"use client"

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

export function TrackRecordChart({
  trackSeries,
  fmtPct,
  fmtSigned,
  trackError
}: {
  trackSeries: Array<Record<string, unknown>>
  fmtPct: (n: number) => string
  fmtSigned: (n: number) => string
  trackError?: string
}) {
  return (
    <div className="mt-4 h-56 rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
      {trackSeries.length ? (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={trackSeries}>
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="acc" domain={[0, 1]} tickFormatter={(v) => `${Math.round(Number(v) * 100)}%`} />
            <YAxis yAxisId="roi" orientation="right" tickFormatter={(v) => fmtSigned(Number(v))} />
            <Tooltip
              formatter={(value, name) => {
                if (name === "accuracy") return [fmtPct(Number(value)), "Accuracy"]
                if (name === "roi_total") return [fmtSigned(Number(value)), "ROI tot"]
                return [String(value), String(name)]
              }}
            />
            <Line yAxisId="acc" type="monotone" dataKey="accuracy" stroke="#22c55e" strokeWidth={2} dot={false} />
            <Line yAxisId="roi" type="monotone" dataKey="roi_total" stroke="#3b82f6" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="grid h-full place-items-center text-sm text-zinc-600 dark:text-zinc-300">{trackError ? trackError : "n/d"}</div>
      )}
    </div>
  )
}
