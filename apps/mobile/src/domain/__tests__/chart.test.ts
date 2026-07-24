import { expect, it } from "@jest/globals";

import type { Candle, ForecastSnapshot } from "@/domain/models";

import { buildChartGeometry, resolveChartWidth } from "../chart";

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

it("maps candles and probability bands into bounded chart geometry", () => {
  const geometry = buildChartGeometry(candles, forecast, 360, 250);

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
  const geometry = buildChartGeometry([], emptyForecast, 360, 250);

  expect(geometry.candles).toEqual([]);
  expect(geometry.forecastPoints).toEqual([]);
  expect(geometry.band50).toBe("");
  expect(geometry.band80).toBe("");
  expect(geometry.medianPath).toBe("");
  expect(geometry.priceMin).toBe(0);
  expect(geometry.priceMax).toBe(1);
});

it("rejects incomplete and future-available candles at the forecast decision time", () => {
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

  const geometry = buildChartGeometry(leakyCandles, forecast, 360, 250);
  const safeGeometry = buildChartGeometry(candles, forecast, 360, 250);

  expect(geometry.candles).toHaveLength(2);
  expect(geometry.priceMax).toBe(safeGeometry.priceMax);
});

it("draws MA5 only from five point-in-time completed closes", () => {
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

  const geometry = buildChartGeometry(fiveCandles, forecast, 360, 250);

  expect(geometry.ma5Path).toMatch(/^M /);
});

it("uses the available phone width while keeping chart geometry bounded", () => {
  expect(resolveChartWidth(390)).toBe(334);
  expect(resolveChartWidth(844)).toBe(788);
  expect(resolveChartWidth(220)).toBe(304);
  expect(resolveChartWidth(1_600)).toBe(1_180);
});
