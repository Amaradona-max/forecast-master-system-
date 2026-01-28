"use client"

import React from "react"

function clamp01(x: number) {
  if (Number.isNaN(x)) return 0
  return x < 0 ? 0 : x > 1 ? 1 : x
}

function fmtPct01(x: number) {
  return `${Math.round(clamp01(x) * 100)}%`
}

type Props = {
  p1: number
  px: number
  p2: number
  className?: string
  compact?: boolean
}

export const PredictionBar = React.memo(function PredictionBar({ p1, px, p2, className, compact }: Props) {
  const a = clamp01(Number(p1))
  const b = clamp01(Number(px))
  const c = clamp01(Number(p2))
  const sum = a + b + c || 1

  const w1 = (a / sum) * 100
  const wx = (b / sum) * 100
  const w2 = (c / sum) * 100

  const labelSize = compact ? "text-[11px]" : "text-xs"
  const barH = compact ? "h-9" : "h-10"

  return (
    <div className={className}>
      <div
        className={`overflow-hidden rounded-2xl border border-white/10 bg-white/10 shadow-sm backdrop-blur-md dark:bg-zinc-950/25 ${barH}`}
        role="img"
        aria-label={`Probabilità 1X2: 1 ${fmtPct01(a)}, X ${fmtPct01(b)}, 2 ${fmtPct01(c)}`}
      >
        <div className="flex h-full w-full">
          <div
            className="flex h-full items-center justify-between gap-2 bg-emerald-500/18 px-3 text-emerald-950 dark:text-emerald-200"
            style={{ width: `${w1}%` }}
            title={`1 (Casa): ${fmtPct01(a)}`}
          >
            <span className={`font-extrabold ${labelSize}`}>1</span>
            <span className={`num font-extrabold ${labelSize}`}>{fmtPct01(a)}</span>
          </div>

          <div
            className="flex h-full items-center justify-between gap-2 bg-sky-500/14 px-3 text-sky-950 dark:text-sky-200"
            style={{ width: `${wx}%` }}
            title={`X (Pareggio): ${fmtPct01(b)}`}
          >
            <span className={`font-extrabold ${labelSize}`}>X</span>
            <span className={`num font-extrabold ${labelSize}`}>{fmtPct01(b)}</span>
          </div>

          <div
            className="flex h-full items-center justify-between gap-2 bg-violet-500/14 px-3 text-violet-950 dark:text-violet-200"
            style={{ width: `${w2}%` }}
            title={`2 (Trasferta): ${fmtPct01(c)}`}
          >
            <span className={`font-extrabold ${labelSize}`}>2</span>
            <span className={`num font-extrabold ${labelSize}`}>{fmtPct01(c)}</span>
          </div>
        </div>
      </div>

      <div className="mt-1 flex items-center justify-between text-[11px] text-zinc-600 dark:text-zinc-300">
        <span className="num">
          {Math.round(a * 100)} / {Math.round(b * 100)} / {Math.round(c * 100)}
        </span>
        <span className="opacity-80">1 · X · 2</span>
      </div>
    </div>
  )
})
