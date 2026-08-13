import { expect, it } from "@jest/globals";

import type {
  Candle,
  ForecastSnapshot,
  ParticipationBar,
} from "@/domain/models";

import {
  buildChartGeometry,
  findNearestByX,
  resolveChartWidth,
  type ChartGeometryInput,
} from "../chart";

const candles: Candle[] = [
  {
    timestamp: "2026-07-24T09:30:00-04:00",
    availableAt: "2026-07-24T09:30:01-04:00",
    complete: true,
    open: 100,
    high: 104,
    low: 99,
    close: 103,
    volume: 1_000,
  },
  {
    timestamp: "2026-07-24T09:35:00-04:00",
    availableAt: "2026-07-24T09:35:01-04:00",
    complete: true,
    open: 103,
    high: 105,
    low: 101,
    close: 102,
    volume: 2_000,
  },
];

const forecast: ForecastSnapshot = {
  horizon: "未来 2 个交易日",
  points: [
    {
      timestamp: "T+1",
      median: 104,
      lower50: 102,
      upper50: 106,
      lower80: 100,
      upper80: 108,
    },
    {
      timestamp: "T+2",
      median: 105,
      lower50: 103,
      upper50: 107,
      lower80: 99,
      upper80: 110,
    },
  ],
  probability: { up: 0.55, flat: 0.2, down: 0.25 },
  calibrationError: 0.1,
  predictedAt: "2026-07-24T10:00:00-04:00",
  modelVersion: "test",
  invalidation: "跌破 99",
};
const decisionCutoff = forecast.predictedAt;

const participationBars: ParticipationBar[] = [
  {
    closedAt: candles[0]!.timestamp,
    mainShare: 0.6,
    retailShare: 0.4,
    mainActivity: 120,
    retailActivity: 80,
    netFlow: -20,
    coverage: 1,
    source: "moomoo",
    asOf: candles[0]!.timestamp,
    availableAt: candles[0]!.availableAt,
    methodVersion: "order-size-activity-share-v1",
    qualityStatus: "live",
    missingReason: null,
  },
  {
    closedAt: candles[1]!.timestamp,
    mainShare: 0.25,
    retailShare: 0.75,
    mainActivity: 50,
    retailActivity: 150,
    netFlow: 30,
    coverage: 1,
    source: "moomoo",
    asOf: candles[1]!.timestamp,
    availableAt: candles[1]!.availableAt,
    methodVersion: "order-size-activity-share-v1",
    qualityStatus: "live",
    missingReason: null,
  },
];

function geometryFor(overrides: Partial<ChartGeometryInput> = {}) {
  return buildChartGeometry({
    candles,
    forecast,
    participationBars,
    decisionCutoff,
    width: 360,
    height: 250,
    ...overrides,
  });
}

/** Bars that straddle an overnight close, the shape that produced the blank. */
const overnightCandles: Candle[] = [
  "2026-07-23T19:50:00.000Z",
  "2026-07-23T19:55:00.000Z",
  "2026-07-24T13:35:00.000Z",
  "2026-07-24T13:40:00.000Z",
].map((timestamp, index) => ({
  timestamp,
  availableAt: new Date(Date.parse(timestamp) + 1_000).toISOString(),
  complete: true,
  open: 100 + index,
  high: 104 + index,
  low: 99 + index,
  close: 103 + index,
  volume: 1_000 + index,
}));

const overnightInput: ChartGeometryInput = {
  candles: overnightCandles,
  forecast: null,
  participationBars: [],
  decisionCutoff: "2026-07-24T14:00:00.000Z",
  width: 360,
  height: 250,
};

it("spaces every candle by one ordinal step across an overnight close", () => {
  const geometry = buildChartGeometry(overnightInput);

  expect(geometry.candles).toHaveLength(4);
  const gaps = geometry.candles
    .slice(1)
    .map((candle, index) => candle.x - geometry.candles[index]!.x);
  gaps.forEach((gap) => expect(gap).toBeCloseTo(geometry.step, 10));
  // The closed session must not consume plot width: the four bars fill it.
  expect(geometry.candles[0]!.x).toBeCloseTo(
    geometry.plotLeft + geometry.step / 2,
    10,
  );
  expect(geometry.candles.at(-1)!.x).toBeCloseTo(
    geometry.plotRight - geometry.step / 2,
    10,
  );
});

it("keeps axis labels on real bar times while spacing stays ordinal", () => {
  const geometry = buildChartGeometry(overnightInput);

  expect(geometry.timeAxis.length).toBeGreaterThanOrEqual(2);
  geometry.timeAxis.forEach((label) => {
    const candle = geometry.candles.find(
      ({ timestamp }) => timestamp === label.timestamp,
    );
    expect(candle).toBeDefined();
    expect(label.x).toBe(candle!.x);
    const realTime = new Date(Date.parse(label.timestamp));
    expect(label.label).toBe(
      `${String(realTime.getUTCHours()).padStart(2, "0")}:${String(
        realTime.getUTCMinutes(),
      ).padStart(2, "0")}`,
    );
  });
  expect(geometry.timeAxis.map(({ label }) => label)).toContain("19:50");
  expect(geometry.timeAxis.at(-1)?.label).toBe("13:40");
});

it("labels a daily series by date instead of clock time", () => {
  const dailyCandles: Candle[] = [
    "2026-07-21T20:00:00.000Z",
    "2026-07-22T20:00:00.000Z",
    "2026-07-23T20:00:00.000Z",
  ].map((timestamp, index) => ({
    timestamp,
    availableAt: new Date(Date.parse(timestamp) + 1_000).toISOString(),
    complete: true,
    open: 100 + index,
    high: 104 + index,
    low: 99 + index,
    close: 103 + index,
    volume: 1_000,
  }));

  const geometry = buildChartGeometry({
    ...overnightInput,
    candles: dailyCandles,
  });

  expect(geometry.timeAxis.map(({ label }) => label)).toEqual([
    "07-21",
    "07-22",
    "07-23",
  ]);
  expect(geometry.sessionBreaks).toEqual([]);
});

it("marks where the trading day changes instead of leaving a hole", () => {
  const geometry = buildChartGeometry(overnightInput);

  expect(geometry.sessionBreaks).toHaveLength(1);
  const [firstBreak] = geometry.sessionBreaks;
  expect(firstBreak?.label).toBe("07-24");
  expect(firstBreak?.timestamp).toBe(overnightCandles[2]!.timestamp);
  expect(firstBreak?.x).toBeCloseTo(
    geometry.candles[2]!.x - geometry.step / 2,
    10,
  );
});

it("continues the forecast on the same step so no blank column opens", () => {
  const geometry = geometryFor();

  expect(geometry.forecastPoints).toHaveLength(2);
  expect(geometry.forecastPoints[0]!.x - geometry.candles.at(-1)!.x).toBeCloseTo(
    geometry.step,
    10,
  );
  expect(geometry.forecastPoints[1]!.x - geometry.forecastPoints[0]!.x).toBeCloseTo(
    geometry.step,
    10,
  );
  expect(geometry.boundaryX).toBeCloseTo(
    geometry.candles.at(-1)!.x + geometry.step / 2,
    10,
  );
});

it("maps candles and probability bands into bounded chart geometry", () => {
  const geometry = geometryFor();

  expect(geometry.candles).toHaveLength(2);
  expect(geometry.candles[0]?.direction).toBe("up");
  expect(geometry.candles[1]?.direction).toBe("down");
  expect(geometry.forecastPoints).toHaveLength(2);
  expect(geometry.boundaryX).toBeGreaterThan(geometry.candles[1]?.x ?? 0);

  for (const candle of geometry.candles) {
    expect(candle.x).toBeGreaterThanOrEqual(0);
    expect(candle.x).toBeLessThanOrEqual(360);
    expect(candle.wickTop).toBeGreaterThanOrEqual(0);
    expect(candle.wickBottom).toBeLessThanOrEqual(250);
    expect(candle.bodyHeight).toBeGreaterThan(0);
  }

  for (const point of geometry.forecastPoints) {
    expect(point.upper80Y).toBeLessThanOrEqual(point.upper50Y);
    expect(point.upper50Y).toBeLessThanOrEqual(point.medianY);
    expect(point.medianY).toBeLessThanOrEqual(point.lower50Y);
    expect(point.lower50Y).toBeLessThanOrEqual(point.lower80Y);
  }

  expect(geometry.band80).toMatch(/^M /);
  expect(geometry.band50).toMatch(/^M /);
  expect(geometry.medianPath).toMatch(/^M /);
});

it("returns stable empty geometry instead of throwing without candles or forecasts", () => {
  const geometry = buildChartGeometry({
    candles: [],
    forecast: { ...forecast, points: [] },
    participationBars: [],
    decisionCutoff,
    width: 360,
    height: 250,
  });

  expect(geometry.candles).toEqual([]);
  expect(geometry.forecastPoints).toEqual([]);
  expect(geometry.overlays).toEqual([]);
  expect(geometry.timeAxis).toEqual([]);
  expect(geometry.band50).toBe("");
  expect(geometry.band80).toBe("");
  expect(geometry.medianPath).toBe("");
  expect(geometry.priceMin).toBe(0);
  expect(geometry.priceMax).toBe(1);
});

it("rejects incomplete and future-available candles at the explicit decision cutoff", () => {
  const leakyCandles: Candle[] = [
    ...candles,
    {
      timestamp: "2026-07-24T09:40:00-04:00",
      availableAt: "2026-07-24T09:40:01-04:00",
      complete: false,
      open: 102,
      high: 106,
      low: 101,
      close: 105,
      volume: 2_500,
    },
    {
      timestamp: "2026-07-24T10:05:00-04:00",
      availableAt: "2026-07-24T10:05:01-04:00",
      complete: true,
      open: 105,
      high: 110,
      low: 104,
      close: 109,
      volume: 4_000,
    },
  ];

  const geometry = geometryFor({ candles: leakyCandles });
  const safeGeometry = geometryFor();

  expect(geometry.candles).toHaveLength(2);
  expect(geometry.priceMax).toBe(safeGeometry.priceMax);
});

it("draws no moving average when the server published no series", () => {
  const geometry = geometryFor({ overlays: [] });

  expect(geometry.overlays).toEqual([]);
});

it("draws the server moving average and breaks the line where it has no value", () => {
  const fiveCandles: Candle[] = Array.from({ length: 5 }, (_, index) => ({
    timestamp: `2026-07-24T09:${String(30 + index * 5).padStart(2, "0")}:00-04:00`,
    availableAt: `2026-07-24T09:${String(30 + index * 5).padStart(2, "0")}:01-04:00`,
    complete: true,
    open: 100 + index,
    high: 102 + index,
    low: 99 + index,
    close: 101 + index,
    volume: 1_000 + index * 100,
  }));

  const geometry = geometryFor({
    candles: fiveCandles,
    overlays: [
      {
        key: "ma5",
        label: "MA5",
        values: [null, 100.5, 101.5, null, 103.5],
      },
    ],
  });

  const [overlay] = geometry.overlays;
  expect(overlay?.key).toBe("ma5");
  expect(overlay?.label).toBe("MA5");
  // Two runs of drawable values means two subpaths, never one line bridging
  // the bar the server had no value for.
  expect(overlay?.path.match(/M /g)).toHaveLength(2);
  expect(overlay?.points.map(({ index }) => index)).toEqual([1, 2, 4]);
  overlay?.points.forEach((point) => {
    expect(point.x).toBe(geometry.candles[point.index]!.x);
  });
});

it("keeps overlay values on the bars they describe when candles are dropped", () => {
  // The dropped bar is the first one, so an overlay read by position in the
  // drawn list rather than by its own index would shift every value one bar
  // earlier — an MA sitting on a price it never described.
  const dropped: Candle = {
    timestamp: "2026-07-24T09:25:00-04:00",
    availableAt: "2026-07-24T09:25:01-04:00",
    complete: false,
    open: 99,
    high: 101,
    low: 98,
    close: 100,
    volume: 900,
  };

  const geometry = geometryFor({
    candles: [dropped, ...candles],
    overlays: [{ key: "ma5", label: "MA5", values: [900, 101, 102] }],
  });

  expect(geometry.candles).toHaveLength(2);
  expect(geometry.overlays[0]?.points.map(({ value }) => value)).toEqual([
    101, 102,
  ]);
  expect(geometry.overlays[0]?.path).not.toContain("900");
});

it("keeps the MACD panel empty and unavailable when no series arrived", () => {
  const geometry = geometryFor({ panels: ["macd"] });

  expect(geometry.macd?.available).toBe(false);
  expect(geometry.macd?.bars).toEqual([]);
  expect(geometry.macd?.linePath).toBe("");
  expect(geometry.macd?.signalPath).toBe("");
  expect(geometry.macd?.bottom).toBeGreaterThan(geometry.macd!.top);
});

it("draws the MACD histogram and both lines from a published series", () => {
  const geometry = geometryFor({
    panels: ["macd"],
    macdSeries: {
      line: [0.4, -0.2],
      signal: [0.1, 0.05],
      histogram: [0.3, -0.25],
    },
  });

  expect(geometry.macd?.available).toBe(true);
  expect(geometry.macd?.bars.map(({ positive }) => positive)).toEqual([
    true,
    false,
  ]);
  expect(geometry.macd?.bars.map(({ x }) => x)).toEqual(
    geometry.candles.map(({ x }) => x),
  );
  expect(geometry.macd?.linePath).toMatch(/^M /);
  expect(geometry.macd?.signalPath).toMatch(/^M /);
  const [positiveBar, negativeBar] = geometry.macd!.bars;
  expect(positiveBar!.y + positiveBar!.height).toBeCloseTo(
    geometry.macd!.zeroY,
    10,
  );
  expect(negativeBar!.y).toBeCloseTo(geometry.macd!.zeroY, 10);
});

it("keeps the RSI reference lines while stating a missing series", () => {
  const geometry = geometryFor({ panels: ["rsi"] });

  expect(geometry.rsi?.available).toBe(false);
  expect(geometry.rsi?.path).toBe("");
  expect(geometry.rsi?.references.map(({ value }) => value)).toEqual([70, 50, 30]);
  const [overbought, middle, oversold] = geometry.rsi!.references;
  expect(overbought!.y).toBeLessThan(middle!.y);
  expect(middle!.y).toBeLessThan(oversold!.y);
});

it("maps a published RSI series onto the fixed 0 to 100 panel scale", () => {
  const geometry = geometryFor({
    panels: ["rsi"],
    rsiSeries: { values: [30, 70] },
  });

  expect(geometry.rsi?.available).toBe(true);
  expect(geometry.rsi?.path).toMatch(/^M /);
  expect(geometry.rsi?.points).toHaveLength(2);
  const [oversoldPoint, overboughtPoint] = geometry.rsi!.points;
  const references = geometry.rsi!.references;
  expect(oversoldPoint!.y).toBeCloseTo(references.at(-1)!.y, 10);
  expect(overboughtPoint!.y).toBeCloseTo(references[0]!.y, 10);
});

it("gives the price panel the larger half of the stack it shares", () => {
  const stacked = geometryFor({
    panels: ["volume", "macd", "rsi", "participation"],
    height: 460,
  });
  const height = (panel: { top: number; bottom: number }) =>
    panel.bottom - panel.top;
  const indicators = [
    stacked.panels.volume!,
    stacked.panels.macd!,
    stacked.panels.rsi!,
    stacked.panels.participation!,
  ].reduce((total, panel) => total + height(panel), 0);

  // The K line is the subject of the screen and the indicators are read
  // against it; four sub-panels at their own weights took more of the frame
  // than the bars they describe, and the price flattened into a ribbon.
  expect(height(stacked.panels.price)).toBeGreaterThan(indicators);
  expect(height(stacked.panels.price)).toBeGreaterThan(
    (stacked.panels.axisY - stacked.panels.price.top) * 0.5,
  );
});

it("rules the price axis at round levels instead of at the panel's own thirds", () => {
  const geometry = geometryFor({ height: 420 });
  const values = geometry.priceTicks.map(({ label }) => Number(label));

  expect(values.length).toBeGreaterThanOrEqual(4);
  // The step is chosen for a level count near the target, so the axis can land
  // one line either side of it rather than on it exactly.
  expect(values.length).toBeLessThanOrEqual(7);
  const step = values[0]! - values[1]!;
  const magnitude = 10 ** Math.floor(Math.log10(step));
  // A level a reader can hold in their head — 142.50, not 141.37, which is
  // what dividing this window's own range into thirds produces.
  expect(
    [1, 2, 2.5, 5].some((nice) => Math.abs(step / magnitude - nice) < 1e-9),
  ).toBe(true);

  const { top, bottom } = geometry.panels.price;
  const span = geometry.priceMax - geometry.priceMin;
  values.forEach((value, index) => {
    expect(value).toBeGreaterThanOrEqual(geometry.priceMin);
    expect(value).toBeLessThanOrEqual(geometry.priceMax);
    expect(Math.abs(value / step - Math.round(value / step))).toBeLessThan(1e-9);
    // The label has to name the row it is printed on, or the grid line under it
    // is a price the chart never claimed.
    expect(geometry.priceTicks[index]!.y).toBeCloseTo(
      top + ((geometry.priceMax - value) / span) * (bottom - top),
      6,
    );
    if (index > 0) expect(values[index - 1]! - value).toBeCloseTo(step, 9);
  });
});

it("still rules the axis when a window spans only a couple of dollars", () => {
  // The range an intraday window actually has. Rounding the step up to the
  // next round number left two labelled levels on the whole panel, and a bar
  // between them could be read to about a dollar.
  const intraday: Candle[] = Array.from({ length: 40 }, (_, index) => {
    const timestamp = new Date(Date.UTC(2026, 6, 24, 13, 30 + index * 5)).toISOString();
    const open = 142 + Math.sin(index / 6) * 1.2;
    return {
      timestamp,
      availableAt: new Date(Date.parse(timestamp) + 1_000).toISOString(),
      complete: true,
      open,
      high: open + 0.4,
      low: open - 0.4,
      close: open + 0.1,
      volume: 1_000 + index,
    };
  });

  const geometry = buildChartGeometry({
    candles: intraday,
    forecast: null,
    participationBars: [],
    decisionCutoff: "2026-07-24T23:00:00.000Z",
    width: resolveChartWidth(390),
    height: 460,
    panels: ["volume", "macd", "rsi"],
  });

  expect(geometry.priceMax - geometry.priceMin).toBeLessThan(4);
  expect(geometry.priceTicks.length).toBeGreaterThanOrEqual(4);
});

it("uses the available phone width while keeping chart geometry bounded", () => {
  expect(resolveChartWidth(375)).toBe(319);
  expect(resolveChartWidth(390)).toBe(334);
  expect(resolveChartWidth(844)).toBe(788);
  expect(resolveChartWidth(220)).toBe(304);
  expect(resolveChartWidth(1_600)).toBe(1_180);
});

it("selects the nearest x coordinate and resolves an exact midpoint to the first", () => {
  const points = [
    { id: "first", x: 10 },
    { id: "second", x: 30 },
  ];

  expect(findNearestByX(points, 19.9)?.id).toBe("first");
  expect(findNearestByX(points, 20)?.id).toBe("first");
  expect(findNearestByX(points, 20.1)?.id).toBe("second");
});

it("reads participation as a deviation from an even split, bar by bar", () => {
  const geometry = geometryFor({ panels: ["participation"] });

  expect(geometry.participation).toHaveLength(2);
  expect(geometry.participation.map(({ timestamp }) => timestamp)).toEqual(
    geometry.candles.map(({ timestamp }) => timestamp),
  );
  const [mainLed, retailLed] = geometry.participation;
  expect(mainLed).toMatchObject({ available: true, dominant: "main" });
  expect(retailLed).toMatchObject({ available: true, dominant: "retail" });
  // 60/40 leans one tenth of the full range above the even line; 25/75 leans a
  // quarter below it, and the marks are drawn on that same scale.
  expect(mainLed!.markHeight).toBeCloseTo(mainLed!.height * 0.1, 10);
  expect(mainLed!.markY + mainLed!.markHeight).toBeCloseTo(mainLed!.midY, 10);
  expect(retailLed!.markHeight).toBeCloseTo(retailLed!.height * 0.25, 10);
  expect(retailLed!.markY).toBeCloseTo(retailLed!.midY, 10);
  geometry.participation.forEach((bar, index) => {
    expect(bar.x).toBe(geometry.candles[index]!.x);
    expect(bar.midY).toBeCloseTo(bar.top + bar.height / 2, 10);
  });
});

it("keeps a missing participation value as an unavailable empty slot", () => {
  const unavailable: ParticipationBar = {
    ...participationBars[1]!,
    mainShare: null,
    retailShare: null,
    mainActivity: null,
    retailActivity: null,
    netFlow: null,
    coverage: 0,
    qualityStatus: "unavailable",
    missingReason: "capital flow unavailable",
  };

  const geometry = geometryFor({
    panels: ["participation"],
    participationBars: [participationBars[0]!, unavailable],
  });

  expect(geometry.participation[1]).toMatchObject({
    timestamp: candles[1]!.timestamp,
    available: false,
    dominant: null,
    markHeight: 0,
    mainShare: null,
    retailShare: null,
  });
});

it("renders only exact complete activity-derived participation as usable", () => {
  const invalidBars: ParticipationBar[] = [
    { ...participationBars[0]!, coverage: 0.9999999999999999 },
    { ...participationBars[0]!, mainActivity: -1 },
    {
      ...participationBars[0]!,
      mainShare: 0.5,
      retailShare: 0.5,
      mainActivity: 0,
      retailActivity: 0,
    },
    {
      ...participationBars[0]!,
      mainShare: 0.5,
      retailShare: 0.5,
      mainActivity: 60,
      retailActivity: 40,
    },
    { ...participationBars[0]!, mainShare: 0.6000000001 },
  ];

  invalidBars.forEach((invalid) => {
    const geometry = geometryFor({
      panels: ["participation"],
      participationBars: [invalid, participationBars[1]!],
    });

    expect(geometry.participation[0]).toMatchObject({
      available: false,
      dominant: null,
      markHeight: 0,
    });
  });
});

it("rejects participation that was unavailable at the explicit decision cutoff", () => {
  const futureAvailable: ParticipationBar = {
    ...participationBars[0]!,
    availableAt: "2026-07-24T10:00:01-04:00",
  };

  const geometry = geometryFor({
    panels: ["participation"],
    participationBars: [futureAvailable, participationBars[1]!],
  });

  expect(geometry.participation[0]?.available).toBe(false);
  expect(geometry.participation[0]).toMatchObject({
    coverage: null,
    source: null,
    missingReason: "决策截止时不可用",
  });
  expect(geometry.participation[1]?.available).toBe(true);
});

it("never lets participation input reorder candle geometry", () => {
  const chronological = geometryFor({ panels: ["participation"] });
  const reversed = geometryFor({
    panels: ["participation"],
    participationBars: [...participationBars].reverse(),
  });

  expect(reversed.candles.map(({ timestamp, x }) => ({ timestamp, x }))).toEqual(
    chronological.candles.map(({ timestamp, x }) => ({ timestamp, x })),
  );
  expect(reversed.participation.map(({ timestamp, x }) => ({ timestamp, x }))).toEqual(
    chronological.participation.map(({ timestamp, x }) => ({ timestamp, x })),
  );
});

it("draws only the window while keeping every earlier bar reachable", () => {
  const manyCandles: Candle[] = Array.from({ length: 201 }, (_, index) => ({
    timestamp: new Date(Date.UTC(2026, 6, 23, 9, index)).toISOString(),
    availableAt: new Date(Date.UTC(2026, 6, 23, 9, index, 1)).toISOString(),
    complete: true,
    open: 100 + index,
    high: 102 + index,
    low: 99 + index,
    close: 101 + index,
    volume: 1_000 + index,
  }));

  const geometry = geometryFor({
    candles: manyCandles,
    forecast: { ...forecast, predictedAt: "2026-07-24T10:00:00.000Z" },
    participationBars: [],
    panels: ["participation"],
    overlays: [
      {
        key: "ma5",
        label: "MA5",
        values: manyCandles.map((_, index) => 100 + index),
      },
    ],
  });

  const { size, offset, total } = geometry.window;
  expect(geometry.window.total).toBe(201);
  expect(size).toBeLessThan(201);
  expect(geometry.candles).toHaveLength(size);
  // The newest bar is the one the chart opens on.
  expect(offset).toBe(201 - size);
  expect(geometry.candles.at(-1)?.timestamp).toBe(manyCandles[200]?.timestamp);
  // Server indices survive the window so a bar the server named by index — a
  // confirmed nine, say — still lands on the bar it described.
  expect(geometry.candles[0]?.sourceIndex).toBe(offset);
  expect(geometry.candles.at(-1)?.sourceIndex).toBe(200);
  expect(geometry.participation).toHaveLength(size);
  expect(geometry.overlays[0]?.points).toHaveLength(size);
  expect(geometry.overlays[0]?.points[0]?.value).toBe(100 + offset);

  // The bars the window left out are still there to be dragged back into view.
  const dragged = geometryFor({
    candles: manyCandles,
    forecast: { ...forecast, predictedAt: "2026-07-24T10:00:00.000Z" },
    participationBars: [],
    panels: ["participation"],
    window: { size, offset: 0, total },
    overlays: [
      {
        key: "ma5",
        label: "MA5",
        values: manyCandles.map((_, index) => 100 + index),
      },
    ],
  });

  expect(dragged.candles[0]?.sourceIndex).toBe(0);
  expect(dragged.candles[0]?.timestamp).toBe(manyCandles[0]?.timestamp);
  expect(dragged.overlays[0]?.points[0]?.value).toBe(100);
});

it("uses an explicit live decision cutoff when forecast is null", () => {
  const liveCutoff = "2026-07-24T09:36:00-04:00";
  const futureCandle: Candle = {
    timestamp: "2026-07-24T09:40:00-04:00",
    availableAt: "2026-07-24T09:40:01-04:00",
    complete: true,
    open: 500,
    high: 550,
    low: 450,
    close: 525,
    volume: 50_000,
  };
  const futureParticipation: ParticipationBar = {
    ...participationBars[1]!,
    closedAt: futureCandle.timestamp,
    availableAt: futureCandle.availableAt,
    source: "post-cutoff-secret-source",
    coverage: 0.37,
    qualityStatus: "unavailable",
    mainShare: null,
    retailShare: null,
    mainActivity: null,
    retailActivity: null,
    netFlow: null,
    missingReason: "post-cutoff-secret-reason",
  };

  const safe = geometryFor({
    forecast: null,
    decisionCutoff: liveCutoff,
    panels: ["participation"],
  });
  const leaky = geometryFor({
    candles: [...candles, futureCandle],
    forecast: null,
    participationBars: [...participationBars, futureParticipation],
    decisionCutoff: liveCutoff,
    panels: ["participation"],
  });

  expect(leaky.candles.map(({ timestamp }) => timestamp)).toEqual(
    safe.candles.map(({ timestamp }) => timestamp),
  );
  expect(leaky.priceMin).toBe(safe.priceMin);
  expect(leaky.priceMax).toBe(safe.priceMax);
  expect(leaky.participation.map(({ timestamp }) => timestamp)).toEqual(
    safe.participation.map(({ timestamp }) => timestamp),
  );
});

it("stacks only the panels asked for and leaves room for the time axis", () => {
  const stacked = geometryFor({
    panels: ["volume", "macd", "rsi", "participation"],
    height: 420,
  });
  const bare = geometryFor({ panels: [], height: 420 });

  expect(bare.panels.volume).toBeNull();
  expect(bare.panels.macd).toBeNull();
  expect(bare.panels.rsi).toBeNull();
  expect(bare.panels.participation).toBeNull();
  expect(bare.macd).toBeNull();
  expect(bare.rsi).toBeNull();
  expect(bare.participation).toEqual([]);
  // With no sub-panels the price panel owns the height the others would take.
  expect(bare.panels.price.bottom).toBeGreaterThan(stacked.panels.price.bottom);

  const ordered = [
    stacked.panels.price,
    stacked.panels.volume!,
    stacked.panels.macd!,
    stacked.panels.rsi!,
    stacked.panels.participation!,
  ];
  ordered.forEach((panel, index) => {
    expect(panel.bottom).toBeGreaterThan(panel.top);
    if (index > 0) expect(panel.top).toBeGreaterThanOrEqual(ordered[index - 1]!.bottom);
  });
  expect(stacked.panels.axisY).toBeGreaterThanOrEqual(
    stacked.panels.participation!.bottom,
  );
  expect(stacked.panels.axisY).toBeLessThanOrEqual(420);
});
