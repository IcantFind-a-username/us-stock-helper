# Backend core

The backend is intentionally split into small Python boundaries so correctness
can be tested before deployment topology is chosen:

1. `information_layer` acquires and freezes cited, point-in-time evidence.
2. `analysis_core` computes completed-bar indicators, patterns, three-horizon
   scores, scenario ranges, and analysis-only risk plans.
3. `adviser_layer` validates the thirteen public style lenses as a bounded soft
   factor; it cannot replace facts or bypass hard gates.
4. `decision_engine` composes those three layers against one `as_of` cutoff.
5. `market_gateway` is the isolated, read-only moomoo OpenD boundary.

Python is the correct first production language because the workload is
research- and I/O-heavy, the numerical ecosystem is mature, and the current
implementation is small enough to audit. Vectorized NumPy/Polars is the next
step for measured batch bottlenecks. Rust is reserved for a profiled hot path,
not used speculatively.

No package contains a broker, account, trade context, or order-submission
interface.

## Verification

Run from the repository root:

```bash
PYTHONPATH=services/analysis_core \
  python3 -m unittest discover -s services/analysis_core/tests -v
PYTHONPATH=services/information_layer \
  python3 -m unittest discover -s services/information_layer/tests -v
PYTHONPATH=services/adviser_layer \
  python3 -m unittest discover -s services/adviser_layer/tests -v
PYTHONPATH=services/analysis_core:services/information_layer:services/adviser_layer:services/decision_engine \
  python3 -m unittest discover -s services/decision_engine/tests -v
PYTHONPATH=services/market_gateway/src:services/analysis_core \
  python3 -m unittest discover -s services/market_gateway/tests -v
```

Every decision-bearing object preserves `as_of`/`available_at` semantics.
Future or incomplete bars, post-cutoff revisions, unconfirmed rumors, stale
market snapshots, and stale/future short-borrow checks fail closed.
