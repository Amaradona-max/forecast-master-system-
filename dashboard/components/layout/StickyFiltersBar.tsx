"use client"

import React from "react"

export function StickyFiltersBar({
  left,
  right,
  bottom
}: {
  left?: React.ReactNode
  right?: React.ReactNode
  bottom?: React.ReactNode
}) {
  return (
    <div className="sticky top-[72px] z-20 -mx-4 px-4 md:static md:mx-0 md:px-0">
      <div className="rounded-2xl border border-white/10 bg-white/80 p-2 shadow-soft backdrop-blur-md dark:bg-zinc-950/60">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">{left}</div>
          <div className="flex items-center gap-2">{right}</div>
        </div>

        {bottom ? <div className="mt-2">{bottom}</div> : null}
      </div>
    </div>
  )
}
