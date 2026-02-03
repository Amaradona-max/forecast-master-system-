"use client"

import { useMemo } from "react"
import { Card } from "@/components/widgets/Card"

type ExplainPayload = {
  decision_gate?: { confidence_tier?: unknown; warnings?: unknown }
  ev?: { best?: { ev?: unknown } }
  similar_reliability_pct?: unknown
  chaos?: { index?: unknown }
}

function safeNum(x: unknown): number | null {
  const n = Number(x)
  return Number.isFinite(n) ? n : null
}

function getExplain(m: unknown): ExplainPayload {
  const e = (m as { explain?: unknown } | null | undefined)?.explain
  return e && typeof e === "object" ? (e as ExplainPayload) : {}
}

export function BentoKpiHeader({
  matches,
  bestCount,
  topCount
}: {
  matches: unknown[]
  bestCount?: number
  topCount?: number
}) {
  const metrics = useMemo(() => {
    let tierS = 0
    let tierA = 0
    let evPos = 0
    let driftFlags = 0
    let simSum = 0
    let simN = 0
    let chaosSum = 0
    let chaosN = 0

    for (const m of matches || []) {
      const ex = getExplain(m)
      const dg = ex.decision_gate
      const tier = dg?.confidence_tier ? String(dg.confidence_tier) : null
      if (tier === "S") tierS++
      if (tier === "A") tierA++

      const ev = ex.ev?.best?.ev
      const evn = safeNum(ev)
      if (evn !== null && evn > 0) evPos++

      const warns = dg?.warnings
      if (Array.isArray(warns) && warns.some((w) => /drift/i.test(String(w)))) driftFlags++

      const sim = safeNum(ex.similar_reliability_pct)
      if (sim !== null && sim > 0) {
        simSum += sim
        simN++
      }

      const chaosIdx = safeNum(ex.chaos?.index)
      if (chaosIdx !== null) {
        chaosSum += chaosIdx
        chaosN++
      }
    }

    const simAvg = simN ? simSum / simN : null
    const chaosAvg = chaosN ? chaosSum / chaosN : null

    return {
      tierS,
      tierA,
      evPos,
      driftFlags,
      simAvg,
      chaosAvg
    }
  }, [matches])

  const kpi = [
    {
      title: "Top Picks",
      value: `${bestCount ?? 0} / ${topCount ?? 0}`,
      hint: "Best / Top nel filtro attuale",
      tone: "from-indigo-500/20 via-cyan-500/10 to-fuchsia-500/10"
    },
    {
      title: "Tier Elite",
      value: `S ${metrics.tierS} · A ${metrics.tierA}`,
      hint: "Conteggio Tier (Decision Gate)",
      tone: "from-emerald-500/20 via-cyan-500/10 to-indigo-500/10"
    },
    {
      title: "EV+",
      value: String(metrics.evPos),
      hint: "Match con Expected Value positivo (se quote presenti)",
      tone: "from-emerald-500/18 via-emerald-500/8 to-zinc-500/0"
    },
    {
      title: "Drift",
      value: String(metrics.driftFlags),
      hint: "Match con warning Drift (confidenza ridotta)",
      tone: "from-amber-500/18 via-amber-500/8 to-zinc-500/0"
    },
    {
      title: "Simili",
      value: metrics.simAvg !== null ? `${Math.round(metrics.simAvg)}%` : "—",
      hint: "Accuratezza media sui bucket 'match simili'",
      tone: "from-zinc-500/10 via-indigo-500/10 to-cyan-500/10"
    },
    {
      title: "Caos",
      value: metrics.chaosAvg !== null ? `${Math.round(metrics.chaosAvg)}` : "—",
      hint: "Indice medio (0–100) nel filtro attuale",
      tone: "from-fuchsia-500/12 via-zinc-500/0 to-cyan-500/12"
    }
  ]

  return (
    <div className="bento-grid">
      {kpi.map((x) => (
        <Card key={x.title} className={`bento-col-4 bg-gradient-to-br ${x.tone} p-0`}>
          <div className="p-4">
            <div className="text-[11px] font-bold uppercase tracking-wide text-zinc-600 dark:text-zinc-300">{x.title}</div>
            <div className="mt-1 text-2xl font-black text-zinc-900 dark:text-zinc-50">{x.value}</div>
            <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">{x.hint}</div>
          </div>
        </Card>
      ))}
    </div>
  )
}
