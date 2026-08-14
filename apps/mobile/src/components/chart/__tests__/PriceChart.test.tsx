import { expect, it } from "@jest/globals";
import {
  act,
  render,
  userEvent,
} from "@testing-library/react-native";
import { Dimensions, StyleSheet } from "react-native";
import { State, type PanGesture, type PinchGesture } from "react-native-gesture-handler";
import {
  fireGestureHandler,
  getByGestureTestId,
} from "react-native-gesture-handler/jest-utils";

import {
  minReadableBodyWidth,
  readableWindowSize,
  resolveChartWidth,
} from "@/domain/chart";
import type { Candle, ChartSnapshot } from "@/domain/models";
import { colors } from "@/theme/tokens";

import { PriceChart } from "../PriceChart";

const metadata = {
  source: "analysis-core",
  asOf: "2026-07-25T15:55:00.000Z",
  availableAt: "2026-07-25T15:55:01.000Z",
  methodVersion: "test-v1",
  qualityStatus: "live" as const,
};

const snapshot: ChartSnapshot = {
  demoData: false,
  source: {
    source: "moomoo",
    status: "live",
    asOf: "2026-07-25T15:59:48.000Z",
    decisionCutoff: "2026-07-25T15:59:50.000Z",
  },
  symbol: "NVDA",
  interval: "5m",
  quote: {
    price: 141.5,
    changePercent: 1.25,
    source: "moomoo",
    asOf: "2026-07-25T15:59:48.000Z",
    availableAt: "2026-07-25T15:59:48.000Z",
    methodVersion: "provider-quote-v1",
    qualityStatus: "live",
  },
  candles: [
    {
      timestamp: "2026-07-25T15:50:00.000Z",
      availableAt: "2026-07-25T15:50:01.000Z",
      complete: true,
      open: 140,
      high: 141,
      low: 139.5,
      close: 140.5,
      volume: 1_200,
    },
    {
      timestamp: "2026-07-25T15:55:00.000Z",
      availableAt: "2026-07-25T15:55:01.000Z",
      complete: true,
      open: 140.5,
      high: 142,
      low: 140,
      close: 141.5,
      volume: 1_500,
    },
  ],
  participationBars: [
    {
      closedAt: "2026-07-25T15:50:00.000Z",
      mainShare: 0.6,
      retailShare: 0.4,
      mainActivity: 120,
      retailActivity: 80,
      netFlow: -20,
      coverage: 1,
      source: "moomoo",
      asOf: "2026-07-25T15:50:00.000Z",
      availableAt: "2026-07-25T15:50:01.000Z",
      methodVersion: "order-size-activity-share-v1",
      qualityStatus: "live",
      missingReason: null,
    },
    {
      closedAt: "2026-07-25T15:55:00.000Z",
      mainShare: null,
      retailShare: null,
      mainActivity: null,
      retailActivity: null,
      netFlow: null,
      coverage: 0,
      source: "moomoo",
      asOf: "2026-07-25T15:55:00.000Z",
      availableAt: "2026-07-25T15:55:01.000Z",
      methodVersion: "order-size-activity-share-v1",
      qualityStatus: "unavailable",
      missingReason: "capital flow unavailable",
    },
  ],
  indicators: {
    ma5: { ...metadata, value: 140.8, series: null },
    rsi: { ...metadata, value: 56.2, series: null },
    macd: {
      ...metadata,
      line: 0.45,
      signal: 0.3,
      histogram: 0.15,
      series: null,
    },
  },
  magicNine: {
    ...metadata,
    direction: "bullish",
    count: 2,
    series: null,
    completed: false,
    perfected: false,
    confirmedAtIndex: null,
    lastCompleted: null,
  },
  forecast: null,
};

const withSeries: ChartSnapshot = {
  ...snapshot,
  indicators: {
    ma5: {
      ...snapshot.indicators.ma5,
      series: { ...metadata, methodVersion: "sma-5-v1", values: [null, 140.8] },
    },
    rsi: {
      ...snapshot.indicators.rsi,
      series: {
        ...metadata,
        methodVersion: "wilder-rsi-14-v1",
        values: [48.5, 56.2],
      },
    },
    macd: {
      ...snapshot.indicators.macd,
      series: {
        ...metadata,
        methodVersion: "macd-12-26-9-v1",
        line: [0.3, 0.45],
        signal: [0.25, 0.3],
        histogram: [0.05, 0.15],
      },
    },
  },
};

const hidden = { includeHiddenElements: true } as const;

function responderEvent(locationX: number) {
  const target = { measure: () => undefined };
  return {
    currentTarget: target,
    nativeEvent: {
      changedTouches: [],
      identifier: 1,
      locationX,
      locationY: 0,
      pageX: locationX,
      pageY: 0,
      target: 1,
      timestamp: 1,
      touches: [],
    },
    stopPropagation: () => undefined,
    target,
  };
}

async function pressAt(
  element: { props: { onClick?: (event: ReturnType<typeof responderEvent>) => void } },
  locationX: number,
) {
  await act(async () => {
    element.props.onClick?.(responderEvent(locationX));
  });
}

const candleAt = (index: number): Candle => {
  const timestamp = new Date(Date.UTC(2026, 6, 25, 12, index)).toISOString();
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

/** More bars than any window can hold, so the window has to be real. */
const deepCandles: Candle[] = Array.from({ length: 240 }, (_, index) =>
  candleAt(index),
);

const deepSnapshot = (
  candles: Candle[],
  decisionCutoff: string,
): ChartSnapshot => ({
  ...snapshot,
  source: { ...snapshot.source, decisionCutoff },
  candles,
  participationBars: candles.map((candle, index) => ({
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
    qualityStatus: "live" as const,
    missingReason: null,
  })),
  indicators: {
    ma5: {
      ...snapshot.indicators.ma5,
      series: {
        ...metadata,
        methodVersion: "sma-5-v1",
        values: candles.map((_, index) => 100.5 + index),
      },
    },
    rsi: {
      ...snapshot.indicators.rsi,
      series: {
        ...metadata,
        methodVersion: "wilder-rsi-14-v1",
        values: candles.map((_, index) => 30 + (index % 40)),
      },
    },
    macd: {
      ...snapshot.indicators.macd,
      series: {
        ...metadata,
        methodVersion: "macd-12-26-9-v1",
        line: candles.map((_, index) => index / 100),
        signal: candles.map((_, index) => index / 200),
        histogram: candles.map((_, index) => (index % 7) - 3),
      },
    },
  },
});

const deep = deepSnapshot(deepCandles, snapshot.source.decisionCutoff);

const viewportWidth = Dimensions.get("window").width;
const defaultWindowSize = readableWindowSize(resolveChartWidth(viewportWidth));

const visibleBodies = (view: Awaited<ReturnType<typeof render>>) =>
  view.getAllByTestId("chart-candle", hidden).map((candle) => candle.props);

async function selectedTimestamp(
  view: Awaited<ReturnType<typeof render>>,
  locationX: number,
) {
  await pressAt(
    view.getByRole("button", { name: /NVDA 图表摘要/ }),
    locationX,
  );
  return view.getByLabelText(/NVDA 收盘时间/).props.accessibilityLabel as string;
}

async function pinchBy(scale: number, focalX: number) {
  await act(async () => {
    fireGestureHandler<PinchGesture>(getByGestureTestId("chart-pinch"), [
      { state: State.BEGAN, scale: 1, focalX },
      { state: State.ACTIVE, scale, focalX },
      { state: State.END, scale, focalX },
    ]);
  });
}

async function dragBy(translationX: number) {
  await act(async () => {
    fireGestureHandler<PanGesture>(getByGestureTestId("chart-pan"), [
      { state: State.BEGAN, translationX: 0 },
      { state: State.ACTIVE, translationX: translationX / 2 },
      { state: State.ACTIVE, translationX },
      { state: State.END, translationX },
    ]);
  });
}

it("opens on a window dense enough to tell an up bar from a down bar", async () => {
  const view = await render(<PriceChart stock={deep} />);

  const bodies = visibleBodies(view);
  expect(bodies).toHaveLength(defaultWindowSize);
  expect(bodies.length).toBeLessThan(deepCandles.length);
  bodies.forEach(({ width }) => {
    expect(width).toBeGreaterThanOrEqual(minReadableBodyWidth);
  });
  // The newest bar is what the chart opens on.
  expect(await selectedTimestamp(view, 10_000)).toContain(
    deepCandles.at(-1)!.timestamp,
  );
});

it("thins the window on a pinch and leaves the bar under the fingers alone", async () => {
  const view = await render(<PriceChart stock={deep} />);
  const oldestBefore = await selectedTimestamp(view, 0);

  await pinchBy(2, 8);

  const bodies = visibleBodies(view);
  expect(bodies.length).toBeLessThan(defaultWindowSize);
  expect(bodies.length).toBeGreaterThanOrEqual(
    Math.floor(defaultWindowSize / 2) - 1,
  );
  // Pinched around the left edge, the leftmost bar is the anchor and stays.
  expect(await selectedTimestamp(view, 0)).toBe(oldestBefore);
  bodies.forEach(({ width }) => {
    expect(width).toBeGreaterThanOrEqual(minReadableBodyWidth);
  });
});

it("widens the window on a reverse pinch without passing the whole series", async () => {
  const view = await render(<PriceChart stock={deep} />);

  await pinchBy(0.05, 8);

  const bodies = visibleBodies(view);
  expect(bodies.length).toBeGreaterThan(defaultWindowSize);
  expect(bodies.length).toBeLessThanOrEqual(200);
});

it("drags back into history and stops at the oldest bar", async () => {
  const view = await render(<PriceChart stock={deep} />);
  const newest = await selectedTimestamp(view, 10_000);
  expect(newest).toContain(deepCandles.at(-1)!.timestamp);

  await dragBy(120);
  const stepped = await selectedTimestamp(view, 10_000);
  expect(stepped).not.toContain(deepCandles.at(-1)!.timestamp);

  await dragBy(90_000);
  expect(await selectedTimestamp(view, 0)).toContain(deepCandles[0]!.timestamp);
  // Already at the oldest bar: another drag has nowhere left to go.
  await dragBy(90_000);
  expect(await selectedTimestamp(view, 0)).toContain(deepCandles[0]!.timestamp);
  expect(visibleBodies(view)).toHaveLength(defaultWindowSize);

  await dragBy(-90_000);
  expect(await selectedTimestamp(view, 10_000)).toContain(
    deepCandles.at(-1)!.timestamp,
  );
});

it("keeps following the newest bar when a refresh brings two more", async () => {
  const view = await render(<PriceChart stock={deep} />);
  // A gesture takes the window over from the default that follows the newest
  // bar on its own, and it is that handed-over window a refresh used to strand:
  // the offset counts from the oldest bar, so two new bars at the other end
  // left the reader looking at neither the live edge nor anything they chose.
  await dragBy(-40);
  expect(await selectedTimestamp(view, 10_000)).toContain(
    deepCandles.at(-1)!.timestamp,
  );
  const drawn = visibleBodies(view).length;

  const refreshedCandles = [...deepCandles, candleAt(240), candleAt(241)];
  await act(async () => {
    view.rerender(
      <PriceChart
        stock={deepSnapshot(refreshedCandles, "2026-07-25T16:05:00.000Z")}
      />,
    );
  });

  expect(await selectedTimestamp(view, 10_000)).toContain(
    refreshedCandles.at(-1)!.timestamp,
  );
  // Following the newest bar is not the same as being reset: the reader keeps
  // the zoom they pinched to.
  expect(visibleBodies(view)).toHaveLength(drawn);
});

it("moves the volume, MACD, RSI and participation panels with the same drag", async () => {
  const view = await render(<PriceChart stock={deep} />);
  const labelsAt = () =>
    view
      .getAllByTestId(/^chart-time-label:/, hidden)
      .map((label) => (label.props.testID as string).replace("chart-time-label:", ""));
  const before = labelsAt();

  await dragBy(90_000);

  const bodies = visibleBodies(view);
  expect(labelsAt()).not.toEqual(before);
  expect(view.getAllByTestId("macd-histogram-bar", hidden)).toHaveLength(
    bodies.length,
  );
  expect(view.getAllByTestId("participation-available", hidden)).toHaveLength(
    bodies.length,
  );
  const rsiPath = view.getByTestId("rsi-line", hidden).props.d as string;
  const maPath = view.getByTestId("chart-overlay-ma5", hidden).props.d as string;
  // Every panel is cut from the same window, so each line starts on the very
  // first drawn bar and ends on the last one.
  const firstX = bodies[0]!.x + bodies[0]!.width / 2;
  const lastX = bodies.at(-1)!.x + bodies.at(-1)!.width / 2;
  [rsiPath, maPath].forEach((path) => {
    const xs = [...path.matchAll(/[ML] (-?[\d.]+)/g)].map(([, value]) =>
      Number(value),
    );
    // Path coordinates are written to two decimals.
    expect(Math.min(...xs)).toBeCloseTo(firstX, 2);
    expect(Math.max(...xs)).toBeCloseTo(lastX, 2);
  });
});

/** Every prop value the renderer would hand to the native SVG layer. */
const renderedValues = (node: unknown, collected: string[] = []): string[] => {
  if (Array.isArray(node)) {
    node.forEach((child) => renderedValues(child, collected));
    return collected;
  }
  if (!node || typeof node !== "object") return collected;
  const element = node as {
    props?: Record<string, unknown>;
    children?: unknown[];
  };
  Object.values(element.props ?? {}).forEach((value) => {
    if (typeof value === "number" || typeof value === "string") {
      collected.push(String(value));
    }
  });
  (element.children ?? []).forEach((child) => renderedValues(child, collected));
  return collected;
};

it("never hands the canvas a coordinate the device cannot draw", async () => {
  // A path of "M NaN 12" is not an error anywhere in JS: it renders as nothing
  // on the phone while every element the tests count is still present.
  const drawn = await render(<PriceChart stock={deep} />);
  const values = renderedValues(drawn.toJSON());
  expect(values.length).toBeGreaterThan(100);
  values.forEach((value) => {
    expect(value).not.toMatch(/NaN|Infinity/);
  });

  // The same guarantee where the arithmetic has nothing to work with: every
  // bar of this snapshot closed after the decision cutoff.
  const nothingDecided = await render(
    <PriceChart stock={deepSnapshot(deepCandles, "2026-07-25T11:00:00.000Z")} />,
  );
  renderedValues(nothingDecided.toJSON()).forEach((value) => {
    expect(value).not.toMatch(/NaN|Infinity/);
  });
  expect(
    nothingDecided.queryAllByTestId("chart-candle", hidden),
  ).toHaveLength(0);
});

it("keeps the chart on the page surface instead of a dark island", async () => {
  const view = await render(<PriceChart stock={snapshot} />);

  const card = StyleSheet.flatten(
    view.getByTestId("stock-chart-card").props.style,
  );
  expect(card.backgroundColor).toBe(colors.card);
  expect(card.borderColor).toBe(colors.line);
});

it("names every indicator line the server has not published", async () => {
  const view = await render(<PriceChart stock={snapshot} />);

  expect(view.getByTestId("chart-series-missing")).toHaveTextContent(
    "MA5 / MACD / RSI 曲线缺失 · 服务端未提供版本化序列",
  );
  expect(view.queryByTestId("chart-overlay-ma5", hidden)).toBeNull();
  expect(view.queryByTestId("macd-dif-line", hidden)).toBeNull();
  expect(view.queryByTestId("macd-dea-line", hidden)).toBeNull();
  expect(view.queryByTestId("rsi-line", hidden)).toBeNull();
  expect(view.queryAllByTestId("macd-histogram-bar", hidden)).toHaveLength(0);
  // The panels stay, so the reader sees which frames are waiting on data.
  expect(view.getByTestId("macd-panel", hidden)).toBeTruthy();
  expect(view.getByTestId("rsi-panel", hidden)).toBeTruthy();
  expect(view.queryByText("MA5")).toBeNull();
});

it("draws the moving average, MACD and RSI the server did publish", async () => {
  const view = await render(<PriceChart stock={withSeries} />);

  expect(view.queryByTestId("chart-series-missing")).toBeNull();
  expect(view.getByTestId("chart-overlay-ma5", hidden)).toBeTruthy();
  expect(view.getByTestId("macd-dif-line", hidden)).toBeTruthy();
  expect(view.getByTestId("macd-dea-line", hidden)).toBeTruthy();
  expect(view.getByTestId("rsi-line", hidden)).toBeTruthy();
  expect(view.getAllByTestId("macd-histogram-bar", hidden)).toHaveLength(2);
  expect(view.getByText("MA5")).toBeTruthy();
});

it("holds the MA5 line back until the server series covers the drawn bars", async () => {
  const warmingUp: ChartSnapshot = {
    ...withSeries,
    indicators: {
      ...withSeries.indicators,
      ma5: {
        ...withSeries.indicators.ma5,
        series: {
          ...metadata,
          methodVersion: "sma-5-v1",
          values: [null, null],
        },
      },
    },
  };
  const view = await render(<PriceChart stock={warmingUp} />);

  expect(view.queryByTestId("chart-overlay-ma5", hidden)).toBeNull();
  expect(view.getByTestId("chart-series-missing")).toHaveTextContent(
    "MA5 曲线缺失 · 服务端序列尚未覆盖已绘制的 K 线",
  );
});

it("labels the ordinal axis with the real clock time of each bar", async () => {
  const view = await render(<PriceChart stock={snapshot} />);

  const labels = view
    .getAllByTestId(/^chart-time-label:/, hidden)
    .map((label) =>
      (label.props.testID as string).replace("chart-time-label:", ""),
    );
  expect(labels).toEqual(["15:50", "15:55"]);
});

it("reads participation as a lean away from an even split", async () => {
  const view = await render(<PriceChart stock={snapshot} />);

  expect(view.getAllByTestId("participation-available", hidden)).toHaveLength(1);
  expect(view.getAllByTestId("participation-main", hidden)).toHaveLength(1);
  expect(view.queryAllByTestId("participation-retail", hidden)).toHaveLength(0);
  expect(view.getAllByTestId("participation-missing", hidden)).toHaveLength(1);
  expect(view.getByTestId("participation-even-line", hidden)).toBeTruthy();
});

it("hides the participation legend, marks, and selected detail together", async () => {
  const view = await render(
    <PriceChart showParticipation={false} stock={snapshot} />,
  );

  expect(view.queryByText("主力代理")).toBeNull();
  expect(view.queryByTestId("participation-available", hidden)).toBeNull();
  expect(view.queryByTestId("participation-missing", hidden)).toBeNull();
  expect(view.queryByTestId("participation-even-line", hidden)).toBeNull();

  const selector = view.getByRole("button", { name: /NVDA 图表摘要/ });
  await pressAt(selector, 0);
  expect(view.getByLabelText(/NVDA 收盘时间/).props.accessibilityLabel).toBe(
    "NVDA 收盘时间 2026-07-25T15:50:00.000Z；开 140.00，高 141.00，低 139.50，收 140.50，成交量 1200",
  );
  expect(view.queryByTestId("participation-detail-text")).toBeNull();
  expect(view.queryByText("订单规模活动代理 · 非真实机构身份")).toBeNull();
});

it("shows the nine count as progress toward nine instead of a floating circle", async () => {
  const view = await render(<PriceChart stock={snapshot} />);

  expect(view.getByText("九转 看涨 2/9")).toBeTruthy();
  expect(view.getAllByTestId("magic-nine-step-filled")).toHaveLength(2);
  expect(view.getAllByTestId("magic-nine-step-empty")).toHaveLength(7);
  // Nothing is drawn on a bar until the server names which bar it was.
  expect(view.queryByTestId("magic-nine-marker", hidden)).toBeNull();
});

it("marks the exact bar the server confirmed a nine on", async () => {
  const thirdCandle = {
    timestamp: "2026-07-25T15:45:00.000Z",
    availableAt: "2026-07-25T15:45:01.000Z",
    complete: true,
    open: 139.5,
    high: 140.2,
    low: 139,
    close: 140,
    volume: 900,
  };
  const confirmedAt = (confirmedAtIndex: number): ChartSnapshot => ({
    ...snapshot,
    candles: [thirdCandle, ...snapshot.candles],
    participationBars: [],
    magicNine: {
      ...snapshot.magicNine,
      direction: "bearish",
      count: 9,
      completed: true,
      confirmedAtIndex,
    },
  });

  const first = await render(<PriceChart stock={confirmedAt(0)} />);
  expect(first.getByText("九转 看跌 9/9 · 序列完成")).toBeTruthy();
  expect(first.getAllByTestId("magic-nine-step-filled")).toHaveLength(9);
  const firstX = first.getByTestId("magic-nine-marker", hidden).props.x;

  const last = await render(<PriceChart stock={confirmedAt(2)} />);
  const lastX = last.getByTestId("magic-nine-marker", hidden).props.x;

  // The mark follows the index the server named, so it cannot be parked on the
  // newest bar and still look right.
  expect(firstX).toBeLessThan(lastX);
});

it("draws every published TD count across a complete run", async () => {
  const candles = Array.from({ length: 9 }, (_, index) => ({
    ...snapshot.candles[0]!,
    timestamp: `2026-07-25T15:${String(5 + index * 5).padStart(2, "0")}:00.000Z`,
    availableAt: `2026-07-25T15:${String(5 + index * 5).padStart(2, "0")}:01.000Z`,
    close: 132 + index,
  }));
  const view = await render(
    <PriceChart
      stock={{
        ...snapshot,
        candles,
        participationBars: [],
        magicNine: {
          ...snapshot.magicNine,
          direction: "bearish",
          count: 9,
          completed: true,
          confirmedAtIndex: 8,
          series: Array.from({ length: 9 }, (_, index) => ({
            direction: "bearish" as const,
            count: index + 1,
          })),
        },
      }}
    />,
  );

  expect(
    view.getAllByTestId("magic-nine-series-marker", hidden),
  ).toHaveLength(9);
  expect(
    view
      .getAllByTestId("magic-nine-series-label", hidden)
      .map((node) =>
        String(
          (node.props.children as { props?: { children?: unknown } }).props
            ?.children,
        ),
      ),
  ).toEqual(["1", "2", "3", "4", "5", "6", "7", "8", "9"]);
});

it("does not draw a false magic-nine zero when the indicator is unavailable", async () => {
  const unavailableMagic: ChartSnapshot = {
    ...snapshot,
    magicNine: {
      ...snapshot.magicNine,
      direction: null,
      // A count the server no longer stands behind: unavailable outranks it,
      // and none of the nine steps may be painted from it.
      count: 7,
      completed: false,
      confirmedAtIndex: null,
      qualityStatus: "unavailable",
    },
  };
  const view = await render(<PriceChart stock={unavailableMagic} />);

  expect(view.getByText("九转 暂不可用")).toBeTruthy();
  expect(view.queryByTestId("magic-nine-marker", hidden)).toBeNull();
  expect(view.queryAllByTestId("magic-nine-step-filled")).toHaveLength(0);
  expect(view.getAllByTestId("magic-nine-step-empty")).toHaveLength(9);
  expect(view.queryByText("九转 无方向 7/9")).toBeNull();
});

it("labels a stale chart without also claiming live data", async () => {
  const staleSnapshot: ChartSnapshot = {
    ...snapshot,
    source: { ...snapshot.source, status: "stale" },
  };
  const view = await render(<PriceChart stock={staleSnapshot} />);

  expect(view.getByText("5 分钟 · 缓存数据")).toBeTruthy();
  expect(view.queryByText("5 分钟 · 实时只读")).toBeNull();
});

it("names the final completed close as its candles-only price basis", async () => {
  const candlesOnly: ChartSnapshot = {
    ...snapshot,
    interval: "day",
    quote: null,
  };
  const view = await render(<PriceChart stock={candlesOnly} />);

  const chart = view.getByRole("button", { name: /NVDA 图表摘要/ });
  expect(chart.props.accessibilityLabel).toContain("最新日K收盘 141.50");
  expect(chart.props.accessibilityLabel).toContain("实时报价不可用");
  expect(chart.props.accessibilityLabel).not.toContain("涨跌");
  expect(chart.props.accessibilityLabel).not.toMatch(/NaN|Infinity/);
});

it("shows an honest non-interactive state when only a quote is available", async () => {
  const quoteOnly: ChartSnapshot = {
    ...snapshot,
    interval: "day",
    candles: [],
    participationBars: [],
  };
  const view = await render(<PriceChart stock={quoteOnly} />);

  expect(view.getByText("暂无已完成日K")).toBeTruthy();
  const empty = view.getByTestId("price-chart-empty");
  expect(empty.props.accessibilityLabel).toContain("暂无已完成日K");
  expect(empty.props.accessibilityLabel).toContain("当前报价 141.50");
  expect(empty.props.accessibilityLabel).not.toMatch(/NaN|Infinity/);
  expect(view.queryByRole("button", { name: /图表摘要/ })).toBeNull();
  renderedValues(view.toJSON()).forEach((value) => {
    expect(value).not.toMatch(/NaN|Infinity/);
  });
});

it("selects the nearest candle by tap with exact accessible detail", async () => {
  const view = await render(<PriceChart stock={snapshot} />);
  const selector = view.getByRole("button", {
    name: /NVDA 图表摘要.*轻点或长按选择最近的 K 线/,
  });
  expect(StyleSheet.flatten(selector.props.style).minHeight).toBeGreaterThanOrEqual(44);
  expect(view.getByText("轻点或长按图表读取精确 K 线")).toBeTruthy();

  await pressAt(selector, 0);
  expect(view.getByLabelText(/NVDA 收盘时间/).props.accessibilityLabel).toBe(
    "NVDA 收盘时间 2026-07-25T15:50:00.000Z；开 140.00，高 141.00，低 139.50，收 140.50，成交量 1200；主力代理 60.00%，散户代理 40.00%，覆盖率 100.00%，来源 moomoo；非真实机构身份",
  );
  expect(view.getByTestId("chart-crosshair", hidden)).toBeTruthy();
});

it("uses locationX to select both candles", async () => {
  const view = await render(<PriceChart stock={snapshot} />);
  const selector = view.getByRole("button", {
    name: /NVDA 图表摘要/,
  });

  await pressAt(selector, 0);
  expect(view.getByLabelText(/NVDA 收盘时间/).props.accessibilityLabel).toContain(
    snapshot.candles[0]!.timestamp,
  );

  await pressAt(selector, 10_000);
  expect(view.getByLabelText(/NVDA 收盘时间/).props.accessibilityLabel).toContain(
    snapshot.candles[1]!.timestamp,
  );
});

it("selects a missing nearest candle by long press without inventing shares", async () => {
  const longReason =
    "capital flow unavailable because the provider returned an extended diagnostic reason";
  const unavailableFirst: ChartSnapshot = {
    ...snapshot,
    participationBars: [
      {
        ...snapshot.participationBars[1]!,
        closedAt: snapshot.candles[0]!.timestamp,
        asOf: snapshot.candles[0]!.timestamp,
        availableAt: snapshot.candles[0]!.availableAt,
        missingReason: longReason,
      },
      {
        ...snapshot.participationBars[0]!,
        closedAt: snapshot.candles[1]!.timestamp,
        asOf: snapshot.candles[1]!.timestamp,
        availableAt: snapshot.candles[1]!.availableAt,
      },
    ],
  };
  const longPressView = await render(<PriceChart stock={unavailableFirst} />);
  const longPressTarget = longPressView.getByRole("button", {
    name: /NVDA 图表摘要/,
  });
  const user = userEvent.setup();
  const detailBefore = longPressView.getByTestId("chart-detail-strip");
  const minHeightBefore = StyleSheet.flatten(detailBefore.props.style).minHeight;

  await user.longPress(longPressTarget, { duration: 600 });

  const detailAfter = longPressView.getByTestId("chart-detail-strip");
  expect(detailAfter).toBe(detailBefore);
  expect(StyleSheet.flatten(detailAfter.props.style).minHeight).toBe(
    minHeightBefore,
  );
  expect(
    longPressView.getByTestId("participation-detail-text").props,
  ).toMatchObject({
    ellipsizeMode: "tail",
    numberOfLines: 2,
  });
  expect(
    longPressView.getByLabelText(/NVDA 收盘时间/).props.accessibilityLabel,
  ).toBe(
    `NVDA 收盘时间 2026-07-25T15:50:00.000Z；开 140.00，高 141.00，低 139.50，收 140.50，成交量 1200；活动占比缺失，覆盖率 0.00%，来源 moomoo，原因 ${longReason}；非真实机构身份`,
  );
});

it("excludes future live data from null-forecast geometry and selection", async () => {
  const futureTimestamp = "2026-07-25T16:00:00.000Z";
  const futureSnapshot: ChartSnapshot = {
    ...snapshot,
    candles: [
      ...snapshot.candles,
      {
        timestamp: futureTimestamp,
        availableAt: "2026-07-25T16:00:01.000Z",
        complete: true,
        open: 500,
        high: 600,
        low: 400,
        close: 550,
        volume: 99_999,
      },
    ],
    participationBars: [
      ...snapshot.participationBars,
      {
        ...snapshot.participationBars[0]!,
        closedAt: futureTimestamp,
        availableAt: "2026-07-25T16:00:01.000Z",
      },
    ],
  };
  const view = await render(<PriceChart stock={futureSnapshot} />);
  expect(
    view.getByRole("button", {
      name: /NVDA 图表摘要，2 根已完成 K 线/,
    }),
  ).toBeTruthy();
  const selector = view.getByRole("button", {
    name: /NVDA 图表摘要/,
  });

  await pressAt(selector, 10_000);

  expect(view.queryByText(new RegExp(futureTimestamp))).toBeNull();
  expect(view.getByLabelText(/NVDA 收盘时间/).props.accessibilityLabel).toContain(
    snapshot.candles[1]!.timestamp,
  );
  expect(view.getByLabelText(/NVDA 收盘时间/).props.accessibilityLabel).not.toContain(
    futureTimestamp,
  );
});

it("never exposes post-cutoff participation metadata in selected detail", async () => {
  const postCutoffSnapshot: ChartSnapshot = {
    ...snapshot,
    participationBars: [
      {
        ...snapshot.participationBars[1]!,
        closedAt: snapshot.candles[0]!.timestamp,
        availableAt: "2026-07-25T16:00:01.000Z",
        coverage: 0.37,
        source: "post-cutoff-secret-source",
        missingReason: "post-cutoff-secret-reason",
      },
      snapshot.participationBars[1]!,
    ],
  };
  const view = await render(<PriceChart stock={postCutoffSnapshot} />);
  const selector = view.getByRole("button", {
    name: /NVDA 图表摘要/,
  });

  await pressAt(selector, 0);

  const label = view.getByLabelText(/NVDA 收盘时间/).props
    .accessibilityLabel as string;
  expect(label).toContain(
    "活动占比缺失，覆盖率不可用，来源不可用，原因 决策截止时不可用",
  );
  expect(label).not.toContain("37.00%");
  expect(label).not.toContain("post-cutoff-secret-source");
  expect(label).not.toContain("post-cutoff-secret-reason");
});
