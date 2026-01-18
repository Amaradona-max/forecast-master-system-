# STEP 13 — Storico previsioni & performance

## Obiettivo
Salvare lo storico delle previsioni prodotte dall’app e misurare in modo oggettivo come stanno performando nel tempo (per campionato, periodo e mercato).

---

## Perché serve
- Verifica: capire se il modello sta migliorando o degradando.
- Trasparenza: mostrare all’utente risultati aggregati (non solo singole percentuali).
- Tuning: regolare soglie (es. confidence, value_index) su basi statistiche.

---

## Cosa salvare (minimo)
Per ogni match (quando si genera una previsione):
- `match_id`, `championship`, `home_team`, `away_team`
- `kickoff_unix`
- `generated_at_unix` (quando è stata prodotta la previsione)
- probabilità per mercato (almeno 1X2: home/draw/away)
- `confidence` (0–100) e/o i dettagli in `explain.confidence`
- snapshot `explain` (per audit e explainability)

Per ogni match (quando è FINISHED e si conosce il risultato):
- `final_score` (home/away)
- esito 1X2 reale
- eventuali outcome per mercati derivati (over2.5, btts) se calcolabili dal punteggio finale

---

## Granularità: snapshot vs “ultima previsione”
Opzioni:
- Solo ultima previsione per match: più semplice, meno dati storici.
- Snapshot multipli (consigliato): conserva più previsioni nel tempo (es. 24h prima, 6h prima, 1h prima, kickoff, live), utile per analizzare drift.

---

## Metriche principali

### Per 1X2
- Log loss: penalizza previsioni molto sbagliate e molto confident.
- Brier score (multiclasse): misura errore quadratico sulle probabilità.
- Accuracy (argmax): solo come metrica secondaria (può essere fuorviante).
- ROC-AUC: usabile su binarizzazioni o indicatori derivati; utile come trend.

### Per mercati binari (Over/Under, BTTS)
- Brier score binario
- Log loss binario
- Calibration curve (reliability diagram)

---

## Calibration & stabilità
Monitorare:
- calibrazione (probabilità vs frequenze reali)
- variazione nel tempo delle metriche (trend 7/14/30 giorni)
- copertura: quante partite con dati completi vs fallback (missing)

---

## Output consigliati per UI

### 1) Trend performance
Per campionato:
- serie temporale (giornaliera) di log loss / brier / ROC-AUC

### 2) Tab “per match”
Per match concluso:
- probabilità pre-match (snapshot selezionato) + risultato reale
- “hit/miss” per mercato

### 3) Breakdown per confidence bucket
Separare match per fasce confidence (es. 0–40, 40–60, 60–80, 80–100) e mostrare:
- accuracy/brier/logloss medi
- frequenza reale degli eventi

---

## Persistenza dati
Strategie:
- SQLite: adatta a storico e query aggregate.
- File JSON append-only: semplice, ma poco scalabile per query.

Se si usa SQLite, separare idealmente:
- `predictions_history` (snapshot previsioni)
- `match_results` (risultati reali)
- `metrics_daily` (metriche aggregate già calcolate)

---

## Considerazioni “Real Data Only”
Per evitare statistiche distorte:
- includere in KPI solo match con risultati reali (FINISHED)
- escludere periodi non coperti dal provider
- tracciare nel record la `source` del match e la `degradation_level`

