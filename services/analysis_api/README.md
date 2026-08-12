# analysis_api

The read-only HTTP boundary for the point-in-time decision chain. It composes
`information_layer`, `analysis_core`, `adviser_layer` and `decision_engine`
behind two GET paths and turns their output into one JSON answer the app can
render.

## Safety invariants

- The path allowlist is exactly `GET /health` and `GET /decision`; every write
  method fails closed with 405.
- No field in any response can carry an order, an account or a credential, and
  the risk plan states in its own warnings that it cannot place one.
- Provider failures are replaced with a fixed message: their text can contain
  credentials.

## What the contract refuses to hide

The chain declines to state some things, and those refusals travel to the
screen rather than being smoothed over in serialization:

- `score.factorCoverage` and `score.unavailableFactors` — macro, geopolitical,
  institutional-flow and fundamental factors have no feed yet, so a score is
  explicitly partial rather than quietly averaging in judgements nobody made.
- `forecast: null` with a note — when realized volatility cannot be measured
  there is no honest width for a scenario range, and a band of no width shown
  as confidently as a measured one is worse than showing nothing.
- `status: "unavailable"` — no completed candles means no analysis, stated as
  such.

## Run tests

```bash
PYTHONPATH=services/analysis_api/src:services/analysis_api/tests:services/analysis_core:services/information_layer:services/adviser_layer:services/decision_engine \
  python3 -m unittest discover -s services/analysis_api/tests -v
```
