"use client"

export function HighConfidenceToggle({
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
          ? "border-sky-500/20 bg-sky-500/15 text-sky-700 dark:text-sky-300"
          : "border-white/10 bg-white/10 text-zinc-700 hover:bg-white/15 dark:bg-zinc-950/25 dark:text-zinc-200",
        className ?? ""
      ].join(" ")}
      aria-pressed={value}
      title="Mostra solo match con confidenza alta"
    >
      <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-bold">HC</span>
      <span>High Conf</span>
    </button>
  )
}
