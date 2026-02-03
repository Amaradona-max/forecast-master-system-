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

const sections: { key: Section; label: string; icon: string }[] = [
  { key: "pred", label: "Previsioni", icon: "⚽" },
  { key: "live", label: "Live", icon: "🔴" },
  { key: "acc", label: "Accuracy", icon: "📊" },
  { key: "compare", label: "Confronto", icon: "🏆" }
]

const sectionMeta: Record<Section, { title: string; subtitle: string; emoji: string }> = {
  pred: {
    title: "Previsioni Match",
    subtitle: "Vista principale per scegliere match, qualità e rischio con contesto completo.",
    emoji: "⚽"
  },
  live: {
    title: "Live Match Center",
    subtitle: "Monitoraggio in tempo reale con insight e indicatori principali.",
    emoji: "🔴"
  },
  acc: {
    title: "Accuracy & Trend",
    subtitle: "Andamento stagionale, prestazioni e indicatori di affidabilità.",
    emoji: "📊"
  },
  compare: {
    title: "Confronto Campionati",
    subtitle: "Panoramica rapida delle leghe con dati comparabili.",
    emoji: "🏆"
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
    <div className="min-h-screen pb-20 md:pb-0 bg-neutral-50 dark:bg-dark-bg">
      <div className="mx-auto flex min-h-screen w-full max-w-[1600px] px-3 sm:px-4 md:px-6">
        <aside
          className={`hidden md:flex flex-col glass-panel transition-all duration-300 ${
            collapsed ? "w-20" : "w-72"
          }`}
        >
          <div className="flex items-center justify-between px-5 py-6 border-b border-neutral-200 dark:border-dark-border">
            <div className={`text-sm font-bold transition-all ${collapsed ? "text-center" : ""}`}>
              {collapsed ? <span className="text-2xl">⚽</span> : <span className="text-gradient-pastel">Forecast Master</span>}
            </div>
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="p-2 rounded-xl hover:bg-pastel-blue/30 transition-colors text-neutral-600 hover:text-accent-blue"
              title={collapsed ? "Espandi" : "Comprimi"}
            >
              {collapsed ? "›" : "‹"}
            </button>
          </div>

          <nav className="flex-1 space-y-2 px-3 py-4">
            {sections.map((s) => {
              const isActive = active === s.key
              return (
                <button
                  key={s.key}
                  onClick={() => setActive(s.key)}
                  className={[
                    "group w-full rounded-2xl px-4 py-3 text-left text-sm font-semibold transition-all duration-200",
                    isActive
                      ? "bg-gradient-to-br from-pastel-blue/40 to-pastel-lavender/40 text-neutral-900 dark:text-dark-text-primary shadow-soft ring-1 ring-accent-blue/20"
                      : "text-neutral-700 hover:bg-white/50 dark:text-neutral-300 dark:hover:bg-dark-surface/50"
                  ].join(" ")}
                >
                  <span className={`flex items-center gap-3 ${collapsed ? "justify-center" : ""}`}>
                    <span className="text-lg">{s.icon}</span>
                    {!collapsed && <span>{s.label}</span>}
                  </span>
                </button>
              )
            })}

            <div className="pt-4 mt-4 border-t border-neutral-200 dark:border-dark-border">
              <Link
                href="/reliability"
                className="group w-full rounded-2xl px-4 py-3 flex items-center gap-3 text-sm font-semibold transition-all duration-200 text-neutral-700 hover:bg-white/50 dark:text-neutral-300 dark:hover:bg-dark-surface/50"
              >
                <ShieldCheckIcon className="h-5 w-5" />
                {!collapsed && <span>Affidabilità</span>}
              </Link>
            </div>
          </nav>
        </aside>

        <main className="flex-1 md:ml-6">
          <div className="section-container">
            <header className="card-modern p-6 mb-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 dark:text-neutral-400 mb-2">
                    {sectionMeta[active].emoji} Forecast Master
                  </div>
                  <h1 className="text-2xl lg:text-3xl font-bold tracking-tight text-neutral-900 dark:text-dark-text-primary mb-2">
                    {sectionMeta[active].title}
                  </h1>
                  <p className="text-sm text-neutral-600 dark:text-neutral-300">{sectionMeta[active].subtitle}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <ThemeToggle />
                  <button
                    type="button"
                    onClick={() => setLegendOpen(true)}
                    className="btn-secondary text-sm"
                  >
                    📖 Legenda
                  </button>
                  <button
                    type="button"
                    onClick={() => setHowToOpen(true)}
                    className="btn-secondary text-sm"
                  >
                    ❓ Come Usare
                  </button>
                </div>
              </div>
            </header>

            {showMatchFilters && <StickyFiltersBar left={filtersLeft} right={filtersRight} bottom={filtersBottom} />}

            <div className="animate-fade-in">
              <Content />
            </div>
          </div>
        </main>
      </div>

      <nav className="fixed bottom-0 left-0 right-0 z-50 md:hidden glass-panel border-t border-neutral-200 dark:border-dark-border">
        <div className="flex items-center justify-around px-2 py-3">
          {sections.map((s) => {
            const isActive = active === s.key
            return (
              <button
                key={s.key}
                onClick={() => setActive(s.key)}
                className={[
                  "flex flex-col items-center gap-1 px-4 py-2 rounded-2xl transition-all duration-200",
                  isActive ? "bg-pastel-blue/40 text-accent-blue scale-105" : "text-neutral-500 dark:text-neutral-400"
                ].join(" ")}
              >
                <span className="text-xl">{s.icon}</span>
                <span className="text-[10px] font-bold uppercase tracking-wider">{s.label}</span>
              </button>
            )
          })}
        </div>
      </nav>

      <Modal open={legendOpen} title="📖 Legenda Badge e Simboli" onClose={() => setLegendOpen(false)}>
        <div className="space-y-4">
          <div className="card-modern p-4">
            <h3 className="text-sm font-bold text-neutral-900 dark:text-dark-text-primary mb-3">Badge Principali</h3>
            <div className="flex flex-wrap gap-2 mb-4">
              <span className="badge-success">TOP</span>
              <span className="badge-info">CONF</span>
              <span className="badge-danger">LIVE</span>
              <span className="badge-warning">NO BET</span>
              <span className="badge-danger">UPSET</span>
            </div>
            <div className="space-y-2 text-xs text-neutral-600 dark:text-neutral-300">
              <div><strong>TOP:</strong> Probabilità massima elevata</div>
              <div><strong>CONF:</strong> Confidence alta</div>
              <div><strong>LIVE:</strong> Partita in corso</div>
              <div><strong>NO BET:</strong> Segnali insufficienti</div>
              <div><strong>UPSET:</strong> Possibile sorpresa</div>
            </div>
          </div>

          <div className="card-modern p-4">
            <h3 className="text-sm font-bold text-neutral-900 dark:text-dark-text-primary mb-3">Tier Quality</h3>
            <div className="space-y-2 text-xs text-neutral-600 dark:text-neutral-300">
              <div><strong>Tier S/A:</strong> Massima qualità (verde)</div>
              <div><strong>Tier B:</strong> Buona qualità (blu)</div>
              <div><strong>Tier C:</strong> Qualità discreta (giallo)</div>
            </div>
          </div>
        </div>
      </Modal>

      <Modal open={howToOpen} title="❓ Come Usare l'App" onClose={() => setHowToOpen(false)}>
        <div className="space-y-4">
          {[
            {
              title: "1️⃣ Scegli la sezione",
              desc: "Usa la navigazione laterale (desktop) o in basso (mobile) per passare tra Previsioni, Live, Accuracy e Confronto."
            },
            {
              title: "2️⃣ Filtra i match",
              desc: "In Previsioni, usa i filtri per campionato, giornata e livello di rischio (Prudente/Bilanciato/Aggressivo)."
            },
            {
              title: "3️⃣ Leggi le card",
              desc: "Ogni card mostra: probabilità, confidence, chaos index, tier quality e insights. Click per dettagli completi."
            },
            {
              title: "4️⃣ Monitora in Live",
              desc: "Vai su Live per seguire le partite in corso con dati aggiornati in tempo reale."
            },
            {
              title: "5️⃣ Analizza l'Accuracy",
              desc: "Controlla le performance del modello per periodo e campionato nella sezione Accuracy."
            }
          ].map((step, i) => (
            <div key={i} className="card-modern p-4">
              <h4 className="text-sm font-bold text-neutral-900 dark:text-dark-text-primary mb-2">{step.title}</h4>
              <p className="text-xs text-neutral-600 dark:text-neutral-300">{step.desc}</p>
            </div>
          ))}
        </div>
      </Modal>
    </div>
  )
}
