# STEP 00 — Schema dati & terminologia dell’App

## Scopo
Questo documento spiega tutti i principali dati e termini usati nell’app, in modo comprensibile anche a chi non è un esperto di analisi calcistica.

Serve come:
- riferimento interno
- documentazione per sviluppo
- base per il quadro informativo UI

---

## 1. RISULTATI E MERCATI PREVISTI

### 1X2 — Esito finale
Previsione del risultato al 90° minuto.

| Sigla | Significato |
|------|-------------|
| 1 | Vittoria squadra di casa |
| X | Pareggio |
| 2 | Vittoria squadra ospite |

Le percentuali indicano probabilità stimate, non certezze.

---

### Over / Under (Goal totali)
Numero complessivo di gol segnati nella partita.

| Termine | Significato |
|--------|------------|
| Over 2.5 | 3 o più gol |
| Under 2.5 | Meno di 3 gol |
| Over 1.5 | Almeno 2 gol |

---

### BTTS (Both Teams To Score)
Indica se entrambe le squadre segneranno almeno un gol.

| Valore | Significato |
|--------|------------|
| YES | Entrambe segnano |
| NO | Almeno una non segna |

---

## 2. METRICHE DI AFFIDABILITÀ

### Confidence (conf)
Indica quanto è solida la previsione, su scala 0–100.

| Valore | Interpretazione |
|--------|-----------------|
| 80–100 | Molto affidabile |
| 60–79 | Affidabile |
| 40–59 | Media |
| < 40 | Poco affidabile |

La confidence dipende da:
- quantità di dati reali
- stabilità delle squadre
- forma recente
- coerenza storica

---

### Risk (Rischio)
Livello di imprevedibilità della partita.

| Rischio | Significato |
|---------|-------------|
| LOW | Scenario stabile |
| MEDIUM | Alcune incognite |
| HIGH | Match imprevedibile |

---

## 3. METRICHE DI FORZA DELLE SQUADRE

### Team Strength (Forza squadra)
Valore statistico che rappresenta la qualità complessiva della squadra.

Non è:
- classifica
- numero di vittorie

È una misura relativa alle altre squadre.

---

### Elo Rating
Sistema matematico che aggiorna la forza squadra dopo ogni match.

| Evento | Effetto |
|--------|---------|
| Vittoria contro forte | Aumento elevato |
| Vittoria contro debole | Aumento lieve |
| Sconfitta contro debole | Calo forte |

È il cuore del modello predittivo.

---

### Form (Forma recente)
Valuta come sta andando una squadra negli ultimi match.

| Risultato | Punteggio |
|----------|-----------|
| Vittoria | 1 |
| Pareggio | 0.5 |
| Sconfitta | 0 |

Usata per intercettare:
- crisi
- strisce positive
- cambi recenti

---

## 4. METRICHE COMPOSITE (INSIGHTS)

### Success %
Indicatore complessivo di qualità e affidabilità.

È una combinazione di:
- forza squadra
- forma recente
- stabilità dati

| Valore | Significato |
|--------|------------|
| > 75% | Squadra molto solida |
| 60–75% | Buona scelta |
| < 60% | Valutare con cautela |

Non indica la probabilità matematica di vittoria.

---

### Squadra da giocare
Squadra che offre il miglior equilibrio tra qualità, forma e rischio contenuto nel contesto attuale.

---

## 5. TERMINI DI SISTEMA

### Real Data Only
Il sistema utilizza esclusivamente dati reali ufficiali. Nessuna simulazione o dato fittizio.

---

### Stato match

| Stato | Significato |
|-------|-------------|
| FINISHED | Match concluso |
| SCHEDULED | Match futuro |
| LIVE | Match in corso |

---

## Conclusione
Il sistema non fornisce certezze, ma analisi quantitative basate su dati reali per aiutare a prendere decisioni più consapevoli.

