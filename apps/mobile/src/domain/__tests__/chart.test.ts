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

it("maps candles and probability bands into bounded chart geometry", () => {
  const geometry = buildChartGeometry(
    candles,
    forecast,
    participationBars,
    decisionCutoff,
    360,
    250,
  );

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
  expect(geometry.ma5Path).toBe("");
});

it("returns stable empty geometry instead of throwing without candles or forecasts", () => {
  const emptyForecast = { ...forecast, points: [] };
  const geometry = buildChartGeometry(
    [],
    emptyForecast,
    [],
    decisionCutoff,
    360,
    250,
  );

  expect(geometry.candles).toEqual([]);
  expect(geometry.forecastPoints).toEqual([]);
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

  const geometry = buildChartGeometry(
    leakyCandles,
    forecast,
    participationBars,
    decisionCutoff,
    360,
    250,
  );
  const safeGeometry = buildChartGeometry(
    candles,
    forecast,
    participationBars,
    decisionCutoff,
    360,
    250,
  );

  expect(geometry.candles).toHaveLength(2);
  expect(geometry.priceMax).toBe(safeGeometry.priceMax);
});

it("does not derive an MA5 chart path from client candle closes", () => {
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

  const geometry = buildChartGeometry(
    fiveCandles,
    forecast,
    [],
    decisionCutoff,
    360,
    250,
  );

  expect(geometry.ma5Path).toBe("");
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

it("aligns one fixed-height 100% participation bar to every completed candle", () => {
  const geometry = buildChartGeometry(
    candles,
    forecast,
    participationBars,
    decisionCutoff,
    360,
    250,
  );

  expect(geometry.participation).toHaveLength(2);
  expect(geometry.participation.map(({ timestamp }) => timestamp)).toEqual(
    geometry.candles.map(({ timestamp }) => timestamp),
  );
  geometry.participation.forEach((bar, index) => {
    expect(bar.x).toBe(geometry.candles[index]!.x);
    expect(bar.width).toBe(geometry.candles[index]!.bodyWidth);
    expect(bar.height).toBe(16);
    expect(bar.mainHeight + bar.retailHeight).toBeCloseTo(16, 10);
  });
  expect(geometry.participation[0]).toMatchObject({
    available: true,
    mainHeight: 9.6,
    retailHeight: 6.4,
  });
  expect(geometry.participation[1]).toMatchObject({
    available: true,
    mainHeight: 4,
    retailHeight: 12,
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

  const geometry = buildChartGeometry(
    candles,
    forecast,
    [participationBars[0]!, unavailable],
    decisionCutoff,
    360,
    250,
  );

  expect(geometry.participation[1]).toMatchObject({
    timestamp: candles[1]!.timestamp,
    available: false,
    height: 16,
    mainHeight: 0,
    retailHeight: 0,
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
    const geometry = buildChartGeometry(
      candles,
      forecast,
      [invalid, participationBars[1]!],
      decisionCutoff,
      360,
      250,
    );

    expect(geometry.participation[0]).toMatchObject({
      available: false,
      mainHeight: 0,
      retailHeight: 0,
    });
  });
});

it("rejects participation that was unavailable at the explicit decision cutoff", () => {
  const futureAvailable: ParticipationBar = {
    ...participationBars[0]!,
    availableAt: "2026-07-24T10:00:01-04:00",
  };

  const geometry = buildChartGeometry(
    candles,
    forecast,
    [futureAvailable, participationBars[1]!],
    decisionCutoff,
    360,
    250,
  );

  expect(geometry.participation[0]?.available).toBe(false);
  expect(geometry.participation[0]).toMatchObject({
    coverage: null,
    source: null,
    missingReason: "决策截止时不可用",
  });
  expect(geometry.participation[1]?.available).toBe(true);
});

it("never lets participation input reorder candle geometry", () => {
  const chronological = buildChartGeometry(
    candles,
    forecast,
    participationBars,
    decisionCutoff,
    360,
    250,
  );
  const reversed = buildChartGeometry(
    candles,
    forecast,
    [...participationBars].reverse(),
    decisionCutoff,
    360,
    250,
  );

  expect(reversed.candles.map(({ timestamp, x }) => ({ timestamp, x }))).toEqual(
    chronological.candles.map(({ timestamp, x }) => ({ timestamp, x })),
  );
  expect(reversed.participation.map(({ timestamp, x }) => ({ timestamp, x }))).toEqual(
    chronological.participation.map(({ timestamp, x }) => ({ timestamp, x })),
  );
});

it("keeps only the latest 200 completed candles in the interactive chart", () => {
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
  const laterForecast = {
    ...forecast,
    predictedAt: "2026-07-24T10:00:00.000Z",
  };

  const geometry = buildChartGeometry(
    manyCandles,
    laterForecast,
    [],
    decisionCutoff,
    360,
    250,
  );

  expect(geometry.candles).toHaveLength(200);
  expect(geometry.candles[0]?.timestamp).toBe(manyCandles[1]?.timestamp);
  expect(geometry.participation).toHaveLength(200);
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

  const safe = buildChartGeometry(
    candles,
    null,
    participationBars,
    liveCutoff,
    360,
    250,
  );
  const leaky = buildChartGeometry(
    [...candles, futureCandle],
    null,
    [...participationBars, futureParticipation],
    liveCutoff,
    360,
    250,
  );

  expect(leaky.candles.map(({ timestamp }) => timestamp)).toEqual(
    safe.candles.map(({ timestamp }) => timestamp),
  );
  expect(leaky.priceMin).toBe(safe.priceMin);
  expect(leaky.priceMax).toBe(safe.priceMax);
  expect(leaky.participation.map(({ timestamp }) => timestamp)).toEqual(
    safe.participation.map(({ timestamp }) => timestamp),
  );
});
