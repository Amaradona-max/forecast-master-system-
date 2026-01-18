# STEP 00 — App info overview

## Scopo
Questo documento riassume in modo pratico:
- cosa fa l’app
- come leggere le analisi
- quali sono le principali fonti dati e i componenti del sistema
- quali endpoint sono usati dalla dashboard

---

## Che cosa fa l’app
Questa applicazione analizza partite di calcio e fornisce indicazioni statistiche (non certezze) basate su dati reali ufficiali.

L’obiettivo è aiutare a prendere decisioni più consapevoli, mostrando:
- probabilità stimate dei mercati principali
- un indice di affidabilità (confidence)
- indicatori di forza e forma delle squadre
- insight sintetici come “Squadre da giocare”

---

## Come leggere le percentuali
Le percentuali non indicano cosa succederà con sicurezza, ma quanto un’analisi è supportata dai dati disponibili.

In generale:
- percentuali più alte: previsione più solida (a parità di contesto)
- percentuali più basse: scenario più incerto o dati meno stabili

---

## Principali mercati analizzati
- 1X2: esito finale della partita (1 / X / 2)
- Over / Under: numero totale di gol
- BTTS: entrambe le squadre segnano (YES / NO)

---

## Confidence e rischio
- Confidence: quanto è affidabile l’analisi (scala 0–100)
- Risk: quanto il match è imprevedibile (LOW / MEDIUM / HIGH)

Una previsione con alta confidence e basso rischio è generalmente più affidabile.

---

## Forza e forma delle squadre
L’app non si basa solo sulla classifica. Considera:
- forza statistica della squadra (team strength)
- aggiornamento Elo dopo ogni match
- forma recente (ultimi match)
- contesto e stabilità dei dati

---

## “Squadre da giocare”
La sezione “Squadre da giocare” mostra le squadre che, nel contesto attuale, risultano più solide e affidabili secondo i dati disponibili.

Nell’implementazione attuale l’insight usa:
- forza squadra (Elo) e
- forma recente (ultimi 8 match FINISHED)

---

## Principio: Real Data Only
Quando Real Data Only è attivo:
- il sistema usa esclusivamente match e risultati reali ufficiali
- non vengono generate partite fittizie
- le previsioni sono vincolate ai match presenti nel runtime store (seed da provider)

---

## Componenti del progetto (high level)

### API gateway
Servizio FastAPI che:
- carica/aggiorna partite dal provider dati
- espone endpoint per dashboard e automazioni
- gestisce cache/telemetria di runtime
- schedula refresh dei fixtures e rebuild dei rating (quando configurato)

Directory: [api_gateway/](file:///Users/prova/Desktop/Top%20Pronostici%20per%20Campionati%20Europei/forecast-master-system/api_gateway)

### Motore ML / logica predittiva
Modulo che produce probabilità e spiegazioni, con cache e misure di robustezza.

Directory: [ml_engine/](file:///Users/prova/Desktop/Top%20Pronostici%20per%20Campionati%20Europei/forecast-master-system/ml_engine)

### Dashboard
UI Next.js che visualizza:
- overview campionati, match da giocare, trend
- chart e metriche
- insight “Squadre da giocare”

Directory: [dashboard/](file:///Users/prova/Desktop/Top%20Pronostici%20per%20Campionati%20Europei/forecast-master-system/dashboard)

---

## Artefatti dati principali
- Team ratings: [data/team_ratings.json](file:///Users/prova/Desktop/Top%20Pronostici%20per%20Campionati%20Europei/forecast-master-system/data/team_ratings.json)

---

## Endpoint principali (API)
- GET /api/v1/system/status: stato provider e diagnostica runtime
- GET /api/v1/overview/championships: dati per la dashboard (campionati, matchday, match)
- POST /api/v1/predictions/batch: calcola previsioni per una lista di match
- GET /api/v1/live/{match_id}/probabilities: snapshot probabilità per un match
- GET /api/v1/accuracy/season-progress: andamento metriche recenti (es. ROC-AUC)
- GET /api/v1/accuracy/calibration-summary: riepilogo calibrazione
- GET /api/v1/insights/teams-to-play: insight Top 3 “Squadre da giocare”
- POST /api/v1/system/rebuild-ratings: rebuild manuale ratings (provider compatibili)

---

## Importante
L’app è uno strumento di supporto alle decisioni. Il calcio resta imprevedibile e nessuna analisi garantisce il risultato finale.

