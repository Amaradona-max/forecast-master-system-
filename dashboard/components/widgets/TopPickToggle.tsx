"use client"

export function TopPickToggle({
  value,
  onChange,
  className
}: {
  value: boolean
  onChange: (v: boolean) => void
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      className={[
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold shadow-sm transition",
        value
          ? "border-emerald-500/20 bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
          : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200",
        className ?? ""
      ].join(" ")}
      aria-pressed={value}
      title="Mostra solo match con fragility bassa"
    >
      <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-bold">TOP</span>
      <span>TOP Picks</span>
    </button>
  )
}
