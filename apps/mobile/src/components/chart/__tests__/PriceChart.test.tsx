import { expect, it } from "@jest/globals";
import { render, userEvent } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import type { ChartSnapshot } from "@/domain/models";

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
    ma5: { ...metadata, value: 140.8 },
    rsi: { ...metadata, value: 56.2 },
    macd: {
      ...metadata,
      line: 0.45,
      signal: 0.3,
      histogram: 0.15,
    },
  },
  magicNine: {
    ...metadata,
    direction: "bullish",
    count: 2,
    completed: false,
    confirmedAtIndex: null,
  },
  forecast: null,
};

it("renders aligned participation semantics without inventing a live forecast", async () => {
  const view = await render(<PriceChart stock={snapshot} />);

  expect(
    view.getByText("订单规模活动占比 · 深色主力代理 / 浅色散户代理"),
  ).toBeTruthy();
  expect(
    view.getAllByTestId("participation-available", {
      includeHiddenElements: true,
    }),
  ).toHaveLength(1);
  expect(
    view.getAllByTestId("participation-main", { includeHiddenElements: true }),
  ).toHaveLength(1);
  expect(
    view.getAllByTestId("participation-retail", { includeHiddenElements: true }),
  ).toHaveLength(1);
  expect(
    view.getAllByTestId("participation-missing", { includeHiddenElements: true }),
  ).toHaveLength(1);
  expect(view.getByText("价格 · 成交量")).toBeTruthy();
  expect(view.queryByText("价格 · 成交量 · 概率预测")).toBeNull();
  expect(view.queryByText("上涨概率")).toBeNull();
  expect(view.queryByText("现在 / 预测起点")).toBeNull();
});

it("selects the nearest candle by tap with exact accessible detail", async () => {
  const view = await render(<PriceChart stock={snapshot} />);
  const user = userEvent.setup();
  const selector = view.getByRole("button", {
    name: /NVDA 图表摘要.*轻点或长按选择最近的 K 线/,
  });

  expect(StyleSheet.flatten(selector.props.style).minHeight).toBeGreaterThanOrEqual(44);
  expect(view.getByText("轻点或长按图表查看精确 K 线数据")).toBeTruthy();

  await user.press(selector);
  expect(view.getByLabelText(/NVDA 收盘时间/).props.accessibilityLabel).toBe(
    "NVDA 收盘时间 2026-07-25T15:50:00.000Z；开 140.00，高 141.00，低 139.50，收 140.50，成交量 1200；主力代理 60.00%，散户代理 40.00%，覆盖率 100.00%，来源 moomoo；非真实机构身份",
  );
});

it("selects a missing nearest candle by long press without inventing shares", async () => {
  const unavailableFirst: ChartSnapshot = {
    ...snapshot,
    participationBars: [
      {
        ...snapshot.participationBars[1]!,
        closedAt: snapshot.candles[0]!.timestamp,
        asOf: snapshot.candles[0]!.timestamp,
        availableAt: snapshot.candles[0]!.availableAt,
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
  const user = userEvent.setup();
  const longPressSelector = longPressView.getByRole("button", {
    name: /NVDA 图表摘要.*轻点或长按选择最近的 K 线/,
  });

  await user.longPress(longPressSelector, { duration: 600 });
  expect(
    longPressView.getByLabelText(/NVDA 收盘时间/).props.accessibilityLabel,
  ).toBe(
    "NVDA 收盘时间 2026-07-25T15:50:00.000Z；开 140.00，高 141.00，低 139.50，收 140.50，成交量 1200；活动占比缺失，覆盖率 0.00%，来源 moomoo，原因 capital flow unavailable；非真实机构身份",
  );
});
