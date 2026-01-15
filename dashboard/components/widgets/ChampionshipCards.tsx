"use client"

import { useEffect, useMemo, useState } from "react"

import { apiUrl, getApiBaseUrl } from "@/components/api/client"
import { Card } from "@/components/widgets/Card"

type OverviewMatch = {
  match_id: string
  championship: string
  home_team: string
  away_team: string
  status: string
  matchday?: number | null
  kickoff_unix?: number | null
  updated_at_unix: number
  probabilities: Record<string, number>
  confidence: number
  explain?: Record<string, unknown>
  source?: Record<string, unknown>
}

type MatchdayBlock = { matchday_number?: number | null; matchday_label: string; matches: OverviewMatch[] }

type ChampionshipOverview = {
  championship: string
  title: string
  accuracy_target?: string | null
  key_features: string[]
  matchdays: MatchdayBlock[]
  top_matches: OverviewMatch[]
  to_play_ge_70: OverviewMatch[]
  finished: OverviewMatch[]
}

type ChampionshipsOverviewResponse = { generated_at_utc: string; championships: ChampionshipOverview[] }

type SystemStatusResponse = {
  data_provider: string
  real_data_only: boolean
  data_error?: string | null
  matches_loaded: number
  now_utc: string
}

function matchdayKey(md: MatchdayBlock) {
  return String(md.matchday_number ?? md.matchday_label)
}

function formatKickoff(kickoffUnix?: number | null) {
  const v = Number(kickoffUnix)
  if (!Number.isFinite(v) || v <= 0) return null
  const dt = new Date(v * 1000)
  if (Number.isNaN(dt.getTime())) return null
  return new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(dt)
}

export function ChampionshipCards() {
  const [data, setData] = useState<ChampionshipOverview[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<SystemStatusResponse | null>(null)

  useEffect(() => {
    let active = true

    async function loadStatus() {
      try {
        const res = await fetch(apiUrl("/api/v1/system/status"), { cache: "no-store" })
        if (!res.ok) return
        const json = (await res.json()) as SystemStatusResponse
        if (active) setStatus(json)
      } catch {}
    }

    async function run() {
      try {
        const res = await fetch(apiUrl("/api/v1/overview/championships"), { cache: "no-store" })
        if (!res.ok) {
          let detail = ""
          try {
            const body = (await res.json()) as { detail?: unknown }
            if (body?.detail) detail = String(body.detail)
          } catch {}
          throw new Error(detail ? `overview_failed:${res.status}:${detail}` : `overview_failed:${res.status}`)
        }
        const json = (await res.json()) as ChampionshipsOverviewResponse
        if (active) setData(json.championships)
      } catch (e) {
        if (active) setError(String((e as Error)?.message ?? e))
      }
    }

    loadStatus()
    run()
    const t = window.setInterval(run, 30_000)
    return () => {
      active = false
      window.clearInterval(t)
    }
  }, [])

  const ordered = useMemo(() => {
    if (!data) return []
    const order = ["serie_a", "premier_league", "la_liga", "bundesliga", "eliteserien"]
    return [...data].sort((a, b) => order.indexOf(a.championship) - order.indexOf(b.championship))
  }, [data])

  if (status && (status.data_provider === "mock" || !status.real_data_only || Boolean(status.data_error))) {
    return (
      <Card>
        <div className="text-sm font-semibold tracking-tight">Dati non verificati</div>
        <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
          Sorgente: {status.data_provider} · Real data only: {status.real_data_only ? "on" : "off"} · Match caricati: {status.matches_loaded}
        </div>
        {status.data_error ? (
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">Errore sorgente dati: {status.data_error}</div>
        ) : null}
        <div className="mt-4 rounded-2xl border border-amber-200/70 bg-amber-50/70 p-3 text-xs text-amber-900 backdrop-blur-md dark:border-amber-900/40 dark:bg-amber-950/35 dark:text-amber-100">
          <div className="font-medium">Per sbloccare i calendari 2026 (solo dati reali)</div>
          {status.data_error === "football_data_key_missing" || status.data_error === "api_football_key_missing" ? (
            <div className="mt-1">
              Apri <span className="font-mono">forecast-master-system/.env</span> e imposta <span className="font-mono">FORECAST_FOOTBALL_DATA_KEY</span> (e <span className="font-mono">FORECAST_DATA_PROVIDER=football_data</span>), poi riavvia l’API.
            </div>
          ) : status.data_error === "ratings_missing" ? (
            <div className="mt-1">
              Genera prima i rating storici 2015–2025: esegui una POST su <span className="font-mono">/api/v1/system/rebuild-ratings</span> (richiede chiave API),
              poi attendi il caricamento delle gare 2026.
            </div>
          ) : (
            <div className="mt-1">Configura il provider reale e completa la sincronizzazione prima dei pronostici.</div>
          )}
        </div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <div className="text-sm font-semibold tracking-tight">Errore caricamento overview</div>
        <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">API: {getApiBaseUrl()}</div>
        <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">{error}</div>
        {status?.real_data_only ? (
          <div className="mt-4 rounded-2xl border border-amber-200/70 bg-amber-50/70 p-3 text-xs text-amber-900 backdrop-blur-md dark:border-amber-900/40 dark:bg-amber-950/35 dark:text-amber-100">
            Modalità dati reali attiva: se vedi 503, manca la sorgente dati oppure la chiave provider.
          </div>
        ) : null}
        <div className="mt-4 rounded-2xl border border-zinc-200/70 bg-white/55 p-3 text-xs text-zinc-700 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/25 dark:text-zinc-200">
          Su Vercel puoi impostare la base API anche senza rebuild aprendo il sito con <span className="font-mono">?api=https://TUO-TUNNEL</span>.
        </div>
      </Card>
    )
  }

  if (!data) {
    return (
      <Card>
        <div className="text-sm font-semibold tracking-tight">Caricamento campionati…</div>
        {status ? (
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
            Sorgente: {status.data_provider} · Real data only: {status.real_data_only ? "on" : "off"} · Match caricati: {status.matches_loaded}
          </div>
        ) : null}
      </Card>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {ordered.map((c) => (
        <ChampionshipCard key={c.championship} data={c} />
      ))}
    </div>
  )
}

function ChampionshipCard({ data }: { data: ChampionshipOverview }) {
  const matchdays = useMemo(() => data.matchdays ?? [], [data.matchdays])
  const matchdaysToPlay = useMemo(() => matchdays.filter((md) => md.matches?.some((m) => m.status !== "FINISHED")), [matchdays])

  const defaultMdKey = useMemo(() => {
    if (!matchdaysToPlay.length) return ""
    return matchdayKey(matchdaysToPlay[0])
  }, [matchdaysToPlay])

  const [selectedMdKey, setSelectedMdKey] = useState<string>("")

  useEffect(() => {
    if (!matchdaysToPlay.length) return
    const keys = new Set(matchdaysToPlay.map(matchdayKey))
    if (!selectedMdKey || !keys.has(selectedMdKey)) setSelectedMdKey(defaultMdKey)
  }, [defaultMdKey, matchdaysToPlay, selectedMdKey])

  const md = useMemo(() => {
    return matchdaysToPlay.find((x) => matchdayKey(x) === selectedMdKey) ?? matchdaysToPlay[0]
  }, [matchdaysToPlay, selectedMdKey])

  const scopedMatches = useMemo(() => md?.matches ?? [], [md])
  const scopedToPlay = useMemo(() => scopedMatches.filter((m) => m.status !== "FINISHED"), [scopedMatches])
  const topList = useMemo(() => {
    const base = scopedToPlay.length ? scopedToPlay : (data.top_matches ?? [])
    return [...base].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0)).slice(0, 5)
  }, [data.top_matches, scopedToPlay])
  const toPlayList = useMemo(() => {
    return topList.filter((m) => (m.confidence ?? 0) >= 0.7)
  }, [topList])
  const finishedList = useMemo(() => {
    const base = scopedMatches.length ? scopedMatches : (data.finished ?? [])
    return base.filter((m) => m.status === "FINISHED")
  }, [data.finished, scopedMatches])

  const calendar2026 = useMemo(() => {
    const out: { label: string; matches: OverviewMatch[] }[] = []
    for (const b of matchdaysToPlay) {
      const ms = (b.matches ?? []).filter((m) => m.status !== "FINISHED")
      if (ms.length) out.push({ label: b.matchday_label, matches: ms })
    }
    return out
  }, [matchdaysToPlay])

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-base font-semibold tracking-tight">{data.title}</div>
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
            Target: {data.accuracy_target ?? "n/d"} · Feature: {data.key_features?.length ? data.key_features.join(", ") : "n/d"}
          </div>
        </div>
        <div className="shrink-0 rounded-full border border-zinc-200/70 bg-white/60 px-2 py-1 text-xs text-zinc-700 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-900/45 dark:text-zinc-200">
          {data.championship}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3">
        <Section title="Calendario stagione 2025/2026 · Gare 2026 (verificate)">
          {calendar2026.length ? (
            <div className="space-y-3">
              {calendar2026.map((b) => (
                <div key={b.label}>
                  <div className="text-xs font-medium text-zinc-700 dark:text-zinc-200">{b.label}</div>
                  <div className="mt-2 space-y-2">
                    {b.matches.map((m) => (
                      <MiniRow key={m.match_id} m={m} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-zinc-600 dark:text-zinc-300">Nessuna gara 2026 disponibile.</div>
          )}
        </Section>

        {matchdaysToPlay.length > 1 ? (
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs text-zinc-600 dark:text-zinc-300">Giornata</div>
            <select
              aria-label="Seleziona giornata"
              className="rounded-xl border border-zinc-200/70 bg-white/70 px-3 py-2 text-xs shadow-sm backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/35"
              value={selectedMdKey}
              onChange={(e) => setSelectedMdKey(e.target.value)}
            >
              {matchdaysToPlay.map((x) => (
                <option key={matchdayKey(x)} value={matchdayKey(x)}>
                  {x.matchday_label}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        <Section title={`${md?.matchday_label ?? "Giornata"} · Previsioni`}>
          {scopedToPlay.length ? (
            <div className="space-y-2">
              {scopedToPlay.map((m) => (
                <MatchRow key={m.match_id} m={m} />
              ))}
            </div>
          ) : (
            <div className="text-sm text-zinc-600 dark:text-zinc-300">Nessuna partita disponibile.</div>
          )}
        </Section>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Section title={`Top gare · ${md?.matchday_label ?? "Giornata"}`}>
            {topList.length ? (
              <div className="space-y-2">
                {topList.map((m) => (
                  <MiniRow key={m.match_id} m={m} />
                ))}
              </div>
            ) : (
              <div className="text-sm text-zinc-600 dark:text-zinc-300">n/d</div>
            )}
          </Section>
          <Section title={`≥70% da giocare · ${md?.matchday_label ?? "Giornata"}`}>
            {toPlayList.length ? (
              <div className="space-y-2">
                {toPlayList.map((m) => (
                  <MiniRow key={m.match_id} m={m} />
                ))}
              </div>
            ) : (
              <div className="text-sm text-zinc-600 dark:text-zinc-300">Nessuna sopra soglia.</div>
            )}
          </Section>
          <Section title={`Gare concluse · ${md?.matchday_label ?? "Giornata"}`}>
            {finishedList.length ? (
              <div className="space-y-2">
                {finishedList.map((m) => (
                  <MiniRow key={m.match_id} m={m} />
                ))}
              </div>
            ) : (
              <div className="text-sm text-zinc-600 dark:text-zinc-300">Nessuna conclusa.</div>
            )}
          </Section>
        </div>
      </div>
    </Card>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-zinc-200/70 bg-white/55 p-3 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-900/30">
      <div className="text-xs font-semibold text-zinc-800 dark:text-zinc-100">{title}</div>
      <div className="mt-2">{children}</div>
    </div>
  )
}

function MatchRow({ m }: { m: OverviewMatch }) {
  const p1 = m.probabilities?.home_win ?? 0
  const px = m.probabilities?.draw ?? 0
  const p2 = m.probabilities?.away_win ?? 0
  const bestLabel = p1 >= px && p1 >= p2 ? "1" : px >= p1 && px >= p2 ? "X" : "2"
  const kickoffLabel = formatKickoff(m.kickoff_unix)

  return (
    <div className="rounded-2xl border border-zinc-200/70 bg-white/55 p-3 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/25">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">
            {m.home_team} - {m.away_team}
          </div>
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
            {kickoffLabel ? <span>{kickoffLabel} · </span> : null}
            {m.status} · conf {Math.round((m.confidence ?? 0) * 100)}% · pick {bestLabel}
          </div>
        </div>
        <div className="shrink-0 text-right text-xs">
          <div className="font-semibold">{Math.round((p1 ?? 0) * 100)} / {Math.round((px ?? 0) * 100)} / {Math.round((p2 ?? 0) * 100)}</div>
          <div className="mt-1 h-2 w-24 overflow-hidden rounded bg-zinc-200 dark:bg-zinc-800">
            <div
              className="h-2 bg-[linear-gradient(90deg,#10b981,#3b82f6)]"
              style={{ width: `${Math.round((m.confidence ?? 0) * 100)}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

function MiniRow({ m }: { m: OverviewMatch }) {
  const src = m.source ?? {}
  const srcLabel = typeof src.provider === "string" ? src.provider : null
  const kickoffLabel = formatKickoff(m.kickoff_unix)
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-zinc-200/70 bg-white/55 px-3 py-2 text-xs backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-950/20">
      <div className="min-w-0">
        <div className="truncate">
          {m.home_team} - {m.away_team}
        </div>
        {kickoffLabel ? <div className="mt-0.5 text-[10px] text-zinc-500 dark:text-zinc-400">{kickoffLabel}</div> : null}
      </div>
      <div className="shrink-0 text-right">
        <div className="font-semibold">{Math.round((m.confidence ?? 0) * 100)}%</div>
        {srcLabel ? <div className="text-[10px] text-zinc-500 dark:text-zinc-400">{srcLabel}</div> : null}
      </div>
    </div>
  )
}
