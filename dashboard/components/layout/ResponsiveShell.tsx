"use client"

import Link from "next/link"
import { useState } from "react"

import { StickyFiltersBar } from "@/components/layout/StickyFiltersBar"
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

const sectionMeta: Record<Section, { title: string; subtitle: string; steps: string[] }> = {
  pred: {
    title: "Previsioni Match",
    subtitle: "Vista principale per scegliere match, qualità e rischio con contesto completo.",
    steps: ["Seleziona campionato e giornata", "Valuta qualità e rischio", "Apri dettagli e motivazioni"]
  },
  live: {
    title: "Live Match Center",
    subtitle: "Monitoraggio in tempo reale con insight e indicatori principali.",
    steps: ["Apri una partita live", "Osserva gli insight", "Aggiorna con i dati in arrivo"]
  },
  acc: {
    title: "Accuracy & Trend",
    subtitle: "Andamento stagionale, prestazioni e indicatori di affidabilità.",
    steps: ["Scegli periodo", "Confronta le metriche", "Valuta il trend"]
  },
  compare: {
    title: "Confronto Campionati",
    subtitle: "Panoramica rapida delle leghe con dati comparabili.",
    steps: ["Seleziona le leghe", "Leggi i KPI principali", "Identifica differenze chiave"]
  }
}

function ShieldCheckIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={className}>
      <path d="M12 3l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3z" />
      <path d="M9.2 12.2l2 2.1 4.2-4.3" />
    </svg>
  )
}

export function ResponsiveShell() {
  const [active, setActive] = useState<Section>("pred")
  const [collapsed, setCollapsed] = useState(false)
  const [legendOpen, setLegendOpen] = useState(false)
  const [howToOpen, setHowToOpen] = useState(false)
  const showMatchFilters = active === "pred"
  const filtersLeft = null
  const filtersRight = null
  const filtersBottom = null

  const Content = () => {
    if (active === "pred") return <StatisticalPredictionsDashboard />
    if (active === "live") return <LiveMatchCenter />
    if (active === "acc") return <PredictionAccuracyTracker />
    return <ChampionshipComparator />
  }

  return (
    <div className="min-h-screen pb-16 md:pb-0">
      <div className="mx-auto flex min-h-screen w-full max-w-[1440px] px-3 sm:px-4 md:px-6">
        <aside
          className={`hidden md:flex flex-col border-r border-white/10 glass-panel shadow-soft transition-all duration-300 ${
            collapsed ? "w-[80px]" : "w-72"
          }`}
        >
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
          <div className="text-sm font-bold text-gradient truncate">{collapsed ? "FM" : "Forecast Master"}</div>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="text-xs text-zinc-500 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors"
          >
            {collapsed ? "›" : "‹"}
          </button>
        </div>

        <nav className="flex-1 space-y-2 px-3 py-4">
          {sections.map((s) => {
            const activeItem = active === s.key
            return (
              <button
                key={s.key}
                onClick={() => setActive(s.key)}
                className={[
                  "group w-full rounded-2xl px-4 py-3 text-left text-sm font-semibold transition-all duration-200",
                  activeItem
                    ? "bg-gradient-to-br from-emerald-500/15 to-emerald-600/10 text-emerald-700 dark:text-emerald-300 shadow-soft"
                    : "text-zinc-700 hover:bg-white/80 dark:text-zinc-300 dark:hover:bg-zinc-800/50"
                ].join(" ")}
              >
                <span className={collapsed ? "block text-center" : ""}>{collapsed ? s.label[0] : s.label}</span>
              </button>
            )
          })}

          <div className="pt-4 mt-4 border-t border-white/10">
            <Link
              href="/reliability"
              className="group w-full rounded-2xl px-4 py-3 text-left text-sm font-semibold transition-all duration-200 text-zinc-700 hover:bg-white/80 dark:text-zinc-300 dark:hover:bg-zinc-800/50"
            >
              <span className={collapsed ? "flex items-center justify-center" : "flex items-center gap-2"}>
                <ShieldCheckIcon className="h-4 w-4" />
                {collapsed ? null : <span>Affidabilità</span>}
              </span>
            </Link>
          </div>
        </nav>
        </aside>

        <main className="flex-1 py-4 md:py-6">
          <div className="mx-auto flex max-w-7xl flex-col gap-4 px-1 sm:px-2 md:px-4">
          <header className="rounded-[28px] border border-white/10 bg-white/70 p-4 shadow-soft backdrop-blur-md dark:bg-zinc-950/30 md:p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-500 dark:text-zinc-400">
                  Forecast Master
                </div>
                <div className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
                  {sectionMeta[active].title}
                </div>
                <div className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">{sectionMeta[active].subtitle}</div>
              </div>
              <div className="flex flex-wrap items-center justify-start gap-2 lg:justify-end">
                <ThemeToggle />
                <button
                  type="button"
                  onClick={() => setLegendOpen(true)}
                  className="rounded-full border border-white/10 bg-white/75 px-4 py-2 text-xs font-semibold text-zinc-800 shadow-sm backdrop-blur-md transition hover:bg-white/90 dark:bg-zinc-950/20 dark:text-zinc-200"
                >
                  Legenda
                </button>
                <button
                  type="button"
                  onClick={() => setHowToOpen(true)}
                  className="rounded-full border border-emerald-500/30 bg-emerald-500/20 px-4 py-2 text-xs font-semibold text-emerald-800 shadow-sm transition hover:bg-emerald-500/30 dark:text-emerald-300"
                >
                  Come usare
                </button>
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              {sectionMeta[active].steps.map((step, index) => (
                <div
                  key={step}
                  className="rounded-2xl border border-white/10 bg-white/75 px-4 py-3 text-xs font-semibold text-zinc-800 shadow-sm backdrop-blur-md dark:bg-zinc-950/20 dark:text-zinc-200"
                >
                  <div className="text-[10px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                    Step {index + 1}
                  </div>
                  <div className="mt-1 text-sm font-semibold text-zinc-900 dark:text-zinc-50">{step}</div>
                </div>
              ))}
            </div>
          </header>

          {showMatchFilters && (
            <StickyFiltersBar left={filtersLeft} right={filtersRight} bottom={filtersBottom} />
          )}

          <div className="rounded-[24px] border border-white/10 bg-white/70 p-2 shadow-soft backdrop-blur-md dark:bg-zinc-950/20 md:hidden">
            <div className="flex gap-2 overflow-x-auto px-1 py-1">
              {sections.map((s) => {
                const activeItem = active === s.key
                return (
                  <button
                    key={s.key}
                    onClick={() => setActive(s.key)}
                    className={[
                      "shrink-0 rounded-full px-4 py-2 text-xs font-semibold transition",
                      activeItem
                        ? "bg-zinc-900 text-white shadow-soft dark:bg-white dark:text-zinc-900"
                        : "bg-white/80 text-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-300"
                    ].join(" ")}
                  >
                    {s.label}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="rounded-[28px] border border-white/10 bg-white/70 p-4 shadow-soft backdrop-blur-md dark:bg-zinc-950/20 md:p-5">
            <Content />
          </div>
          </div>
        </main>
      </div>

      <Modal open={legendOpen} title="Legenda" onClose={() => setLegendOpen(false)}>
        <div className="space-y-3">
          <div className="rounded-2xl border border-white/10 bg-white/75 p-3 dark:bg-zinc-950/20">
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

          <div className="rounded-2xl border border-white/10 bg-white/75 p-3 dark:bg-zinc-950/20">
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

          <div className="rounded-2xl border border-white/10 bg-white/75 p-3 dark:bg-zinc-950/20">
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
              <span className="rounded-full border border-white/10 bg-white/85 px-2 py-0.5 text-[10px] font-bold text-zinc-800 dark:text-zinc-200">
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

          <div className="rounded-2xl border border-white/10 bg-white/75 p-3 dark:bg-zinc-950/20">
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
          <div className="rounded-2xl border border-white/10 bg-white/75 p-3 text-xs text-zinc-800 dark:bg-zinc-950/20 dark:text-zinc-200">
            <div className="font-semibold text-zinc-900 dark:text-zinc-50">1) Scegli la sezione</div>
            <div className="mt-1 space-y-1 text-zinc-600 dark:text-zinc-300">
              <div>Previsioni: lista partite con probabilità, qualità e consigli.</div>
              <div>Live: monitoraggio in tempo reale (se dati disponibili).</div>
              <div>Accuracy: andamento e performance del modello.</div>
              <div>Confronto: confronto rapido tra leghe.</div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/75 p-3 text-xs text-zinc-800 dark:bg-zinc-950/20 dark:text-zinc-200">
            <div className="font-semibold text-zinc-900 dark:text-zinc-50">2) In Previsioni, imposta campionato e giornata</div>
            <div className="mt-1 space-y-1 text-zinc-600 dark:text-zinc-300">
              <div>In alto seleziona il campionato (es. Serie A, Premier…).</div>
              <div>Seleziona la giornata dal menu (quando disponibile).</div>
              <div>Usa “Ordina” per vedere prima probabilità, confidence o orario.</div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/75 p-3 text-xs text-zinc-800 dark:bg-zinc-950/20 dark:text-zinc-200">
            <div className="font-semibold text-zinc-900 dark:text-zinc-50">3) Scegli il profilo</div>
            <div className="mt-1 space-y-1 text-zinc-600 dark:text-zinc-300">
              <div>Prudente: mostra solo match con confidence alta e rischio basso.</div>
              <div>Bilanciato: filtra i match più “ragionevoli” (default).</div>
              <div>Aggressivo: include anche match più rischiosi.</div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/75 p-3 text-xs text-zinc-800 dark:bg-zinc-950/20 dark:text-zinc-200">
            <div className="font-semibold text-zinc-900 dark:text-zinc-50">4) Usa i filtri per trovare i match giusti</div>
            <div className="mt-1 space-y-1 text-zinc-600 dark:text-zinc-300">
              <div>Cerca squadra: digita il nome (es. Inter, Milan…).</div>
              <div>Solo Qualità A/B: mostra solo le partite più affidabili.</div>
              <div>Nascondi NO BET: nasconde i match con segnali deboli.</div>
              <div>Se non vedi nulla, premi “Reset filtri”.</div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/75 p-3 text-xs text-zinc-800 dark:bg-zinc-950/20 dark:text-zinc-200">
            <div className="font-semibold text-zinc-900 dark:text-zinc-50">5) Apri i dettagli e salva i preferiti</div>
            <div className="mt-1 space-y-1 text-zinc-600 dark:text-zinc-300">
              <div>Apri una partita per vedere mercati, motivazioni e rischi.</div>
              <div>Usa ☆ per aggiungere ai Preferiti e PIN per fissare in alto.</div>
              <div>Usa “Dettagli” per il riepilogo completo della partita.</div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/75 p-3 text-xs text-zinc-800 dark:bg-zinc-950/20 dark:text-zinc-200">
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

      <nav className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around border-t border-white/10 glass-panel shadow-strong md:hidden">
        {sections.map((s) => {
          const activeItem = active === s.key
          return (
            <button
              key={s.key}
              onClick={() => setActive(s.key)}
              className={[
                "flex flex-col items-center gap-1.5 py-3 px-4 text-xs font-semibold transition-all duration-200",
                activeItem ? "text-emerald-600 dark:text-emerald-400 scale-110" : "text-zinc-500 dark:text-zinc-400"
              ].join(" ")}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full transition-all ${activeItem ? "bg-emerald-600 dark:bg-emerald-400 scale-150" : "bg-transparent"}`}
              />
              {s.label}
            </button>
          )
        })}
      </nav>
    </div>
  )
}
