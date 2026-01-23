"use client"

import { useState } from "react"

import { ThemeToggle } from "@/components/theme/ThemeToggle"
import { Modal } from "@/components/ui/Modal"
import { ChampionshipComparator } from "@/components/widgets/ChampionshipComparator"
import { LiveMatchCenter } from "@/components/widgets/LiveMatchCenter"
import { PredictionAccuracyTracker } from "@/components/widgets/PredictionAccuracyTracker"
import { StatisticalPredictionsDashboard } from "@/components/widgets/StatisticalPredictionsDashboard"

type Section = "pred" | "live" | "acc" | "compare"

const sections: { key: Section; label: string }[] = [
  { key: "pred", label: "Previsioni" },
  { key: "live", label: "Live" },
  { key: "acc", label: "Accuracy" },
  { key: "compare", label: "Confronto" }
]

export function ResponsiveShell() {
  const [active, setActive] = useState<Section>("pred")
  const [collapsed, setCollapsed] = useState(false)
  const [legendOpen, setLegendOpen] = useState(false)
  const [howToOpen, setHowToOpen] = useState(false)

  const Content = () => {
    if (active === "pred") return <StatisticalPredictionsDashboard />
    if (active === "live") return <LiveMatchCenter />
    if (active === "acc") return <PredictionAccuracyTracker />
    return <ChampionshipComparator />
  }

  return (
    <div className="flex min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <div className="fixed right-3 top-3 z-[60] md:right-6 md:top-4">
        <ThemeToggle />
      </div>
      <aside
        className={`hidden md:flex flex-col border-r border-white/10 bg-white/60 dark:bg-zinc-950/60 backdrop-blur-md transition-all ${
          collapsed ? "w-[72px]" : "w-64"
        }`}
      >
        <div className="flex items-center justify-between px-4 py-3">
          <div className="text-sm font-bold truncate">{collapsed ? "FM" : "Forecast Master"}</div>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            {collapsed ? "›" : "‹"}
          </button>
        </div>

        <nav className="flex-1 space-y-1 px-2">
          {sections.map((s) => {
            const activeItem = active === s.key
            return (
              <button
                key={s.key}
                onClick={() => setActive(s.key)}
                className={[
                  "w-full rounded-xl px-3 py-2 text-left text-sm font-medium transition",
                  activeItem
                    ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-900"
                ].join(" ")}
              >
                {collapsed ? s.label[0] : s.label}
              </button>
            )
          })}

          <button
            type="button"
            disabled
            className={[
              "mt-3 w-full cursor-not-allowed rounded-xl px-3 py-2 text-left text-sm font-medium transition opacity-70",
              "text-zinc-600 dark:text-zinc-300"
            ].join(" ")}
          >
            {collapsed ? "C" : "Controllo"}
          </button>

          <button
            type="button"
            onClick={() => setLegendOpen(true)}
            className={[
              "w-full rounded-xl px-3 py-2 text-left text-sm font-medium transition",
              "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-900"
            ].join(" ")}
          >
            {collapsed ? "L" : "Legenda"}
          </button>

          <button
            type="button"
            onClick={() => setHowToOpen(true)}
            className={[
              "w-full rounded-xl px-3 py-2 text-left text-sm font-medium transition",
              "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-900"
            ].join(" ")}
          >
            {collapsed ? "?" : "Come usare l'App"}
          </button>
        </nav>
      </aside>

      <main className="flex-1 px-4 py-4 md:px-6 md:py-6">
        <Content />
      </main>

      <Modal open={legendOpen} title="Legenda" onClose={() => setLegendOpen(false)}>
        <div className="space-y-3">
          <div className="rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
            <div className="text-xs font-bold text-zinc-700 dark:text-zinc-200">Qualità</div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-700 dark:text-zinc-200">
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
                A
              </span>
              <span className="rounded-full border border-sky-500/20 bg-sky-500/15 px-2 py-0.5 text-[10px] font-bold text-sky-700 dark:text-sky-300">
                B
              </span>
              <span className="rounded-full border border-amber-500/20 bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                C
              </span>
              <span className="rounded-full border border-red-500/20 bg-red-500/15 px-2 py-0.5 text-[10px] font-bold text-red-700 dark:text-red-300">
                D
              </span>
            </div>
            <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-300">
              Quality grade (A→D): sintetizza probabilità e confidence. A/B sono le più affidabili, D indica segnali deboli.
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
            <div className="text-xs font-bold text-zinc-700 dark:text-zinc-200">Rischio</div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-700 dark:text-zinc-200">
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
                Basso
              </span>
              <span className="rounded-full border border-amber-500/20 bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                Medio
              </span>
              <span className="rounded-full border border-red-500/20 bg-red-500/15 px-2 py-0.5 text-[10px] font-bold text-red-700 dark:text-red-300">
                Alto
              </span>
            </div>
            <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-300">
              Risk (Basso/Medio/Alto): aumenta quando segnali (probabilità/confidence) non sono allineati.
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
            <div className="text-xs font-bold text-zinc-700 dark:text-zinc-200">Badge</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="rounded-full border border-red-500/20 bg-red-500/15 px-2 py-0.5 text-[10px] font-bold text-red-700 dark:text-red-300">
                LIVE
              </span>
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
                TOP
              </span>
              <span className="rounded-full border border-sky-500/20 bg-sky-500/15 px-2 py-0.5 text-[10px] font-bold text-sky-700 dark:text-sky-300">
                CONF
              </span>
              <span className="rounded-full border border-zinc-500/20 bg-zinc-500/10 px-2 py-0.5 text-[10px] font-bold text-zinc-700 dark:text-zinc-300">
                NO BET
              </span>
              <span className="rounded-full border border-white/10 bg-white/10 px-2 py-0.5 text-[10px] font-bold text-zinc-700 dark:text-zinc-200">
                +30m
              </span>
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
                AFFIDABILE
              </span>
              <span className="rounded-full border border-amber-500/20 bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                MEDIO
              </span>
              <span className="rounded-full border border-rose-500/20 bg-rose-500/15 px-2 py-0.5 text-[10px] font-bold text-rose-700 dark:text-rose-300">
                INSTABILE
              </span>
              <span className="rounded-full border border-sky-500/20 bg-sky-500/15 px-2 py-0.5 text-[10px] font-bold text-sky-700 dark:text-sky-300">
                CHAOS
              </span>
              <span className="rounded-full border border-amber-500/20 bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                CHAOS↑
              </span>
              <span className="rounded-full border border-red-500/20 bg-red-500/15 px-2 py-0.5 text-[10px] font-bold text-red-700 dark:text-red-300">
                CHAOS🔥
              </span>
              <span className="rounded-full border border-red-500/20 bg-red-500/15 px-2 py-0.5 text-[10px] font-bold text-red-700 dark:text-red-300">
                UPSET
              </span>
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-300">
                ↑
              </span>
              <span className="rounded-full border border-amber-500/20 bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                →
              </span>
              <span className="rounded-full border border-rose-500/20 bg-rose-500/15 px-2 py-0.5 text-[10px] font-bold text-rose-700 dark:text-rose-300">
                ↓
              </span>
            </div>
            <div className="mt-2 space-y-1 text-xs text-zinc-600 dark:text-zinc-300">
              <div>LIVE: partita in corso.</div>
              <div>TOP: probabilità massima elevata.</div>
              <div>CONF: confidence alta.</div>
              <div>NO BET: segnali insufficienti o rischio troppo alto.</div>
              <div>+Xm / +Xh: inizio imminente.</div>
              <div>AFFIDABILE / MEDIO / INSTABILE: indicatore sintetico di affidabilità/stabilità del segnale.</div>
              <div>↑ / → / ↓: trend recente dell’affidabilità.</div>
              <div>CHAOS / CHAOS↑ / CHAOS🔥: volatilità del match (più alto = più imprevedibile).</div>
              <div>UPSET: possibile sorpresa (attenzione al rischio).</div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/10 p-3 dark:bg-zinc-950/20">
            <div className="text-xs font-bold text-zinc-700 dark:text-zinc-200">Termini (Home)</div>
            <div className="mt-2 space-y-1 text-xs text-zinc-600 dark:text-zinc-300">
              <div>Confidence (HIGH/MEDIUM/LOW): livello di affidabilità stimato dal modello.</div>
              <div>Kickoff: orario di inizio partita.</div>
              <div>Bankroll: capitale di riferimento (slider). u = unità; es. 100u.</div>
              <div>Stake: puntata consigliata in unità (u) e in percentuale del bankroll.</div>
              <div>Educational only: modalità informativa (non è un invito a scommettere).</div>
              <div>n/d: dato non disponibile.</div>
              <div>1X2: mercato esito finale (1 = casa, X = pareggio, 2 = trasferta).</div>
              <div>BTTS: Both Teams To Score (entrambe le squadre segnano).</div>
              <div>Over 2.5: totale gol maggiore di 2.5.</div>
              <div>Chaos index: indice (0–100) di volatilità del match.</div>
              <div>W/D/L: forma recente (W vittoria, D pareggio, L sconfitta).</div>
              <div>Track Record / Track: storico prestazioni del modello nel periodo selezionato.</div>
              <div>Acc: accuracy (percentuale di pronostici corretti).</div>
              <div>ROI (avg/tot): ritorno simulato medio/totale (metrica tecnica).</div>
              <div>ROC-AUC: indicatore di separazione del modello (più alto = meglio).</div>
              <div>N: numero di match usati nelle statistiche mostrate.</div>
              <div>PIN: fissa un preferito in alto (max 3).</div>
            </div>
          </div>
        </div>
      </Modal>

      <Modal open={howToOpen} title="Come usare l'App" onClose={() => setHowToOpen(false)}>
        <div className="space-y-3">
          <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
            <div className="font-semibold text-zinc-900 dark:text-zinc-50">1) Scegli la sezione</div>
            <div className="mt-1 space-y-1 text-zinc-600 dark:text-zinc-300">
              <div>Previsioni: lista partite con probabilità, qualità e consigli.</div>
              <div>Live: monitoraggio in tempo reale (se dati disponibili).</div>
              <div>Accuracy: andamento e performance del modello.</div>
              <div>Confronto: confronto rapido tra leghe.</div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
            <div className="font-semibold text-zinc-900 dark:text-zinc-50">2) In Previsioni, imposta campionato e giornata</div>
            <div className="mt-1 space-y-1 text-zinc-600 dark:text-zinc-300">
              <div>In alto seleziona il campionato (es. Serie A, Premier…).</div>
              <div>Seleziona la giornata dal menu (quando disponibile).</div>
              <div>Usa “Ordina” per vedere prima probabilità, confidence o orario.</div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
            <div className="font-semibold text-zinc-900 dark:text-zinc-50">3) Scegli il profilo</div>
            <div className="mt-1 space-y-1 text-zinc-600 dark:text-zinc-300">
              <div>Prudente: mostra solo match con confidence alta e rischio basso.</div>
              <div>Bilanciato: filtra i match più “ragionevoli” (default).</div>
              <div>Aggressivo: include anche match più rischiosi.</div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
            <div className="font-semibold text-zinc-900 dark:text-zinc-50">4) Usa i filtri per trovare i match giusti</div>
            <div className="mt-1 space-y-1 text-zinc-600 dark:text-zinc-300">
              <div>Cerca squadra: digita il nome (es. Inter, Milan…).</div>
              <div>Solo Qualità A/B: mostra solo le partite più affidabili.</div>
              <div>Nascondi NO BET: nasconde i match con segnali deboli.</div>
              <div>Se non vedi nulla, premi “Reset filtri”.</div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
            <div className="font-semibold text-zinc-900 dark:text-zinc-50">5) Apri i dettagli e salva i preferiti</div>
            <div className="mt-1 space-y-1 text-zinc-600 dark:text-zinc-300">
              <div>Apri una partita per vedere mercati, motivazioni e rischi.</div>
              <div>Usa ☆ per aggiungere ai Preferiti e PIN per fissare in alto.</div>
              <div>Usa “Dettagli” per il riepilogo completo della partita.</div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/10 p-3 text-xs text-zinc-700 dark:bg-zinc-950/20 dark:text-zinc-200">
            <div className="font-semibold text-zinc-900 dark:text-zinc-50">6) Legenda e lettura veloce</div>
            <div className="mt-1 space-y-1 text-zinc-600 dark:text-zinc-300">
              <div>Apri “Legenda” per capire badge (LIVE, TOP, CONF, NO BET, CHAOS, UPSET) e livelli.</div>
              <div>Apri “Chaos Leaderboard” per vedere le 10 gare più imprevedibili e aprire il “Perché”.</div>
              <div>Qualità (A→D) riassume probabilità e confidence.</div>
              <div>Rischio (Basso/Medio/Alto) indica quanto è “solido” il segnale.</div>
            </div>
          </div>
        </div>
      </Modal>

      <nav className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around border-t border-white/10 bg-white/80 backdrop-blur-md dark:bg-zinc-950/80 md:hidden">
        {sections.map((s) => {
          const activeItem = active === s.key
          return (
            <button
              key={s.key}
              onClick={() => setActive(s.key)}
              className={[
                "flex flex-col items-center gap-1 py-2 text-xs font-medium transition",
                activeItem ? "text-emerald-600 dark:text-emerald-400" : "text-zinc-500 dark:text-zinc-400"
              ].join(" ")}
            >
              {s.label}
            </button>
          )
        })}
      </nav>
    </div>
  )
}
