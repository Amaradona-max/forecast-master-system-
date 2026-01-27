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
    <div className="fixed inset-0 z-[70] animate-fade-in">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
      <div className="absolute inset-x-0 bottom-0 mx-auto max-h-[85vh] w-full max-w-3xl overflow-auto rounded-t-3xl border border-white/20 bg-white/95 p-6 shadow-strong backdrop-blur-2xl dark:border-white/10 dark:bg-zinc-950/95 md:inset-y-10 md:bottom-auto md:rounded-3xl animate-slide-up">
        <div className="flex items-center justify-between gap-3 mb-5">
          <div className="text-lg font-bold tracking-tight text-gradient">{title}</div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-2xl border border-white/20 bg-white/50 px-4 py-2 text-sm font-semibold text-zinc-700 shadow-soft backdrop-blur-md transition-all duration-200 hover:bg-white/70 hover:shadow-medium hover:-translate-y-0.5 dark:bg-zinc-900/50 dark:text-zinc-200 dark:hover:bg-zinc-900/70"
          >
            Chiudi
          </button>
        </div>
        <div className="animate-fade-in">{children}</div>
      </div>
    </div>
  )
}

