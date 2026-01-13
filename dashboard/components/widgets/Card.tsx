import { PropsWithChildren } from "react"

export function Card({ children, className }: PropsWithChildren<{ className?: string }>) {
  return (
    <div
      className={[
        "rounded-2xl border border-zinc-200/70 bg-white/70 p-4 shadow-sm backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-900/55",
        className ?? ""
      ].join(" ")}
    >
      {children}
    </div>
  )
}
