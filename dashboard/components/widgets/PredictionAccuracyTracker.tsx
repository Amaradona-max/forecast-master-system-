"use client"

import { useEffect, useState } from "react"

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { fetchSeasonProgress } from "@/components/api/client"
import type { SeasonAccuracyPoint } from "@/components/api/types"
import { Card } from "@/components/widgets/Card"

export function PredictionAccuracyTracker() {
  const [data, setData] = useState<SeasonAccuracyPoint[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchSeasonProgress("all")
      .then((r) => setData(r.points))
      .catch((e) => setError(String(e?.message ?? e)))
  }, [])

  return (
    <Card>
      <div className="text-sm font-semibold tracking-tight">Accuracy Tracker</div>
      <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Evoluzione giornaliera (dati reali se disponibili)</div>
      {error ? (
        <div className="mt-3 text-sm text-red-600">{error}</div>
      ) : (
        <div className="mt-4 h-44 rounded-2xl border border-zinc-200/70 bg-white/55 p-3 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/25">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <XAxis dataKey="date_utc" hide />
              <YAxis domain={[0.6, 0.8]} />
              <Tooltip />
              <Line type="monotone" dataKey="roc_auc" stroke="#10b981" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}
