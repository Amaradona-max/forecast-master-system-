# STEP 14 — Explainability AI

## Obiettivo
Rendere comprensibile “perché” una previsione ha quelle percentuali, trasformando i dettagli tecnici del modello in spiegazioni chiare (UI + API), senza promettere certezze.

---

## Tipi di explainability
- Tecnica (per sviluppo): mostra componenti, pesi, feature flags, degradazione, range.
- Semantica (per UI): traduce i segnali in frasi brevi e motivazioni leggibili.

---

## Explain attuale (payload tecnico)
Le risposte di previsione includono già un oggetto `explain` che contiene:
- `components`: segnali e parametri usati nel calcolo (forza relativa, home advantage, expected goals, ecc.)
- `ensemble_components`: scomposizione dei contributi (base / poisson / dixon coles / logit, calibrazione)
- `derived_markets`: mercati derivati (es. over 2.5, btts)
- `confidence`: score + label (HIGH / MEDIUM / LOW)
- `ranges`: intervalli di probabilità (incertezza)
- `missing_flags`: indicatori di dati mancanti (feature)
- `safe_mode`: modalità prudenziale e motivo
- `feature_version`: versione del set di feature

Quando presente, può apparire anche:
- `cache`: hit/miss (se la previsione è stata servita da cache)
- `ratings`: metadati del rating/elo (quando disponibili)

Riferimento implementazione: [service.py](file:///Users/prova/Desktop/Top%20Pronostici%20per%20Campionati%20Europei/forecast-master-system/ml_engine/ensemble_predictor/service.py)

---

## Mapping “tecnico → umano” (linee guida)

### Forza relativa
Da `components.team_strength_delta`:
- positivo: squadra di casa più forte (in media)
- negativo: squadra ospite più forte (in media)

### Expected goals
Da `components.lam_home` e `components.lam_away`:
- valori più alti → più gol attesi
- differenza ampia → maggiore sbilanciamento del match

### Mercati derivati
Da `derived_markets`:
- `over_2_5`: probabilità di almeno 3 gol
- `btts`: probabilità che entrambe segnino

### Affidabilità e prudenza
Da `confidence.score/label`, `ranges`, `safe_mode`:
- confidence alta + range stretti → previsione più stabile
- safe_mode true → l’app forza prudenza (più incertezza e/o downgrade)

---

## UI: componenti consigliati
- Tooltip sulle percentuali con 2–3 motivi principali (“driver”).
- Pannello dettagli (drawer/modale) con:
  - expected goals (lam_home/lam_away)
  - indicatori di forza relativa
  - mercati derivati (over2.5, btts)
  - range di incertezza
  - note su dati mancanti/safe mode

---

## Testi suggeriti (microcopy)
Esempi di frasi:
- “La squadra di casa risulta più forte nel rating e gioca in casa.”
- “Il modello stima un totale gol atteso elevato: aumenta Over 2.5.”
- “Affidabilità media: dati parziali o segnali non coerenti.”
- “Modalità prudente attiva: previsione resa più conservativa.”

---

## Output API “explainability summary” (opzionale)
Per evitare di esporre tutta la struttura tecnica in UI, si può aggiungere un riassunto:

```json
{
  "summary": [
    "Home più forte nel rating e vantaggio casa positivo",
    "Expected goals: 1.62 vs 1.08 (match sbilanciato)",
    "Confidence: MEDIUM"
  ],
  "drivers": [
    { "key": "team_strength_delta", "direction": "home", "weight": "high" },
    { "key": "home_advantage", "direction": "home", "weight": "medium" },
    { "key": "lam_diff", "direction": "home", "weight": "medium" }
  ]
}
```

---

## Guardrail
- Non usare linguaggio deterministico (“sicuro”, “garantito”).
- Tenere separati “probabilità” e “confidence” (sono concetti diversi).
- Rendere visibile quando mancano dati o quando safe mode è attivo.

