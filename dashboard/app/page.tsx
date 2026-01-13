import { ThemeToggle } from "@/components/theme/ThemeToggle"
import { StatisticalPredictionsDashboard } from "@/components/widgets/StatisticalPredictionsDashboard"

export default function HomePage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <div className="flex justify-end">
        <ThemeToggle />
      </div>
      <div className="mt-4">
        <StatisticalPredictionsDashboard />
      </div>
    </main>
  )
}
