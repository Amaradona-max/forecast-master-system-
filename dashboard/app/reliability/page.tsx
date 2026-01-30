import { LeagueReliabilityTable } from "@/components/reliability/LeagueReliabilityTable"
import { ReliabilitySummary } from "@/components/reliability/ReliabilitySummary"

export default function ReliabilityPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Affidabilità & Performance</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
          Monitoraggio calibrazione, drift e qualità predittiva per campionato
        </p>
      </header>

      <ReliabilitySummary />
      <LeagueReliabilityTable />
    </div>
  )
}
