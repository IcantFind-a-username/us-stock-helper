# US Stock Helper analysis core

This package is the deterministic, read-only analysis layer behind the app. It
does not scrape, authenticate with a broker, place an order, or claim a
guaranteed return. Inputs must come from an information layer that preserves
source URLs and point-in-time timestamps.

## Safety invariants

- Every timestamp is timezone-aware UTC. Naive or non-UTC datetimes fail
  closed.
- A decision cutoff (`as_of`) sees only complete bars whose `closed_at` and
  `available_at` are no later than the cutoff.
- News and other evidence are selected by `available_at`; the newest revision
  visible at the cutoff wins. Later corrections cannot rewrite an older
  decision snapshot.
- Mixed symbols or intervals are rejected during feature extraction. Evidence
  for another symbol is ignored.
- Frozen evidence packets include citations, conflicts, missing evidence types,
  a deterministic SHA-256 content hash, and an explicit method version.
- Risk preference changes only position/leverage limits. It cannot change the
  objective score or direction.
- Style advisers are a soft factor capped at ±3 score points. Hard gates such
  as stale data and unavailable short borrow always win.
- Forecasts are bear/base/bull probability ranges with explicit calibration
  status and invalidation conditions. There is no single promised target.
- Risk plans are pure immutable data. There is deliberately no broker client,
  order ID, or order-submission function.

## Implemented analysis

`indicators.py` provides MA5, EMA, Wilder RSI, and MACD. `patterns.py` provides
three-bar fractals, confirmed MA5 pullbacks, conservative double-bottom and
head-and-shoulders detections, plus an original generic sequential count named
“神奇九转” in the UI.

The sequential algorithm is `sequential-close-4-v1`: starting with the fifth
closed bar, compare each close with the close four bars earlier; count
consecutive comparisons in the same direction and confirm at nine. A rising
sequence is an exhaustion-risk signal and a falling sequence is a potential
reversal signal. This is an independently specified generic rule, not a copy
of a paid indicator or proprietary formula.

Three independent scoring configurations are provided:

- `short`: intraday through 5 trading days; emphasizes technical trend,
  momentum, news sentiment, and flow.
- `swing`: 1–8 weeks; balances trend, confirmed patterns, context, and company
  health.
- `long`: 2–24 months; gives more weight to fundamentals and macro context.

Market sentiment, macro conditions, geopolitics, institutional-flow estimates,
and adviser input remain named `FactorContribution` rows so a UI can explain
exactly how each soft factor changed a score.

## Basic flow

```python
from us_stock_helper_core import (
    Horizon,
    RiskPreference,
    build_risk_plan,
    build_scenario_forecast,
    extract_horizon_features,
    freeze_evidence_packet,
    score_horizon,
)

packet = freeze_evidence_packet("NVDA", as_of, evidence_records)
features = extract_horizon_features(
    Horizon.SHORT,
    bars,
    packet.citations,
    market_context,
    adviser_factor=0.2,
)
score = score_horizon(features, hard_gates=())
forecast = build_scenario_forecast(
    score,
    current_price=last_price,
    annualized_volatility=realized_volatility,
    invalidation_conditions=("Evidence thesis is invalidated.",),
    citation_ids=tuple(item.evidence_id for item in packet.citations),
)
plan = build_risk_plan(
    score,
    forecast,
    preference=RiskPreference.BALANCED,
)
```

The caller should produce separate, point-in-time bar series for all three
horizons and retain each resulting snapshot for later backtest/audit.

## Verification

The runtime has no third-party dependency:

```bash
cd services/analysis_core
PYTHONPATH=. python3 -m unittest discover -s tests -v
python3 -m compileall -q us_stock_helper_core tests
```

The suite covers future-bar injection, incomplete bars, revisions, shuffled
inputs, reproducibility at the same cutoff, cross-symbol contamination,
objective-score isolation from risk preference, bounded advisers, hard gates,
forecast uncertainty, and analysis-only plans.

## Performance roadmap

Start with this Python 3.11 standard-library implementation because correctness,
auditability, and iteration speed dominate at current scale. Measure production
latency and memory before changing the stack.

1. Batch requests and cache immutable evidence packets.
2. If profiling identifies dataframe/vector math as the bottleneck, add
   optional Polars or NumPy adapters behind the current typed interfaces.
3. Move only a demonstrated CPU hot path to Rust after profiling and parity
   tests. Do not rewrite orchestration, evidence handling, or business rules
   merely for theoretical speed.

Pattern outputs are conservative heuristics, not learned price predictors.
Calibration must remain `UNCALIBRATED` until a leakage-safe walk-forward
backtest has actually been run, and may be promoted only by the system that
owns that audit evidence.
