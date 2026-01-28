"use client"

import React from "react"

type Density = "comfort" | "compact"

export function DensityToggle({
  value,
  onChange,
  className
}: {
  value: Density
  onChange: (v: Density) => void
  className?: string
}) {
  const isComfort = value === "comfort"
  return (
    <div
      className={[
        "flex items-center gap-1 rounded-full border border-white/10 bg-white/10 p-1 shadow-sm backdrop-blur-md dark:bg-zinc-950/20",
        className ?? ""
      ].join(" ")}
      role="group"
      aria-label="Densità layout"
    >
      <button
        type="button"
        onClick={() => onChange("comfort")}
        className={[
          "rounded-full px-3 py-1.5 text-[11px] font-semibold transition",
          isComfort
            ? "bg-white/30 text-zinc-900 dark:bg-white/10 dark:text-zinc-50"
            : "text-zinc-700 hover:bg-white/15 dark:text-zinc-200"
        ].join(" ")}
        aria-pressed={isComfort}
      >
        Comfort
      </button>
      <button
        type="button"
        onClick={() => onChange("compact")}
        className={[
          "rounded-full px-3 py-1.5 text-[11px] font-semibold transition",
          !isComfort
            ? "bg-white/30 text-zinc-900 dark:bg-white/10 dark:text-zinc-50"
            : "text-zinc-700 hover:bg-white/15 dark:text-zinc-200"
        ].join(" ")}
        aria-pressed={!isComfort}
      >
        Compact
      </button>
    </div>
  )
}
