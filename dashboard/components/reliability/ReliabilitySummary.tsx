"use client"

import { useEffect, useState } from "react"

type TempPayload = {
  championships?: Record<string, { temperature?: number }>
}

type DriftPayload = {
  championships?: Record<string, { level?: string }>
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null
}

export function ReliabilitySummary() {
  const [data, setData] = useState<{ temp: TempPayload; drift: DriftPayload } | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      fetch("/static/calibration_temperature.json").then((r) => r.json() as Promise<TempPayload>),
      fetch("/static/drift_status.json").then((r) => r.json() as Promise<DriftPayload>)
    ])
      .then(([temp, drift]) => {
        if (!alive) return
        setData({ temp, drift })
      })
      .catch(() => {
        if (!alive) return
        setData(null)
      })
    return () => {
      alive = false
    }
  }, [])

  if (!data) return null

  const driftChamps = isRecord(data.drift?.championships) ? data.drift.championships : {}
  const tempChamps = isRecord(data.temp?.championships) ? data.temp.championships : {}
  const leagues = Object.keys(driftChamps)
  let ok = 0
  let warn = 0
  let high = 0
  leagues.forEach((l) => {
    const row0 = driftChamps[l]
    const row = isRecord(row0) ? row0 : {}
    const level = String(row.level ?? "ok")
    if (level === "high") high += 1
    else if (level === "warn") warn += 1
    else ok += 1
  })

  const temps = Object.values(tempChamps)
    .map((x) => Number((isRecord(x) ? x.temperature : undefined) ?? NaN))
    .filter((v) => Number.isFinite(v))
  const avgT = temps.length ? (temps.reduce((a, b) => a + b, 0) / temps.length).toFixed(2) : "—"

  return (
    <div className="grid gap-4 sm:grid-cols-4">
      <KPI label="Campionati OK" value={ok} />
      <KPI label="Warning" value={warn} tone="warn" />
      <KPI label="High Drift" value={high} tone="danger" />
      <KPI label="Temp. Media" value={avgT} />
    </div>
  )
}

function KPI({ label, value, tone }: { label: string; value: string | number; tone?: "warn" | "danger" }) {
  const toneCls =
    tone === "danger"
      ? "text-red-600 dark:text-red-400"
      : tone === "warn"
        ? "text-amber-600 dark:text-amber-400"
        : "text-zinc-900 dark:text-zinc-50"

  return (
    <div className="rounded-2xl border border-white/10 bg-white/10 p-4 shadow-sm backdrop-blur-md dark:bg-zinc-950/25">
      <div className="text-xs uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`mt-2 text-2xl font-extrabold ${toneCls}`}>{value}</div>
    </div>
  )
}
