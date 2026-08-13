import { expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import {
  COLLAPSED_WATCHLIST_COUNT,
  visibleWatchlistQuotes,
  WatchlistPanel,
} from "@/components/dashboard/WatchlistPanel";
import { MarketDataError } from "@/data/marketRepository";
import type { DecisionScore, WatchlistQuote } from "@/domain/models";
import type { WatchlistDecisionState } from "@/state/MarketDataProvider";

function quote(index: number): WatchlistQuote {
  return {
    symbol: `SYM${String(index).padStart(2, "0")}`,
    price: 100 + index,
    changePercent: index % 2 === 0 ? 1.25 : -0.4,
    direction: index % 2 === 0 ? "bullish" : "bearish",
    summary: "实时只读",
  };
}

const fortySix = Array.from({ length: 46 }, (_, index) => quote(index));

function score(value: number, overrides: Partial<DecisionScore> = {}): DecisionScore {
  return {
    value,
    direction: "bullish",
    actionable: true,
    methodVersion: "explainable-horizon-score-v1",
    factorCoverage: 0.7,
    unavailableFactors: ["macro"],
    blockedBy: [],
    contributions: [
      {
        name: "technical_trend",
        rawValue: 0.57,
        weight: 0.36,
        points: 10.1,
        explanation: "Closed-bar return.",
      },
    ],
    ...overrides,
  };
}

function renderPanel({
  quotes = fortySix,
  decisions = {},
  expanded = false,
  onPress = jest.fn(),
  onToggleExpanded = jest.fn(),
  onOpenSource = jest.fn(),
}: {
  quotes?: WatchlistQuote[];
  decisions?: Record<string, WatchlistDecisionState>;
  expanded?: boolean;
  onPress?: (symbol: string) => void;
  onToggleExpanded?: () => void;
  onOpenSource?: () => void;
} = {}) {
  return render(
    <WatchlistPanel
      accessibilityLabel="自选行情，实时"
      decisions={decisions}
      expanded={expanded}
      onOpenSource={onOpenSource}
      onPress={onPress}
      onToggleExpanded={onToggleExpanded}
      quotes={quotes}
    />,
  );
}

it("shows the whole watchlist once it is expanded", async () => {
  const view = await renderPanel({ expanded: true });

  expect(view.getAllByTestId("watchlist-quote")).toHaveLength(46);
  expect(view.getByText("SYM45")).toBeTruthy();
  expect(view.getByTestId("watchlist-count").props.children).toBe(
    "共 46 只 · 已全部显示",
  );
  expect(view.getByRole("button", { name: "收起自选列表" })).toBeTruthy();
});

it("says how many are hidden instead of quietly dropping them", async () => {
  const onToggleExpanded = jest.fn();
  const view = await renderPanel({ onToggleExpanded });

  expect(view.getAllByTestId("watchlist-quote")).toHaveLength(
    COLLAPSED_WATCHLIST_COUNT,
  );
  expect(view.getByTestId("watchlist-count").props.children).toBe(
    `共 46 只 · 已显示 ${COLLAPSED_WATCHLIST_COUNT} 只`,
  );
  const expand = view.getByRole("button", { name: "查看全部 46 只自选" });
  expect(StyleSheet.flatten(expand.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(expand);
  expect(onToggleExpanded).toHaveBeenCalledTimes(1);
});

it("offers no expander when nothing is hidden", async () => {
  const view = await renderPanel({ quotes: fortySix.slice(0, 3) });

  expect(view.getAllByTestId("watchlist-quote")).toHaveLength(3);
  expect(view.getByTestId("watchlist-count").props.children).toBe(
    "共 3 只 · 已全部显示",
  );
  expect(view.queryByRole("button", { name: /查看全部/ })).toBeNull();
});

it("routes every single row to its own symbol", async () => {
  const opened: string[] = [];
  const view = await renderPanel({
    expanded: true,
    onPress: (symbol) => opened.push(symbol),
  });

  const rows = view.getAllByTestId("watchlist-quote");
  expect(rows).toHaveLength(46);
  for (const row of rows) {
    expect(StyleSheet.flatten(row.props.style).minHeight).toBeGreaterThanOrEqual(44);
    await fireEvent.press(row);
  }

  expect(opened).toEqual(fortySix.map((item) => item.symbol));
});

it("labels each score state instead of leaving the cell blank", async () => {
  const view = await renderPanel({
    quotes: [
      { ...quote(0), symbol: "SCORED" },
      { ...quote(1), symbol: "PENDING" },
      { ...quote(2), symbol: "BROKEN" },
      { ...quote(3), symbol: "BLANK" },
      { ...quote(4), symbol: "DEMO" },
    ],
    decisions: {
      SCORED: {
        status: "scored",
        score: score(72.5),
        error: null,
        notes: [],
      },
      PENDING: { status: "loading", score: null, error: null, notes: [] },
      BROKEN: {
        status: "unavailable",
        score: null,
        error: new MarketDataError("offline", "analysis service is unavailable"),
        notes: [],
      },
      BLANK: {
        status: "unscored",
        score: null,
        error: null,
        notes: ["没有任何来源覆盖该标的的因子。"],
      },
      DEMO: { status: "demo", score: null, error: null, notes: [] },
    },
  });

  expect(view.getByTestId("watchlist-score-SCORED").props.children).toBe("73");
  expect(view.getByText("偏多 · 覆盖 70%")).toBeTruthy();
  expect(view.getByTestId("watchlist-score-PENDING").props.children).toBe("…");
  expect(view.getByText("读取中")).toBeTruthy();
  expect(view.getByTestId("watchlist-score-BROKEN").props.children).toBe("—");
  expect(view.getByText("不可用 · offline")).toBeTruthy();
  expect(view.getByTestId("watchlist-score-BLANK").props.children).toBe("—");
  expect(view.getByText("未给出评分")).toBeTruthy();
  expect(view.getByTestId("watchlist-score-DEMO").props.children).toBe("—");
  expect(view.getByText("演示无评分")).toBeTruthy();

  expect(
    view.getByLabelText(/查看 SCORED 行情详情.*评分 73 · 偏多 · 因子覆盖 70%$/),
  ).toBeTruthy();
  expect(view.getByLabelText(/查看 PENDING 行情详情.*评分读取中$/)).toBeTruthy();
  expect(
    view.getByLabelText(/查看 BROKEN 行情详情.*评分不可用 · offline$/),
  ).toBeTruthy();
  expect(view.getByLabelText(/查看 BLANK 行情详情.*分析未给出评分$/)).toBeTruthy();
  expect(
    view.getByLabelText(/查看 DEMO 行情详情.*演示模式不提供评分$/),
  ).toBeTruthy();
});

it("treats a row the caller never asked about as pending, not as scoreless", async () => {
  const view = await renderPanel({ quotes: [quote(0)], decisions: {} });

  expect(view.getByTestId("watchlist-score-SYM00").props.children).toBe("…");
  expect(view.getByText("读取中")).toBeTruthy();
});

it("carries the direction of a bearish score into the row", async () => {
  const view = await renderPanel({
    quotes: [{ ...quote(0), symbol: "BEAR" }],
    decisions: {
      BEAR: {
        status: "scored",
        score: score(28, { direction: "bearish", factorCoverage: 1 }),
        error: null,
        notes: [],
      },
    },
  });

  expect(view.getByTestId("watchlist-score-BEAR").props.children).toBe("28");
  expect(view.getByText("偏空 · 覆盖 100%")).toBeTruthy();
});

it("slices the same way the screen does when it decides what to request", () => {
  expect(visibleWatchlistQuotes(fortySix, false)).toHaveLength(
    COLLAPSED_WATCHLIST_COUNT,
  );
  expect(visibleWatchlistQuotes(fortySix, true)).toHaveLength(46);
  expect(visibleWatchlistQuotes(fortySix.slice(0, 2), false)).toHaveLength(2);
});
