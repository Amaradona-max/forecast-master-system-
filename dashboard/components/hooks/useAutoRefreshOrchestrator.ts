"use client"

import { useEffect, useMemo, useRef, useState } from "react"

type MatchStatus = "PREMATCH" | "LIVE" | "FINISHED" | string

type UpdateFrequencies = {
  pre_match: number[]
  in_match: number
  post_match: number[]
}

const defaultFreq: UpdateFrequencies = {
  pre_match: [24 * 3600, 12 * 3600, 6 * 3600, 3600],
  in_match: 30,
  post_match: [0, 3600]
}

export function useAutoRefreshOrchestrator(status: MatchStatus, kickoffUnix?: number | null) {
  const [tick, setTick] = useState(0)
  const timer = useRef<number | null>(null)

  const intervalSeconds = useMemo(() => {
    if (status === "LIVE") return defaultFreq.in_match
    if (status === "FINISHED") return defaultFreq.post_match[1]
    const now = Date.now() / 1000
    if (kickoffUnix && kickoffUnix > now) {
      const delta = kickoffUnix - now
      const thresholds = defaultFreq.pre_match
      const nearest = thresholds.reduce((acc, t) => (Math.abs(delta - t) < Math.abs(delta - acc) ? t : acc), thresholds[0])
      return Math.max(10, Math.min(nearest / 12, 900))
    }
    return 60
  }, [kickoffUnix, status])

  useEffect(() => {
    if (timer.current) window.clearInterval(timer.current)
    timer.current = window.setInterval(() => setTick((t: number) => t + 1), Math.max(5, intervalSeconds) * 1000)
    return () => {
      if (timer.current) window.clearInterval(timer.current)
    }
  }, [intervalSeconds])

  return { tick, intervalSeconds }
}
