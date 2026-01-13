"use client"

import { useEffect, useMemo, useState } from "react"

import type { MatchUpdate } from "@/components/api/types"
import { apiUrl } from "@/components/api/client"
import { Card } from "@/components/widgets/Card"

export function TopMatchHighlight() {
  const [matches, setMatches] = useState<Record<string, MatchUpdate>>({})

  useEffect(() => {
    const ws = new WebSocket(apiUrl("/ws/live-updates").replace("http://", "ws://").replace("https://", "wss://"))
    ws.onmessage = (ev: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(ev.data as string)
        if (msg?.type === "match_update" && msg.payload?.match_id) {
          const upd = msg.payload as MatchUpdate
          setMatches((prev: Record<string, MatchUpdate>) => ({ ...prev, [upd.match_id]: upd }))
        }
      } catch {}
    }
    return () => {
      try {
        ws.close()
      } catch {}
    }
  }, [])

  const top = useMemo(() => {
    const list = (Object.values(matches) as MatchUpdate[])
      .map((m: MatchUpdate) => {
        return {
          ...m,
          best: Math.max(m.probabilities.home_win, m.probabilities.draw, m.probabilities.away_win)
        }
      })
      .filter((m: MatchUpdate & { best: number }) => m.best >= 0.7)
      .sort((a: MatchUpdate & { best: number }, b: MatchUpdate & { best: number }) => b.best - a.best)
    return list.slice(0, 6)
  }, [matches])

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold tracking-tight">Top Match</div>
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Solo confidence ≥ 70%</div>
        </div>
        <div className="rounded-full border border-zinc-200/70 bg-white/60 px-2 py-1 text-[11px] text-zinc-700 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-900/50 dark:text-zinc-200">
          Live
        </div>
      </div>
      {top.length ? (
        <div className="mt-4 space-y-2">
          {top.map((m: MatchUpdate & { best: number }) => (
            <div
              key={m.match_id}
              className="flex items-center justify-between gap-3 rounded-2xl border border-zinc-200/70 bg-white/55 px-3 py-2 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-900/35"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">
                  {m.home_team} - {m.away_team}
                </div>
                <div className="text-xs text-zinc-600 dark:text-zinc-300">{m.championship}</div>
              </div>
              <div className="shrink-0">
                <div className="text-right text-sm font-semibold">{Math.round(m.best * 100)}%</div>
                <div className="mt-1 h-1.5 w-20 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                  <div
                    className="h-1.5 bg-[linear-gradient(90deg,#10b981,#3b82f6)]"
                    style={{ width: `${Math.round(m.best * 100)}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-4 text-sm text-zinc-600 dark:text-zinc-300">Nessuna partita sopra soglia al momento.</div>
      )}
    </Card>
  )
}
