import type { Candle, ForecastSnapshot } from "./models";

export type CandleGeometry = {
  timestamp: string;
  x: number;
  bodyWidth: number;
  bodyTop: number;
  bodyHeight: number;
  wickTop: number;
  wickBottom: number;
  direction: "up" | "down";
  volumeX: number;
  volumeY: number;
  volumeHeight: number;
};

export type ForecastGeometry = {
  x: number;
  medianY: number;
  lower50Y: number;
  upper50Y: number;
  lower80Y: number;
  upper80Y: number;
};

export type ChartGeometry = {
  candles: CandleGeometry[];
  forecastPoints: ForecastGeometry[];
  boundaryX: number;
  band50: string;
  band80: string;
  medianPath: string;
  ma5Path: string;
  priceMin: number;
  priceMax: number;
  priceTicks: { label: string; y: number }[];
  priceBottom: number;
  volumeTop: number;
};

const emptyGeometry = (width: number, height: number): ChartGeometry => ({
  candles: [],
  forecastPoints: [],
  boundaryX: width * 0.66,
  band50: "",
  band80: "",
  medianPath: "",
  ma5Path: "",
  priceMin: 0,
  priceMax: 1,
  priceTicks: [],
  priceBottom: height * 0.78,
  volumeTop: height * 0.82,
});

const linePath = (points: { x: number; y: number }[]) =>
  points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");

const bandPath = (
  points: ForecastGeometry[],
  upperKey: "upper50Y" | "upper80Y",
  lowerKey: "lower50Y" | "lower80Y",
) => {
  if (!points.length) return "";
  const upper = points.map((point) => ({ x: point.x, y: point[upperKey] }));
  const lower = [...points].reverse().map((point) => ({ x: point.x, y: point[lowerKey] }));
  return `${linePath(upper)} ${lower.map((point) => `L ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ")} Z`;
};

export const resolveChartWidth = (viewportWidth: number) =>
  Math.min(Math.max(viewportWidth - 56, 304), 1_180);

export function buildChartGeometry(
  candles: Candle[],
  forecast: ForecastSnapshot,
  width: number,
  height: number,
): ChartGeometry {
  const decisionTime = Date.parse(forecast.predictedAt);
  const pointInTimeCandles = Number.isFinite(decisionTime)
    ? candles
        .filter((candle) => {
          const availableAt = Date.parse(candle.availableAt);
          return candle.complete && Number.isFinite(availableAt) && availableAt <= decisionTime;
        })
        .sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp))
    : [];

  if (!pointInTimeCandles.length && !forecast.points.length) {
    return emptyGeometry(width, height);
  }

  const inset = { left: 8, right: 42, top: 14 };
  const priceBottom = height * 0.75;
  const volumeTop = height * 0.82;
  const volumeBottom = height - 8;
  const boundaryX = inset.left + (width - inset.left - inset.right) * 0.68;
  const allPrices = [
    ...pointInTimeCandles.flatMap(({ high, low }) => [high, low]),
    ...forecast.points.flatMap(({ upper80, lower80 }) => [upper80, lower80]),
  ];
  const rawMin = Math.min(...allPrices);
  const rawMax = Math.max(...allPrices);
  const rawRange = Math.max(rawMax - rawMin, 1);
  const priceMin = rawMin - rawRange * 0.04;
  const priceMax = rawMax + rawRange * 0.04;
  const priceRange = priceMax - priceMin;
  const mapY = (price: number) =>
    inset.top + ((priceMax - price) / priceRange) * (priceBottom - inset.top);

  const candleSpan = Math.max(boundaryX - inset.left - 7, 1);
  const candleStep = candleSpan / Math.max(pointInTimeCandles.length, 1);
  const bodyWidth = Math.max(2.5, Math.min(7, candleStep * 0.58));
  const maxVolume = Math.max(...pointInTimeCandles.map(({ volume }) => volume), 1);
  const candleGeometry = pointInTimeCandles.map((candle, index): CandleGeometry => {
    const x = inset.left + candleStep * (index + 0.5);
    const openY = mapY(candle.open);
    const closeY = mapY(candle.close);
    const volumeHeight = ((volumeBottom - volumeTop) * candle.volume) / maxVolume;
    return {
      timestamp: candle.timestamp,
      x,
      bodyWidth,
      bodyTop: Math.min(openY, closeY),
      bodyHeight: Math.max(Math.abs(closeY - openY), 1.8),
      wickTop: mapY(candle.high),
      wickBottom: mapY(candle.low),
      direction: candle.close >= candle.open ? "up" : "down",
      volumeX: x - bodyWidth / 2,
      volumeY: volumeBottom - volumeHeight,
      volumeHeight,
    };
  });
  const ma5Path = linePath(
    pointInTimeCandles.flatMap((_, index) => {
      if (index < 4) return [];
      const window = pointInTimeCandles.slice(index - 4, index + 1);
      const average = window.reduce((sum, candle) => sum + candle.close, 0) / window.length;
      const x = candleGeometry[index]?.x;
      return x === undefined ? [] : [{ x, y: mapY(average) }];
    }),
  );

  const forecastSpan = Math.max(width - inset.right - boundaryX, 1);
  const forecastGeometry = forecast.points.map((point, index): ForecastGeometry => {
    const x = boundaryX + (forecastSpan * (index + 1)) / (forecast.points.length + 0.35);
    return {
      x,
      medianY: mapY(point.median),
      lower50Y: mapY(point.lower50),
      upper50Y: mapY(point.upper50),
      lower80Y: mapY(point.lower80),
      upper80Y: mapY(point.upper80),
    };
  });

  const priceTicks = Array.from({ length: 4 }, (_, index) => {
    const ratio = index / 3;
    const value = priceMax - priceRange * ratio;
    return {
      label: value.toFixed(value >= 100 ? 0 : 1),
      y: inset.top + (priceBottom - inset.top) * ratio,
    };
  });

  return {
    candles: candleGeometry,
    forecastPoints: forecastGeometry,
    boundaryX,
    band50: bandPath(forecastGeometry, "upper50Y", "lower50Y"),
    band80: bandPath(forecastGeometry, "upper80Y", "lower80Y"),
    medianPath: linePath(forecastGeometry.map((point) => ({ x: point.x, y: point.medianY }))),
    ma5Path,
    priceMin,
    priceMax,
    priceTicks,
    priceBottom,
    volumeTop,
  };
}
