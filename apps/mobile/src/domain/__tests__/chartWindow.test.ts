import { expect, it } from "@jest/globals";

import type { Candle, ForecastSnapshot, ParticipationBar } from "@/domain/models";

import {
  buildChartGeometry,
  clampChartWindow,
  focusRatioForX,
  maxWindowBarsFor,
  minReadableBodyWidth,
  minWindowBars,
  minZoomedOutBodyWidth,
  panChartWindow,
  resolveChartWidth,
  zoomChartWindow,
  type ChartGeometryInput,
} from "../chart";

const total = 300;
const cutoff = "2026-07-24T20:00:00.000Z";

const candleAt = (index: number): Candle => {
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
};

/** A long rising series: every window has its own price range and its own bars. */
const manyCandles: Candle[] = Array.from({ length: total }, (_, index) =>
  candleAt(index),
);

/** The same series after two more bars closed while the chart stayed open. */
const grownCandles: Candle[] = Array.from({ length: total + 2 }, (_, index) =>
  candleAt(index),
);

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
    expect(geometry.window.size).toBeLessThanOrEqual(maxWindowBarsFor(resolveChartWidth(390)));
    expect(geometry.candles).toHaveLength(geometry.window.size);
  });
});

it("keeps the rest of the series in reach instead of drawing all of it", () => {
  const geometry = geometryFor();

  expect(geometry.window.total).toBe(total);
  expect(geometry.candles.length).toBeLessThan(total);
  // 334px of chart leaves 282px of plot; 4px bodies at 0.55 of the step cap the
  // window at 38 bars.
  expect(geometry.candles).toHaveLength(38);
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
  expect(geometry.candles).toHaveLength(36);
});

it("zooms around the pinch centre instead of around the newest bar", () => {
  const before = { size: 100, offset: 100, total };
  const focusRatio = 0.25;
  const focusBar = before.offset + focusRatio * before.size;

  const zoomedIn = zoomChartWindow({
    window: before,
    total,
    scale: 2,
    focusRatio,
    width: resolveChartWidth(390),
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
    width: resolveChartWidth(390),
  });

  // The ceiling is derived from the density floor, so it depends on width.
  expect(zoomedOut.size).toBe(maxWindowBarsFor(resolveChartWidth(390)));
  expect(
    Math.abs(zoomedOut.offset + focusRatio * zoomedOut.size - focusBar),
  ).toBeLessThanOrEqual(0.5);

  // Pinching around the middle divides evenly, so this one has to land exactly.
  const centred = zoomChartWindow({
    window: before,
    total,
    scale: 2,
    focusRatio: 0.5,
    width: resolveChartWidth(390)
  });
  expect(centred).toEqual({ size: 50, offset: 125, total });
});

it("holds the zoom between a readable and a whole-screen window", () => {
  const tightest = zoomChartWindow({
    window: { size: 60, offset: 100, total },
    total,
    scale: 40,
    focusRatio: 0.5,
    width: resolveChartWidth(390),
  });
  const widest = zoomChartWindow({
    window: { size: 60, offset: 100, total },
    total,
    scale: 0.01,
    focusRatio: 0.5,
    width: resolveChartWidth(390),
  });

  expect(minWindowBars).toBe(30);
  // Derived from the density floor rather than picked: a hand-chosen 200 put
  // the body back at one pixel, which is where this started.
  expect(maxWindowBarsFor(resolveChartWidth(390))).toBeGreaterThan(minWindowBars);
  expect(tightest.size).toBe(minWindowBars);
  expect(widest.size).toBe(maxWindowBarsFor(resolveChartWidth(390)));
  expect(widest.offset).toBeGreaterThanOrEqual(0);
  expect(widest.offset + widest.size).toBeLessThanOrEqual(total);
});

it("never zooms out past the data that exists", () => {
  const zoomed = zoomChartWindow({
    window: { size: 40, offset: 0, total: 45 },
    total: 45,
    scale: 0.1,
    focusRatio: 0.5,
    width: resolveChartWidth(390),
  });

  expect(zoomed.size).toBe(45);
  expect(zoomed.offset).toBe(0);
  expect(zoomed.total).toBe(45);
});

it("stops the drag at both ends of the series", () => {
  const current = { size: 60, offset: 100, total };

  expect(panChartWindow({ window: current, total, barDelta: -10_000 })).toEqual({
    size: 60,
    offset: 0,
    total,
  });
  expect(panChartWindow({ window: current, total, barDelta: 10_000 })).toEqual({
    size: 60,
    offset: total - 60,
    total,
  });
  expect(panChartWindow({ window: current, total, barDelta: -12.4 })).toEqual({
    size: 60,
    offset: 88,
    total,
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
    total: 45,
  });
  expect(clampChartWindow({ size: 60, offset: -20 }, total)).toEqual({
    size: 60,
    offset: 0,
    total,
  });
  expect(clampChartWindow({ size: 60, offset: 999 }, total)).toEqual({
    size: 60,
    offset: total - 60,
    total,
  });
});

it("moves every panel with the price window, not just the candles", () => {
  const window = { size: 40, offset: 120, total };
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
  const early = geometryFor({ window: { size: 40, offset: 0, total } });
  const late = geometryFor({ window: { size: 40, offset: 260, total } });

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
    window: { size: 40, offset: 0, total },
    panels: ["volume"],
  });
  const late = geometryFor({
    window: { size: 40, offset: 260, total },
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
  const latest = geometryFor({ forecast, window: { size: 40, offset: 260, total } });
  const history = geometryFor({ forecast, window: { size: 40, offset: 100, total } });

  expect(latest.forecastPoints).toHaveLength(2);
  expect(latest.band50).toMatch(/^M /);
  // A band drawn after a bar from the middle of the series would claim the
  // model forecast from there, which it never did.
  expect(history.forecastPoints).toEqual([]);
  expect(history.band50).toBe("");
  expect(history.band80).toBe("");
  expect(history.medianPath).toBe("");
});

it("spaces the time labels for the width and keeps them off the plot edges", () => {
  phoneWidths.forEach((viewportWidth) => {
    const geometry = geometryFor({ width: resolveChartWidth(viewportWidth) });
    const xs = geometry.timeAxis.map(({ x }) => x);

    expect(geometry.timeAxis.length).toBeGreaterThanOrEqual(3);
    expect(geometry.timeAxis.length).toBeLessThanOrEqual(6);
    // A centred "04:59" is about 22pt wide, so a label on the first or last bar
    // hangs off the plot and gets clipped by the price gutter.
    expect(Math.min(...xs)).toBeGreaterThan(geometry.plotLeft + 11);
    expect(Math.max(...xs)).toBeLessThan(geometry.plotRight - 11);
    geometry.timeAxis.forEach((label, index) => {
      const candle = geometry.candles.find(
        ({ timestamp }) => timestamp === label.timestamp,
      );
      expect(candle?.x).toBe(label.x);
      if (index > 0) expect(label.x).toBeGreaterThan(xs[index - 1]!);
    });
  });
});

it("keeps following the newest bar when two more bars close", () => {
  const opening = geometryFor({ forecast });
  expect(opening.forecastPoints).toHaveLength(2);
  expect(opening.window.total).toBe(total);

  const after = geometryFor({
    candles: grownCandles,
    forecast,
    window: opening.window,
  });

  // An offset counted from the oldest bar names a different slice after every
  // refresh: the window that was sitting on the newest bar quietly stopped
  // being on it, and the forecast — only ever drawn where the series ends —
  // vanished with no reader action and no message.
  expect(after.window.total).toBe(total + 2);
  expect(after.window.offset + after.window.size).toBe(total + 2);
  expect(after.candles.at(-1)!.sourceIndex).toBe(total + 1);
  expect(after.forecastPoints).toHaveLength(2);
  expect(after.band50).toMatch(/^M /);
});

it("leaves a window parked in history on the bars it was showing", () => {
  const parked = geometryFor({ forecast, window: { size: 40, offset: 100, total } });

  const after = geometryFor({
    candles: grownCandles,
    forecast,
    window: parked.window,
  });

  // Following the newest bar is for the reader standing at the live edge. One
  // who dragged back to a specific hour keeps that hour, and keeps being told
  // the forecast does not belong there.
  expect(after.candles[0]!.sourceIndex).toBe(100);
  expect(after.candles.at(-1)!.sourceIndex).toBe(139);
  expect(after.forecastPoints).toEqual([]);
});

it("re-clamps a window whose series came back shorter", () => {
  const parked = geometryFor({ window: { size: 40, offset: 240, total } });

  const after = geometryFor({
    candles: manyCandles.slice(0, 120),
    window: parked.window,
  });

  expect(after.window.total).toBe(120);
  expect(after.window.offset + after.window.size).toBeLessThanOrEqual(120);
  expect(after.candles).toHaveLength(40);
});

it("narrows a window the new width can no longer draw readably", () => {
  const landscape = resolveChartWidth(844);
  const portrait = resolveChartWidth(375);
  const wide = geometryFor({
    width: landscape,
    window: { size: maxWindowBarsFor(landscape), offset: 0, total },
  });

  // Rotating back is not consent to hairlines: 228 bars that read on a tablet
  // width draw a 0.7px body on a phone, body and wick the same size.
  const narrow = geometryFor({ width: portrait, window: wide.window });

  expect(wide.window.size).toBeGreaterThan(maxWindowBarsFor(portrait));
  expect(narrow.window.size).toBe(maxWindowBarsFor(portrait));
  expect(narrow.candles[0]!.bodyWidth).toBeGreaterThanOrEqual(
    minZoomedOutBodyWidth,
  );
});

it("reports an empty window rather than one bar over an empty series", () => {
  // "Zero bars passed the cutoff" and "one bar is on screen" are different
  // facts, and a window of one over an empty series states the second.
  expect(clampChartWindow({ size: 40, offset: 0 }, 0)).toEqual({
    size: 0,
    offset: 0,
    total: 0,
  });
  expect(geometryFor({ candles: [] }).window).toEqual({
    size: 0,
    offset: 0,
    total: 0,
  });
});

it("ignores a gesture that reports a non-finite scale or distance", () => {
  const current = { size: 60, offset: 100, total };

  expect(
    zoomChartWindow({
      window: current,
      total,
      scale: Number.NaN,
      focusRatio: Number.NaN,
      width: resolveChartWidth(390),
    }),
  ).toEqual(current);
  expect(
    panChartWindow({ window: current, total, barDelta: Number.NaN }),
  ).toEqual(current);
});

it("cannot pinch a series shorter than the tightest window apart any further", () => {
  const short = { size: 12, offset: 0, total: 12 };

  expect(
    zoomChartWindow({
      window: short,
      total: 12,
      scale: 8,
      focusRatio: 0.5,
      width: resolveChartWidth(390),
    }),
  ).toEqual(short);
});

it("never zooms out into the hairlines the default window exists to avoid", () => {
  // Pinching out is the reader asking for more history, not for a chart he can
  // no longer read. At 200 bars on a 390pt phone the body measured 1.00px —
  // body and wick the same width in the same colour, which is precisely the
  // state the default window was solved away from.
  phoneWidths.forEach((viewportWidth) => {
    const geometry = geometryFor({
      width: resolveChartWidth(viewportWidth),
      window: {
        size: maxWindowBarsFor(resolveChartWidth(viewportWidth)),
        offset: 0,
        total,
      },
    });

    expect(geometry.candles[0]!.bodyWidth).toBeGreaterThanOrEqual(
      minZoomedOutBodyWidth,
    );
  });
});
