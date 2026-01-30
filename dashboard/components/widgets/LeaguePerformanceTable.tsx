"use client"

import { useEffect, useMemo, useState } from "react"

import { apiFetchTenant } from "@/components/api/client"

type Row = {
  championship: string
  n: number
  accuracy: number
  brier: number
  logloss: number
  ece: number
}

type SortKey = keyof Row
type SortDir = "asc" | "desc"

function clamp01(n: number) {
  const v = Number(n)
  if (!Number.isFinite(v)) return 0
  return Math.max(0, Math.min(1, v))
}

function fmtPct(v: number) {
  const x = clamp01(v) * 100
  return `${x.toFixed(0)}%`
}

function fmt3(v: number) {
  const x = Number(v)
  if (!Number.isFinite(x)) return "n/d"
  return x.toFixed(3)
}

function reliabilityLabel(row: Row) {
  if (!Number.isFinite(row.n) || row.n < 80) return { label: "n/d", tone: "zinc" as const }
  if (row.ece <= 0.06 && row.accuracy >= 0.5) return { label: "Affidabile", tone: "green" as const }
  if (row.ece <= 0.09) return { label: "Medio", tone: "yellow" as const }
  return { label: "Instabile", tone: "red" as const }
}

function trendBadge(championship: string, trends: Record<string, unknown>) {
  const row0 = trends?.[String(championship)]
  const row = isRecord(row0) ? row0 : {}
  if (row.ok !== true) return { icon: "→", label: "Trend n/d", tone: "zinc" as const }

  const dAcc = Number(row.delta_accuracy ?? NaN)
  const dEce = Number(row.delta_ece ?? NaN)
  if (!Number.isFinite(dAcc) || !Number.isFinite(dEce)) return { icon: "→", label: "Trend n/d", tone: "zinc" as const }

  const good = dAcc >= 0.02 && dEce <= -0.01
  const bad = dAcc <= -0.02 && dEce >= 0.01

  if (good) return { icon: "↑", label: "In miglioramento", tone: "green" as const }
  if (bad) return { icon: "↓", label: "In peggioramento", tone: "red" as const }
  return { icon: "→", label: "Stabile", tone: "yellow" as const }
}

function pillClass(tone: "green" | "yellow" | "red" | "zinc") {
  if (tone === "green") return "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
  if (tone === "yellow") return "border-amber-500/20 bg-amber-500/15 text-amber-700 dark:text-amber-300"
  if (tone === "red") return "border-red-500/20 bg-red-500/15 text-red-700 dark:text-red-300"
  return "border-zinc-500/20 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null
}

export function LeaguePerformanceTable({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [rows, setRows] = useState<Row[]>([])
  const [trends, setTrends] = useState<Record<string, unknown>>({})
  const [loading, setLoading] = useState<boolean>(false)
  const [err, setErr] = useState<string | null>(null)

  const [query, setQuery] = useState<string>("")
  const [sortKey, setSortKey] = useState<SortKey>("ece")
  const [sortDir, setSortDir] = useState<SortDir>("asc")
  const [open, setOpen] = useState<boolean>(defaultOpen)

  useEffect(() => setOpen(defaultOpen), [defaultOpen])

  useEffect(() => {
    let alive = true
    async function load() {
      setLoading(true)
      setErr(null)
      try {
        const fetchMetrics = async () => {
          let res = await apiFetchTenant("/api/backtest-metrics", { cache: "default" })
          if (!res.ok) res = await apiFetchTenant("/api/v1/backtest-metrics", { cache: "default" })
          if (!res.ok) throw new Error(`backtest_metrics_failed:${res.status}`)
          return (await res.json()) as unknown
        }

        const fetchTrends = async () => {
          let res = await apiFetchTenant("/api/backtest-trends", { cache: "default" })
          if (!res.ok) res = await apiFetchTenant("/api/v1/backtest-trends", { cache: "default" })
          if (!res.ok) throw new Error(`backtest_trends_failed:${res.status}`)
          return (await res.json()) as unknown
        }

        const [metricsResult, trendsResult] = await Promise.allSettled([fetchMetrics(), fetchTrends()])
        if (!alive) return

        if (metricsResult.status === "fulfilled") {
          const js = metricsResult.value
          if (!isRecord(js) || js.ok !== true) {
            const msg = isRecord(js) ? String(js.error ?? "fetch_failed") : "fetch_failed"
            setErr(msg)
            setRows([])
          } else {
            const champs0 = js.championships
            const champs = isRecord(champs0) ? champs0 : {}

            const keys = Object.keys(champs)
            const out: Row[] = keys
              .map((championship) => {
                const v = champs[championship]
                const obj = isRecord(v) ? v : {}
                return {
                  championship: String(championship),
                  n: Number(obj.n ?? 0),
                  accuracy: Number(obj.accuracy ?? 0),
                  brier: Number(obj.brier ?? 0),
                  logloss: Number(obj.log_loss ?? obj.logloss ?? 0),
                  ece: Number(obj.ece ?? 0),
                }
              })
              .filter((r) => r.championship)
            setRows(out)
          }
        } else {
          setErr("fetch_failed")
          setRows([])
        }

        if (trendsResult.status === "fulfilled") {
          const tJs = trendsResult.value
          if (isRecord(tJs) && tJs.ok === true && isRecord(tJs.championships)) setTrends(tJs.championships)
        }
      } catch {
        if (!alive) return
        setErr("fetch_failed")
        setRows([])
      } finally {
        if (!alive) return
        setLoading(false)
      }
    }

    load()
    const id = window.setInterval(load, 120_000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const base = q ? rows.filter((r) => r.championship.toLowerCase().includes(q)) : rows.slice()

    base.sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      const dir = sortDir === "asc" ? 1 : -1
      if (typeof av === "number" && typeof bv === "number") return dir * (av - bv)
      return dir * String(av).localeCompare(String(bv))
    })

    return base
  }, [query, rows, sortDir, sortKey])

  function toggleSort(k: SortKey) {
    if (k === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(k)
      if (k === "accuracy") setSortDir("desc")
      else if (k === "championship") setSortDir("asc")
      else setSortDir("asc")
    }
  }

  return (
    <div className="mt-4 rounded-3xl border border-white/10 bg-white/10 p-4 dark:bg-zinc-950/20">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Performance per campionato</div>
          <div className="text-xs text-zinc-600 dark:text-zinc-300">
            Accuracy/Brier/LogLoss/ECE (finestra recente). Serve per capire se un campionato è “affidabile”.
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="rounded-full border border-white/10 bg-white/10 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
          >
            {open ? "Nascondi" : "Mostra"}
          </button>
        </div>
      </div>

      {open ? (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Cerca campionato… (es. serie_a)"
              className="w-full max-w-sm rounded-2xl border border-white/10 bg-white/10 px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-500 outline-none dark:bg-zinc-950/25 dark:text-zinc-50"
            />
            {loading ? <span className="text-xs text-zinc-600 dark:text-zinc-300">Caricamento…</span> : null}
            {err ? <span className="text-xs text-red-700 dark:text-red-300">Errore: {err}</span> : null}
          </div>

          <div className="mt-3 overflow-auto rounded-2xl border border-white/10">
            <table className="min-w-[860px] w-full text-left text-sm">
              <thead className="bg-white/10 dark:bg-zinc-950/30">
                <tr className="text-xs text-zinc-700 dark:text-zinc-200">
                  <th className="px-3 py-2 cursor-pointer" onClick={() => toggleSort("championship")}>
                    Campionato
                  </th>
                  <th className="px-3 py-2 cursor-pointer" onClick={() => toggleSort("n")}>
                    N
                  </th>
                  <th className="px-3 py-2 cursor-pointer" onClick={() => toggleSort("accuracy")}>
                    Accuracy
                  </th>
                  <th className="px-3 py-2 cursor-pointer" onClick={() => toggleSort("brier")}>
                    Brier
                  </th>
                  <th className="px-3 py-2 cursor-pointer" onClick={() => toggleSort("logloss")}>
                    LogLoss
                  </th>
                  <th className="px-3 py-2 cursor-pointer" onClick={() => toggleSort("ece")}>
                    ECE
                  </th>
                  <th className="px-3 py-2">Stato</th>
                  <th className="px-3 py-2">Trend</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {filtered.map((r) => {
                  const rel = reliabilityLabel(r)
                  const tr = trendBadge(r.championship, trends)
                  return (
                    <tr key={r.championship} className="hover:bg-white/5">
                      <td className="px-3 py-2 font-semibold text-zinc-900 dark:text-zinc-50">{r.championship}</td>
                      <td className="px-3 py-2 text-zinc-700 dark:text-zinc-200">{Number.isFinite(r.n) ? r.n : "n/d"}</td>
                      <td className="px-3 py-2 text-zinc-700 dark:text-zinc-200">{fmtPct(r.accuracy)}</td>
                      <td className="px-3 py-2 text-zinc-700 dark:text-zinc-200">{fmt3(r.brier)}</td>
                      <td className="px-3 py-2 text-zinc-700 dark:text-zinc-200">{fmt3(r.logloss)}</td>
                      <td className="px-3 py-2 text-zinc-700 dark:text-zinc-200">{fmt3(r.ece)}</td>
                      <td className="px-3 py-2">
                        {rel.label !== "n/d" ? (
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(rel.tone)}`}>{rel.label}</span>
                        ) : (
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass("zinc")}`}>n/d</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pillClass(
                            tr.tone === "green" ? "green" : tr.tone === "yellow" ? "yellow" : tr.tone === "red" ? "red" : "zinc"
                          )}`}
                        >
                          {tr.icon} {tr.label}
                        </span>
                      </td>
                    </tr>
                  )
                })}
                {!filtered.length && !loading ? (
                  <tr>
                    <td className="px-3 py-6 text-zinc-600 dark:text-zinc-300" colSpan={8}>
                      Nessun dato disponibile (o filtro troppo restrittivo).
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-300">
            Suggerimento: ordina per <span className="font-semibold">ECE</span> (più basso = meglio) e poi guarda Accuracy.
          </div>
        </>
      ) : null}
    </div>
  )
}
