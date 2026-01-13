"use client"

import { useEffect, useMemo, useRef, useState } from "react"

import type { MatchUpdate } from "@/components/api/types"
import { apiUrl } from "@/components/api/client"
import { Card } from "@/components/widgets/Card"
import { InsightGenerator } from "@/components/widgets/InsightGenerator"
import { useAutoRefreshOrchestrator } from "@/components/hooks/useAutoRefreshOrchestrator"

function formatPct(x: number) {
  const v = Math.round(x * 100)
  return `${v}%`
}

export function LiveMatchCenter() {
  const [matches, setMatches] = useState<Record<string, MatchUpdate>>({})
  const [selectedId, setSelectedId] = useState<string>("serie_a_001")
  const wsRef = useRef<WebSocket | null>(null)

  const list = useMemo(() => {
    const arr = Object.values(matches) as MatchUpdate[]
    return arr.sort((a: MatchUpdate, b: MatchUpdate) => a.match_id.localeCompare(b.match_id))
  }, [matches])
  const selected = matches[selectedId]
  const { intervalSeconds } = useAutoRefreshOrchestrator(selected?.status ?? "PREMATCH", selected?.kickoff_unix ?? null)

  useEffect(() => {
    const ws = new WebSocket(apiUrl("/ws/live-updates").replace("http://", "ws://").replace("https://", "wss://"))
    wsRef.current = ws

    ws.onmessage = (ev: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(ev.data as string)
        if (msg?.type === "match_update" && msg.payload?.match_id) {
          const upd = msg.payload as MatchUpdate
          setMatches((prev: Record<string, MatchUpdate>) => ({ ...prev, [upd.match_id]: upd }))
        }
      } catch {}
    }

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "subscribe", match_id: selectedId }))
    }

    return () => {
      try {
        ws.close()
      } catch {}
    }
  }, [selectedId])

  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold tracking-tight">Live Match Center</div>
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
            Aggiornamenti live via WebSocket, fallback smart refresh ~{Math.round(intervalSeconds)}s
          </div>
        </div>
        <select
          value={selectedId}
          onChange={(e: { target: { value: string } }) => setSelectedId(e.target.value)}
          className="rounded-xl border border-zinc-200/70 bg-white/70 px-3 py-2 text-sm shadow-sm backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/40"
        >
          {list.map((m: MatchUpdate) => (
            <option key={m.match_id} value={m.match_id}>
              {m.home_team} - {m.away_team}
            </option>
          ))}
        </select>
      </div>

      {selected ? (
        <div className="mt-4">
          <div className="flex items-center justify-between">
            <div className="text-base font-semibold tracking-tight">
              {selected.home_team} - {selected.away_team}
            </div>
            <div className="text-xs text-zinc-600 dark:text-zinc-300">{selected.status}</div>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
            <Prob label="1" value={selected.probabilities.home_win} />
            <Prob label="X" value={selected.probabilities.draw} />
            <Prob label="2" value={selected.probabilities.away_win} />
          </div>

          <div className="mt-4">
            <InsightGenerator match={selected} />
          </div>
        </div>
      ) : (
        <div className="mt-4 text-sm text-zinc-600 dark:text-zinc-300">In attesa dei dati live…</div>
      )}
    </Card>
  )
}

function Prob({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-zinc-200/70 bg-white/55 p-3 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/25">
      <div className="flex items-center justify-between">
        <div className="text-xs text-zinc-600 dark:text-zinc-300">{label}</div>
        <div className="text-sm font-semibold">{formatPct(value)}</div>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded bg-zinc-200 dark:bg-zinc-800">
        <div
          className="h-2 bg-[linear-gradient(90deg,#10b981,#3b82f6)]"
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
    </div>
  )
}
