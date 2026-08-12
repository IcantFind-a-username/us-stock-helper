# US Stock Helper

An evidence-first US stock research assistant. The first implemented foundation
is a transparent technical-indicator engine with:

- `td_nine_count`: a no-lookahead TD Setup / “神奇九转” implementation.
- `open_dragon_trend`: an independently designed, transparent trend-system
  alternative. It is not presented as a clone of any proprietary “神龙指标”.
- Per-indicator methodology and source references.
- Tests that reject accidental future-data dependence.

## Run tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Design rule

Paid functionality is evaluated by the useful job it performs, then implemented
from public rules or a legitimately supplied specification. The project does not
copy vendor source code, bypass subscriptions, or claim equivalence where the
underlying proprietary formula is unavailable.

See [the indicator methodology](docs/indicator-methodology.md) for the validation
and live-trading acceptance rules.

