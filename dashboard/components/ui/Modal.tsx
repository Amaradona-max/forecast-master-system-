"use client"

import React from "react"

export function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
}) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-[70]">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden="true" />
      <div className="absolute inset-x-0 bottom-0 mx-auto max-h-[85vh] w-full max-w-3xl overflow-auto rounded-t-3xl border border-white/10 bg-white/90 p-4 shadow-2xl backdrop-blur-md dark:bg-zinc-950/90 md:inset-y-10 md:bottom-auto md:rounded-3xl">
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-semibold tracking-tight">{title}</div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-white/10 bg-white/10 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200"
          >
            Chiudi
          </button>
        </div>
        <div className="mt-3">{children}</div>
      </div>
    </div>
  )
}

