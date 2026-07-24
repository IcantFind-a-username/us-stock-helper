# Decision engine

This package is the narrow orchestration boundary between the information,
analysis, adviser, and risk layers. It does not fetch data, call an LLM, hold
broker credentials, or place orders.

The engine freezes an evidence packet at `as_of`, lets only confirmed
actionable clusters affect the score, computes a deterministic baseline,
validates any optional adviser outputs against the same packet, applies their
bounded soft adjustment, produces uncalibrated scenario ranges, and finally
builds an analysis-only risk plan. Automatic evidence, market-data freshness,
and short-borrow gates fail closed.

```bash
PYTHONPATH=services/analysis_core:services/information_layer:services/adviser_layer:services/decision_engine \
  python3 -m unittest discover -s services/decision_engine/tests -v
```
