"use client"

import React from "react"

export function FragilityThresholdSlider({
  value,
  onChange,
  min = 0.4,
  max = 0.7,
  step = 0.01,
  className,
}: {
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  className?: string
}) {
  const pct = ((value - min) / (max - min)) * 100

  return (
    <div className={["flex items-center gap-3", className ?? ""].join(" ")}>
      <div className="min-w-[86px] text-[11px] font-semibold text-zinc-700 dark:text-zinc-200">
        Soglia <span className="num">{value.toFixed(2)}</span>
      </div>

      <div className="relative w-44">
        <div className="h-2 rounded-full bg-white/10" />
        <div
          className="pointer-events-none absolute left-0 top-0 h-2 rounded-full bg-emerald-500/40"
          style={{ width: `${pct}%` }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="absolute left-0 top-0 h-2 w-full cursor-pointer opacity-0"
          aria-label="Soglia fragility"
        />
      </div>

      <div
        className="hidden sm:block text-[11px] text-zinc-500"
        title="Più basso = più selettivo"
      >
        più basso = più selettivo
      </div>
    </div>
  )
}
