"use client"

type PredictionBarProps = {
  p1: number
  px: number
  p2: number
  compact?: boolean
  showPercentages?: boolean
  className?: string
}

function clamp01(x: number): number {
  if (Number.isNaN(x)) return 0
  return x < 0 ? 0 : x > 1 ? 1 : x
}

export function PredictionBar({
  p1,
  px,
  p2,
  compact = false,
  showPercentages = true,
  className = ""
}: PredictionBarProps) {
  const home = clamp01(p1) * 100
  const draw = clamp01(px) * 100
  const away = clamp01(p2) * 100

  const maxProb = Math.max(home, draw, away)
  const height = compact ? "h-3" : "h-4"

  return (
    <div className={className}>
      {showPercentages && (
        <div className="flex items-center justify-between text-xs sm:text-sm font-semibold">
          <span className={home === maxProb ? "text-accent-emerald" : "text-neutral-600 dark:text-neutral-400"}>
            Casa {home.toFixed(0)}%
          </span>
          <span className={draw === maxProb ? "text-accent-blue" : "text-neutral-600 dark:text-neutral-400"}>
            X {draw.toFixed(0)}%
          </span>
          <span className={away === maxProb ? "text-accent-coral" : "text-neutral-600 dark:text-neutral-400"}>
            Trasferta {away.toFixed(0)}%
          </span>
        </div>
      )}

      <div className={`relative w-full ${height} overflow-hidden rounded-full bg-neutral-200/70 dark:bg-dark-border/70`}>
        <div
          className="absolute left-0 h-full bg-gradient-to-r from-accent-emerald to-pastel-mint transition-all duration-300"
          style={{ width: `${home}%` }}
        />
        <div
          className="absolute h-full bg-gradient-to-r from-accent-blue to-pastel-blue transition-all duration-300"
          style={{ left: `${home}%`, width: `${draw}%` }}
        />
        <div
          className="absolute right-0 h-full bg-gradient-to-r from-pastel-pink to-accent-coral transition-all duration-300"
          style={{ width: `${away}%` }}
        />
      </div>
    </div>
  )
}
