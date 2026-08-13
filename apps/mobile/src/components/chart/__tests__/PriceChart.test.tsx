import { expect, it } from "@jest/globals";
import {
  act,
  render,
  userEvent,
} from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import type { ChartSnapshot } from "@/domain/models";
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
