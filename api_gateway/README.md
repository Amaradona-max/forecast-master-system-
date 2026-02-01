

## Similarity Buckets (Context Reliability “match simili”)

La dashboard può mostrare un badge **Simili XX%** basato su bucket:
`championship | tier | chaos_bucket | fragility_level`.

Il gateway legge (opzionale):
- `api_gateway/data/similarity_buckets.json`

Per generarlo da uno storico match-level (JSONL/JSON) usa:

```bash
python api_gateway/scripts/build_similarity_buckets.py \
  --input api_gateway/data/backtest_events.jsonl \
  --output api_gateway/data/similarity_buckets.json \
  --min-samples 50
```

Schema minimo per record:
- `championship`, `tier`, `chaos_index` (0..100), `fragility_level`, `hit` (bool)

Se il file è vuoto o mancante, la feature si disabilita automaticamente.


## Offline evaluation: prediction log → backtest_events.jsonl

Per generare automaticamente lo storico **match-level** (usato da Step 8/7):

1) Abilita logging predizioni (solo quando ti serve):
```bash
export PREDICTION_LOG_ENABLE=1
```

Le chiamate a `/api/v1/predictions/batch` scriveranno:
- `api_gateway/data/prediction_events.jsonl`

2) Fornisci i risultati reali (esempio):
`api_gateway/data/match_results.jsonl` con record tipo:
```json
{"match_id":"123","outcome":"home_win"}
```
oppure:
```json
{"match_id":"123","home_goals":2,"away_goals":1}
```

3) Crea `backtest_events.jsonl`:
```bash
python api_gateway/scripts/build_backtest_events_from_logs.py \
  --pred api_gateway/data/prediction_events.jsonl \
  --results api_gateway/data/match_results.jsonl \
  --out api_gateway/data/backtest_events.jsonl \
  --min-tier B
```

4) Da `backtest_events.jsonl` genera i bucket:
```bash
python api_gateway/scripts/build_similarity_buckets.py \
  --input api_gateway/data/backtest_events.jsonl \
  --output api_gateway/data/similarity_buckets.json \
  --min-samples 50
```
