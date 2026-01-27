import { PropsWithChildren } from "react"

export function Card({ children, className }: PropsWithChildren<{ className?: string }>) {
  return (
    <div
      className={[
        "group rounded-3xl border border-white/20 bg-white/70 p-5 shadow-soft backdrop-blur-xl transition-all duration-300 hover:shadow-medium dark:border-white/10 dark:bg-zinc-900/60 animate-fade-in",
        className ?? ""
      ].join(" ")}
    >
      {children}
    </div>
  )
}
