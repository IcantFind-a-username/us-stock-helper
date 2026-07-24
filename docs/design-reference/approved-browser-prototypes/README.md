# Approved Browser Prototypes

These files are the browser prototypes that the user reviewed and approved
before the native iPhone implementation began. They are now versioned so local
and cloud Codex sessions share the same visual source of truth.

## Authority

- `ios-dashboard-demo-v1.html`: Dashboard hierarchy, density, and visual tone.
- `ios-stock-detail-demo-v1.html`: stock-detail composition and portrait
  indicator presentation.
- `kline-and-macro-context-v2.html`: professional candlestick treatment,
  RSI/MACD visibility, ownership/participation views, forecasts, and
  macro/geopolitical context.
- `advisor-architecture-v2.html`: approved adviser/evidence/risk-plan
  architecture and visual presentation.
- `advisor-architecture.html`: earlier adviser exploration retained for
  provenance.
- `design-approved-waiting.html`: records the visual-approval checkpoint.

The React Native implementation should translate these designs into native
components. It must not embed the HTML in a WebView, reproduce browser/device
chrome, or copy proprietary assets from third-party trading apps.

Functional and safety requirements remain authoritative in:

- `docs/superpowers/specs/2026-07-24-us-stock-helper-product-design.md`
- `docs/superpowers/plans/2026-07-24-iphone-product-demo.md`

When more evidence must be exposed than fits the approved compact layout, use
progressive disclosure through a sheet or detail screen rather than expanding
the Dashboard into a long report.
