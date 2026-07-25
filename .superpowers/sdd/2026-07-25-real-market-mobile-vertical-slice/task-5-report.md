# Task 5 report: per-candle 100% participation bars

## Status

Implemented the approved per-candle order-size activity layer. Every rendered
completed candle receives one fixed-height participation slot with the same x
coordinate and width as its candle body. Live shares render as a 100% dark/light
stack; missing data renders as an outlined empty slot and is never treated as
zero or interpolated.

`PriceChart` now consumes `ChartSnapshot` internally. Existing demo-only
`StockSnapshot` callers cross the already-explicit `toDemoChartSnapshot`
adapter; live `forecast: null` renders historical candles only and does not
inherit a fixture forecast.

## TDD evidence

### RED

- Geometry RED: 6 expected failures. The old four-argument function shifted the
  new arguments into width/height, returned no participation geometry, and
  retained 201 candles instead of the latest 200.
- Component RED: both tests failed at the real `PriceChart` boundary with
  `TypeError: participationBars.map is not a function`, proving the component
  had not migrated to the chart snapshot interface.
- Null-forecast title RED: the live chart still rendered
  `价格 · 成交量 · 概率预测` instead of the requested history-only title.

### GREEN

- Focused geometry and component run: 2 suites, 13 tests passed.
- Geometry tests hand-check 16-point totals and 60/40 = 9.6/6.4 plus
  25/75 = 4/12 segment heights; they also cover one-to-one alignment, missing
  slots, cutoff rejection, participation-order isolation, and the 200-candle
  cap.
- Component tests render the real SVG and native `Pressable`; they cover one
  available stack, one missing outline, visible text legend, null forecast,
  44-point minimum interaction size, tap, long-press, and exact accessible
  selected-candle detail.

## Files

- `apps/mobile/src/domain/chart.ts`
- `apps/mobile/src/domain/__tests__/chart.test.ts`
- `apps/mobile/src/components/chart/PriceChart.tsx`
- `apps/mobile/src/components/chart/ChartLegend.tsx`
- `apps/mobile/src/components/chart/__tests__/PriceChart.test.tsx`

## Verification

- Node: `22.23.1`.
- Focused chart run: 2 suites, 13 tests passed.
- Full mobile run: 26 suites, 148 tests passed.
- `npm run typecheck`: exit 0.
- `npm run lint`: exit 0 with no warnings.
- `git diff --check`: clean.

## Self-review

- The participation geometry is keyed to candle close time but derives its
  order exclusively from the filtered candle series. Post-cutoff participation
  is unavailable.
- Available bars have a constant 16-point height and never consume `netFlow`;
  therefore the lane does not encode inflow/outflow or contain a zero axis.
- Missing, invalid, or unmatched bars retain a full outlined slot with zero
  segment geometry behind an explicit `available: false` discriminator.
- The dark and light Calm Alpha token colors have 5.29:1 and 9.44:1 contrast
  against the chart background and are supplemented by the always-visible
  `订单规模活动占比 · 深色主力代理 / 浅色散户代理` legend.
- The chart touch region is much larger than 44 points, uses native pressed
  opacity without layout movement, and reserves the detail strip before and
  after selection.
- Screen-reader output includes a chart summary and, after every selection,
  close time, OHLCV, exact shares or missing reason, coverage, source, and
  `非真实机构身份`.
- No new chart library, animation system, fixture fallback, or unrelated
  refactor was added.

## Concerns

None.

## Fix Round 1

### Status

Resolved all review findings. Chart geometry now receives the snapshot source
`decisionCutoff` explicitly and never derives availability from forecast
presence or `predictedAt`. Live snapshots with `forecast: null` remain
point-in-time filtered.

Selected participation detail now comes only from the geometry-approved,
sanitized projection. A post-cutoff row produces a fixed
`决策截止时不可用` state with no raw coverage, source, or reason metadata.

### TDD evidence

RED:

- The explicit-cutoff geometry run failed three expected cases: the old
  signature shifted width/height, post-cutoff geometry had no sanitized
  metadata, and a null-forecast live chart included a future candle.
- The first component RED showed zero filtered candles because `PriceChart`
  had not yet passed `source.decisionCutoff`.
- New component cases then exercised first/second x selection, null-forecast
  future exclusion, post-cutoff secret metadata, and stable long-reason detail.

GREEN:

- Focused geometry + `PriceChart`: 2 suites, 18 tests passed.
- Full mobile: 26 suites, 153 tests passed.
- Node `22.23.1` typecheck and lint both exited 0 with pristine output.
- `git diff --check` passed.

### Changes

- `buildChartGeometry` accepts `decisionCutoff` separately from
  `forecastOrNull`; candle and participation `availableAt` must be finite and
  no later than that cutoff.
- `ParticipationGeometry` carries only approved shares/coverage/source/reason.
  Rejected rows receive null metadata and a fixed safe missing reason.
- `PriceChart` passes `snapshot.source.decisionCutoff`, selects only filtered
  candle geometry, and renders detail only from sanitized participation
  geometry.
- `findNearestByX` has hand-derived boundary tests at 19.9, 20.0, and 20.1.
  Component taps inject x=0 and x=10000 to select the first and second candles;
  the native long-press path remains covered.
- The detail strip is always mounted with the same testable minimum-height
  container. Long participation reasons are visually capped at two lines with
  tail ellipsis while the parent accessibility label retains the full text.

### Self-review

- A future candle cannot affect candle count, selection, volume scale, or price
  range when forecast is null.
- Raw `snapshot.participationBars` is no longer consulted after selection.
- Post-cutoff coverage, source, and reason sentinel strings are absent from the
  selected accessibility label.
- Existing constant-height stacks, missing outlines, no-direction-axis
  semantics, legend copy, contrast, and non-identity disclaimer remain intact.
- Unrelated untracked plan files remain untouched and excluded.

### Concerns

None.
