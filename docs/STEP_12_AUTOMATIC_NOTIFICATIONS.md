# STEP 12 — Notifiche automatiche

## Obiettivo
Inviare notifiche automatiche quando emergono condizioni “interessanti” (insight, cambiamenti significativi, eventi live), senza trasformare l’app in un sistema invasivo o rumoroso.

---

## Principi
- Opt-in: l’utente sceglie cosa ricevere e con che frequenza.
- Rate limit: nessun flood di notifiche in caso di refresh frequenti.
- Trasparenza: ogni notifica spiega perché è stata inviata (regola + soglia).
- Real Data Only: trigger basati su dati reali (match/risultati) e output dei modelli.

---

## Trigger consigliati

### 1) Value Pick (STEP 11)
Invia quando:
- `value_level` passa a HIGH oppure
- `value_index` supera una soglia configurabile

Payload minimo:
- match, mercato, quota, implied, success, value_index, value_level

---

### 2) Match ad alta confidence
Invia quando:
- `confidence` del match supera soglia (es. 80/100) e
- match è entro una finestra temporale (es. nelle prossime 24h)

---

### 3) Insight “Squadre da giocare”
Invia quando:
- cambia la Top 1 del campionato selezionato oppure
- la `success_pct` della Top 1 supera una soglia (es. 75%)

---

### 4) Live update (solo se attivo LIVE)
Invia quando:
- goal rosso/rigore/eventi importanti (se disponibili nel provider) oppure
- variazione forte di probabilità in un breve intervallo

---

## Canali
Canali suggeriti (implementabili in fasi):
- Webhook (generico): POST verso URL configurato
- Telegram bot (opzionale)
- Email (opzionale)
- Push (fase successiva, se si introduce un layer mobile/PWA)

---

## Preferenze utente (modello dati)
Campi tipici:
- `enabled` (bool)
- `channels` (lista canali attivi)
- `quiet_hours` (fascia oraria di silenzio)
- `max_per_day` e/o `min_interval_minutes`
- `filters` per campionato, mercato, soglie

Persistenza consigliata:
- file JSON locale (semplice) oppure
- tabella SQLite (se già presente runtime storage e si vuole multi-setting)

---

## Deduplica e antispam
Strategie:
- chiave notifica: `(type, match_id, market, level, day)`
- TTL: non reinviare lo stesso evento entro X ore
- soglie con hysteresis: invia solo se supera soglia + delta (es. +2 punti) per evitare oscillazioni

---

## Architettura (coerente con l’attuale progetto)
Approccio consigliato:
- job periodico in background (simile ai scheduler già presenti)
- calcolo “trigger candidates” leggendo:
  - store match runtime (probabilità/confidence)
  - insight endpoint (teams-to-play)
  - quote (se disponibili)
- invio via “notifier service” con adapter per canale

---

## API suggerite (opzionali)
- GET /api/v1/notifications/settings
- PUT /api/v1/notifications/settings
- GET /api/v1/notifications/preview (simula e restituisce notifiche che verrebbero inviate)
- GET /api/v1/notifications/history (ultime notifiche inviate)

---

## UI
Elementi UI utili:
- toggle generale “Notifiche”
- selettore canale (Webhook/Telegram/Email)
- filtri per campionato e mercati
- slider soglie (Value Index, Confidence)
- schermata “Cronologia notifiche”

