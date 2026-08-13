import { expect, it } from "@jest/globals";

import type { Candle, ForecastSnapshot, ParticipationBar } from "@/domain/models";

import {
  buildChartGeometry,
  clampChartWindow,
  focusRatioForX,
  maxWindowBars,
  minReadableBodyWidth,
  minWindowBars,
  panChartWindow,
  resolveChartWidth,
  zoomChartWindow,
  type ChartGeometryInput,
} from "../chart";

const total = 300;
const cutoff = "2026-07-24T20:00:00.000Z";

/** A long rising series: every window has its own price range and its own bars. */
const manyCandles: Candle[] = Array.from({ length: total }, (_, index) => {
  const timestamp = new Date(Date.UTC(2026, 6, 24, 0, index)).toISOString();
  return {
    timestamp,
    availableAt: new Date(Date.parse(timestamp) + 1_000).toISOString(),
    complete: true,
    open: 100 + index,
    high: 102 + index,
    low: 99 + index,
    close: 101 + index,
    volume: 1_000 + index,
  };
});

const participationBars: ParticipationBar[] = manyCandles.map((candle, index) => ({
  closedAt: candle.timestamp,
  mainShare: 0.6,
  retailShare: 0.4,
  mainActivity: 120,
  retailActivity: 80,
  netFlow: index,
  coverage: 1,
  source: "moomoo",
  asOf: candle.timestamp,
  availableAt: candle.availableAt,
  methodVersion: "order-size-activity-share-v1",
  qualityStatus: "live",
  missingReason: null,
}));

const forecast: ForecastSnapshot = {
  horizon: "未来 2 个交易日",
  points: [
    {
      timestamp: "T+1",
      median: 402,
      lower50: 401,
      upper50: 403,
      lower80: 400,
      upper80: 404,
    },
    {
      timestamp: "T+2",
      median: 403,
      lower50: 402,
      upper50: 404,
      lower80: 401,
      upper80: 405,
    },
  ],
  probability: { up: 0.55, flat: 0.2, down: 0.25 },
  calibrationError: 0.1,
  predictedAt: cutoff,
  modelVersion: "test",
  invalidation: "跌破 99",
};

function geometryFor(overrides: Partial<ChartGeometryInput> = {}) {
  return buildChartGeometry({
    candles: manyCandles,
    forecast: null,
    participationBars: [],
    decisionCutoff: cutoff,
    width: resolveChartWidth(390),
    height: 460,
    ...overrides,
  });
}

// Real portrait widths: SE/13 mini, 13/14, 14 Pro/15, 16 Pro, 15 Pro Max, 16 Pro Max.
const phoneWidths = [375, 390, 393, 402, 430, 440];

it("draws a body wide enough to read direction on every real phone width", () => {
  phoneWidths.forEach((viewportWidth) => {
    const geometry = geometryFor({ width: resolveChartWidth(viewportWidth) });

    // A 1px body next to a 1px wick in the same colour is not a candle.
    expect(geometry.candles[0]!.bodyWidth).toBeGreaterThanOrEqual(
      minReadableBodyWidth,
    );
    expect(geometry.window.size).toBeGreaterThanOrEqual(minWindowBars);
    expect(geometry.window.size).toBeLessThanOrEqual(maxWindowBars);
    expect(geometry.candles).toHaveLength(geometry.window.size);
  });
});

it("keeps the rest of the series in reach instead of drawing all of it", () => {
  const geometry = geometryFor();

  expect(geometry.window.total).toBe(total);
  expect(geometry.candles.length).toBeLessThan(total);
  // 334px of chart leaves 282px of plot; 3px bodies at 0.62 of the step cap the
  // window at 58 bars.
  expect(geometry.candles).toHaveLength(58);
});

it("opens on the newest bar, not on the oldest", () => {
  const geometry = geometryFor();

  expect(geometry.window.offset).toBe(total - geometry.window.size);
  expect(geometry.candles.at(-1)!.sourceIndex).toBe(total - 1);
  expect(geometry.candles[0]!.sourceIndex).toBe(total - geometry.window.size);
});

it("leaves room for the forecast slots so the bodies stay readable", () => {
  const geometry = geometryFor({ forecast });

  expect(geometry.forecastPoints).toHaveLength(2);
  expect(geometry.candles[0]!.bodyWidth).toBeGreaterThanOrEqual(
    minReadableBodyWidth,
  );
  expect(geometry.candles).toHaveLength(56);
});

it("zooms around the pinch centre instead of around the newest bar", () => {
  const before = { size: 100, offset: 100 };
  const focusRatio = 0.25;
  const focusBar = before.offset + focusRatio * before.size;

  const zoomedIn = zoomChartWindow({
    window: before,
    total,
    scale: 2,
    focusRatio,
  });

  expect(zoomedIn.size).toBe(50);
  // The bar under the fingers stays under the fingers. Offsets are whole bars,
  // so half a bar is the most the anchor can drift.
  expect(
    Math.abs(zoomedIn.offset + focusRatio * zoomedIn.size - focusBar),
  ).toBeLessThanOrEqual(0.5);
  // Neither of the two ways to get the size right and the anchor wrong.
  expect(zoomedIn.offset).not.toBe(before.offset);
  expect(zoomedIn.offset).not.toBe(total - zoomedIn.size);

  const zoomedOut = zoomChartWindow({
    window: before,
    total,
    scale: 0.5,
    focusRatio,
  });

  expect(zoomedOut.size).toBe(200);
  expect(
    Math.abs(zoomedOut.offset + focusRatio * zoomedOut.size - focusBar),
  ).toBeLessThanOrEqual(0.5);

  // Pinching around the middle divides evenly, so this one has to land exactly.
  const centred = zoomChartWindow({
    window: before,
    total,
    scale: 2,
    focusRatio: 0.5,
  });
  expect(centred).toEqual({ size: 50, offset: 125 });
});

it("holds the zoom between a readable and a whole-screen window", () => {
  const tightest = zoomChartWindow({
    window: { size: 60, offset: 100 },
    total,
    scale: 40,
    focusRatio: 0.5,
  });
  const widest = zoomChartWindow({
    window: { size: 60, offset: 100 },
    total,
    scale: 0.01,
    focusRatio: 0.5,
  });

  expect(minWindowBars).toBe(30);
  expect(maxWindowBars).toBe(200);
  expect(tightest.size).toBe(minWindowBars);
  expect(widest.size).toBe(maxWindowBars);
  expect(widest.offset).toBeGreaterThanOrEqual(0);
  expect(widest.offset + widest.size).toBeLessThanOrEqual(total);
});

it("never zooms out past the data that exists", () => {
  const zoomed = zoomChartWindow({
    window: { size: 40, offset: 0 },
    total: 45,
    scale: 0.1,
    focusRatio: 0.5,
  });

  expect(zoomed.size).toBe(45);
  expect(zoomed.offset).toBe(0);
});

it("stops the drag at both ends of the series", () => {
  const current = { size: 60, offset: 100 };

  expect(panChartWindow({ window: current, total, barDelta: -10_000 })).toEqual({
    size: 60,
    offset: 0,
  });
  expect(panChartWindow({ window: current, total, barDelta: 10_000 })).toEqual({
    size: 60,
    offset: total - 60,
  });
  expect(panChartWindow({ window: current, total, barDelta: -12.4 })).toEqual({
    size: 60,
    offset: 88,
  });
});

it("reads a pinch centre as a share of the plot and never outside it", () => {
  expect(focusRatioForX({ x: 8, plotLeft: 8, plotRight: 290 })).toBe(0);
  expect(focusRatioForX({ x: 290, plotLeft: 8, plotRight: 290 })).toBe(1);
  expect(focusRatioForX({ x: 149, plotLeft: 8, plotRight: 290 })).toBeCloseTo(0.5, 10);
  expect(focusRatioForX({ x: -400, plotLeft: 8, plotRight: 290 })).toBe(0);
  expect(focusRatioForX({ x: 4_000, plotLeft: 8, plotRight: 290 })).toBe(1);
  // A degenerate plot has no centre to speak of; the middle is the honest answer.
  expect(focusRatioForX({ x: 12, plotLeft: 8, plotRight: 8 })).toBe(0.5);
});

it("clamps a window that asks for more bars than the series has", () => {
  expect(clampChartWindow({ size: 500, offset: 40 }, 45)).toEqual({
    size: 45,
    offset: 0,
  });
  expect(clampChartWindow({ size: 60, offset: -20 }, total)).toEqual({
    size: 60,
    offset: 0,
  });
  expect(clampChartWindow({ size: 60, offset: 999 }, total)).toEqual({
    size: 60,
    offset: total - 60,
  });
});

it("moves every panel with the price window, not just the candles", () => {
  const window = { size: 40, offset: 120 };
  const geometry = geometryFor({
    window,
    participationBars,
    panels: ["volume", "macd", "rsi", "participation"],
    overlays: [
      {
        key: "ma5",
        label: "MA5",
        values: manyCandles.map((_, index) => 100 + index),
      },
    ],
    macdSeries: {
      line: manyCandles.map((_, index) => index / 100),
      signal: manyCandles.map((_, index) => index / 200),
      histogram: manyCandles.map((_, index) => (index % 7) - 3),
    },
    rsiSeries: { values: manyCandles.map((_, index) => 30 + (index % 40)) },
  });

  const xs = geometry.candles.map(({ x }) => x);
  expect(geometry.candles).toHaveLength(40);
  expect(geometry.candles[0]!.sourceIndex).toBe(120);

  expect(geometry.participation.map(({ timestamp }) => timestamp)).toEqual(
    geometry.candles.map(({ timestamp }) => timestamp),
  );
  expect(geometry.participation.map(({ x }) => x)).toEqual(xs);
  expect(geometry.macd!.bars.map(({ x }) => x)).toEqual(xs);
  expect(geometry.rsi!.points.map(({ x }) => x)).toEqual(xs);
  expect(geometry.overlays[0]!.points.map(({ x }) => x)).toEqual(xs);
  // Series values stay welded to the bar the server indexed them against.
  expect(geometry.overlays[0]!.points[0]!.value).toBe(220);
  expect(geometry.rsi!.points[0]!.value).toBe(30 + (120 % 40));
  expect(geometry.macd!.bars).toHaveLength(40);
  expect(geometry.candles.every(({ volumeHeight }) => volumeHeight > 0)).toBe(true);
});

it("rescales the price axis for the window in view", () => {
  const early = geometryFor({ window: { size: 40, offset: 0 } });
  const late = geometryFor({ window: { size: 40, offset: 260 } });

  const visibleHigh = (geometry: typeof early) =>
    Math.max(...geometry.candles.map(({ wickTop }) => wickTop));

  expect(early.priceMax).toBeLessThan(late.priceMin);
  // 40 rising bars span 42 dollars; a 300-bar axis would flatten them to a line.
  expect(early.priceMax - early.priceMin).toBeLessThan(60);
  expect(late.priceMax).toBeGreaterThanOrEqual(102 + 299);
  expect(late.priceMin).toBeLessThanOrEqual(99 + 260);
  expect(visibleHigh(early)).toBeGreaterThan(early.panels.price.top);
  // Both windows use the full panel height, so neither reads as a flat line.
  const spread = (geometry: typeof early) =>
    Math.max(...geometry.candles.map(({ wickBottom }) => wickBottom)) -
    Math.min(...geometry.candles.map(({ wickTop }) => wickTop));
  expect(spread(early)).toBeCloseTo(spread(late), 6);
  expect(spread(early)).toBeGreaterThan(
    (early.panels.price.bottom - early.panels.price.top) * 0.8,
  );
});

it("keeps the volume panel on the window's own busiest bar", () => {
  const early = geometryFor({
    window: { size: 40, offset: 0 },
    panels: ["volume"],
  });
  const late = geometryFor({
    window: { size: 40, offset: 260 },
    panels: ["volume"],
  });

  expect(early.candles).toHaveLength(40);
  expect(late.candles).toHaveLength(40);
  const panelHeight = (geometry: typeof early) =>
    geometry.panels.volume!.bottom - geometry.panels.volume!.top;
  const tallest = (geometry: typeof early) =>
    Math.max(...geometry.candles.map(({ volumeHeight }) => volumeHeight));
  // Normalised against the whole series, the quiet early window would draw as a
  // row of stumps against the newest window's taller bars.
  expect(tallest(early)).toBeCloseTo(panelHeight(early), 6);
  expect(tallest(late)).toBeCloseTo(panelHeight(late), 6);
});

it("stops continuing the forecast once the newest bar is off screen", () => {
  const latest = geometryFor({ forecast, window: { size: 40, offset: 260 } });
  const history = geometryFor({ forecast, window: { size: 40, offset: 100 } });

  expect(latest.forecastPoints).toHaveLength(2);
  expect(latest.band50).toMatch(/^M /);
  // A band drawn after a bar from the middle of the series would claim the
  // model forecast from there, which it never did.
  expect(history.forecastPoints).toEqual([]);
  expect(history.band50).toBe("");
  expect(history.band80).toBe("");
  expect(history.medianPath).toBe("");
});
