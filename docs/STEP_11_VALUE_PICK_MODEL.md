# STEP 11 — Modello “Value Pick” (successo vs quota)

## Obiettivo
Individuare le partite in cui la probabilità stimata dall’app risulta più alta della probabilità implicita nelle quote di mercato, evidenziando potenziali “Value Pick”.

---

## Concetti base

### Probabilità stimata dall’app
È una probabilità modellata (0–100) che deriva dai modelli e dai dati disponibili.

Nel contesto dell’app, a seconda del punto UI/feature:
- può essere una probabilità di mercato (es. 1X2: `home_win/draw/away_win`)
- può essere una metrica sintetica (es. `success_pct` per insight “Squadre da giocare”)

Per il Value Pick, la definizione più “pulita” è usare la probabilità del mercato specifico (es. 1X2 1 / X / 2).

---

### Cos’è una quota implicita
Ogni quota rappresenta una probabilità implicita.

Formula base:

`probabilità_implicita = 1 / quota`

Esempi:
- Quota 2.00 → 0.50 → 50%
- Quota 3.00 → 0.333… → 33.3%

Nota: le quote includono spesso una commissione/margine (overround). In una versione avanzata, conviene normalizzare le probabilità implicite considerando l’overround del bookmaker.

---

## Logica “Value Pick”

### Value Index
`value_index = success_pct - implied_pct`

Dove:
- `success_pct` è la probabilità stimata dall’app in percentuale (0–100)
- `implied_pct` è la probabilità implicita della quota in percentuale (0–100)

Interpretazione:
- `value_index > 0` → possibile valore
- `value_index > 8–10` → Value Pick forte

---

## Esempio
- Success stimato: 65%
- Quota mercato: 2.40 (implied 41.6%)

`value_index = 65.0 - 41.6 = +23.4`

---

## Livelli (value_level)
Classificazione consigliata:
- LOW: `0 < value_index < 8`
- MEDIUM: `8 ≤ value_index < 12`
- HIGH: `value_index ≥ 12`

Soglie modulabili per campionato/mercato, in base alla distribuzione storica.

---

## Dati necessari
Per calcolare il Value Pick servono:
- probabilità di mercato dall’app (es. 1X2)
- quote di mercato per lo stesso evento e mercato

In “Real Data Only”, le quote non arrivano automaticamente dai provider risultati: vanno fornite tramite:
- input manuale (UI/admin) oppure
- integrazione separata con provider quote (se consentito dal perimetro del progetto)

---

## Output API suggerito
Esempio payload per un singolo suggerimento:

```json
{
  "match": "Inter vs Roma",
  "market": "1",
  "success_pct": 65.0,
  "odds": 2.40,
  "implied_pct": 41.6,
  "value_index": 23.4,
  "value_level": "HIGH"
}
```

Campi consigliati (più robusti per integrazione):
- `match_id`
- `championship`
- `home_team`, `away_team`
- `kickoff_unix` / `kickoff_utc`
- `market` (es. `1`, `X`, `2`, oppure `over_2_5`, `btts_yes`)
- `success_pct`
- `odds`
- `implied_pct`
- `value_index`
- `value_level`
- `generated_at_utc`
- `source` (bookmaker/provider quote o “manual”)

---

## UI
Linee guida UI:
- ordinamento decrescente per `value_index`
- badge “VALUE” (e variante “VALUE HIGH”)
- colore dedicato (es. verde/emerald per HIGH, giallo per MEDIUM, grigio per LOW)
- tooltip con formula:
  - `implied = 1/odds`
  - `value_index = success - implied`

---

## Note di qualità
- Validazione quote: `odds > 1.01` (minimo realistico) e massimo ragionevole configurabile.
- Clamp su percentuali: `0–100`.
- Tracciamento “edge” reale: confrontare success_pct con risultati storici per verificare che HIGH non sia solo rumore.
- Gestione overround (fase avanzata): normalizzare implied di tutti gli esiti dello stesso mercato.

