"use client"

import { useEffect, useState } from "react"

type TempPayload = {
  championships?: Record<string, { temperature?: number; n?: number }>
}

type DriftPayload = {
  championships?: Record<string, { level?: string; psi?: { outcome?: number; confidence_bins?: number } }>
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null
}

export function LeagueReliabilityTable() {
  const [temp, setTemp] = useState<TempPayload | null>(null)
  const [drift, setDrift] = useState<DriftPayload | null>(null)

  useEffect(() => {
    let alive = true
    fetch("/static/calibration_temperature.json")
      .then((r) => r.json() as Promise<TempPayload>)
      .then((data) => {
        if (!alive) return
        setTemp(data)
      })
      .catch(() => {
        if (!alive) return
        setTemp(null)
      })

    fetch("/static/drift_status.json")
      .then((r) => r.json() as Promise<DriftPayload>)
      .then((data) => {
        if (!alive) return
        setDrift(data)
      })
      .catch(() => {
        if (!alive) return
        setDrift(null)
      })

    return () => {
      alive = false
    }
  }, [])

  if (!temp || !drift) return null

  const tempChamps = isRecord(temp.championships) ? temp.championships : {}
  const driftChamps = isRecord(drift.championships) ? drift.championships : {}
  const leagues = Object.keys(tempChamps)

  return (
    <div className="rounded-2xl border border-white/10 bg-white/10 p-4 shadow-sm backdrop-blur-md dark:bg-zinc-950/25">
      <h2 className="mb-3 text-lg font-bold">Stato per campionato</h2>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="py-2 text-left">League</th>
              <th className="text-right">T</th>
              <th className="text-right">Samples</th>
              <th className="text-center">Drift</th>
              <th className="text-right">PSI out</th>
              <th className="text-right">PSI conf</th>
            </tr>
          </thead>
          <tbody>
            {leagues.map((l) => {
              const t0 = tempChamps[l]
              const t = isRecord(t0) ? t0 : {}
              const d0 = driftChamps[l]
              const d = isRecord(d0) ? d0 : {}
              const psi0 = isRecord(d.psi) ? d.psi : {}
              const lvl = String(d.level ?? "ok")
              const tempVal = Number(t.temperature ?? NaN)
              const tempOut = Number.isFinite(tempVal) ? tempVal.toFixed(2) : "—"
              const nOut = Number.isFinite(Number(t.n ?? NaN)) ? String(t.n) : "—"
              const psiOut = Number.isFinite(Number(psi0.outcome ?? NaN)) ? Number(psi0.outcome).toFixed(3) : "—"
              const psiConf = Number.isFinite(Number(psi0.confidence_bins ?? NaN))
                ? Number(psi0.confidence_bins).toFixed(3)
                : "—"
              return (
                <tr key={l} className="border-t border-white/10">
                  <td className="py-2 font-semibold">{l}</td>
                  <td className="text-right num">{tempOut}</td>
                  <td className="text-right num">{nOut}</td>
                  <td className="text-center">
                    <Badge level={lvl} />
                  </td>
                  <td className="text-right num">{psiOut}</td>
                  <td className="text-right num">{psiConf}</td>
                </tr>
              )
            })}
            {!leagues.length ? (
              <tr>
                <td className="py-4 text-zinc-600 dark:text-zinc-300" colSpan={6}>
                  Nessun dato disponibile.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Badge({ level }: { level: string }) {
  const map: Record<string, string> = {
    ok: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
    warn: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
    high: "bg-red-500/15 text-red-700 dark:text-red-400"
  }
  return <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${map[level] ?? map.ok}`}>{level.toUpperCase()}</span>
}
