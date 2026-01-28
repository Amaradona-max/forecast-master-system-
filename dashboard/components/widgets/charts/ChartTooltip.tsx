"use client"

import type { TooltipProps } from "recharts"
import React from "react"

type RechartsValue = string | number | Array<string | number>

export function GlassTooltip({
  active,
  payload,
  label,
  labelFormatter
}: TooltipProps<RechartsValue, string> & { labelFormatter?: (label: unknown) => string }) {
  if (!active || !payload?.length) return null

  const labelText = labelFormatter ? labelFormatter(label) : String(label ?? "")
  return (
    <div className="rounded-2xl border border-white/10 bg-white/85 px-3 py-2 text-xs shadow-soft backdrop-blur-md dark:bg-zinc-950/55">
      {labelText ? (
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
          {labelText}
        </div>
      ) : null}
      <div className="space-y-1">
        {payload.map((p, idx) => (
          <div key={`${p.name ?? "v"}-${idx}`} className="flex items-center justify-between gap-4">
            <span className="truncate text-zinc-700 dark:text-zinc-200">{String(p.name ?? "")}</span>
            <span className="num font-bold text-zinc-900 dark:text-zinc-50">{String(p.value ?? "")}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
