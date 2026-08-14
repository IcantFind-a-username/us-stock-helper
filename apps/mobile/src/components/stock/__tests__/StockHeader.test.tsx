import { expect, it, jest } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { toDemoChartSnapshot, type ChartSnapshot } from "@/domain/models";
import { stockFixtures } from "@/fixtures/stocks";
import { StockHeader } from "../StockHeader";

function baseSnapshot(): ChartSnapshot {
  return toDemoChartSnapshot(stockFixtures["NVDA:short"]!);
}

it("keeps quote-present price and percentage rendering unchanged", async () => {
  const snapshot = baseSnapshot();
  const view = await render(
    <StockHeader dataStatus="live" stock={snapshot} onBack={jest.fn()} />,
  );

  expect(view.getByText("$143.80")).toBeTruthy();
  expect(view.getByText("+2.46%")).toBeTruthy();
  expect(view.getByText("实时只读")).toBeTruthy();
});

it("uses only the final completed candle close without inventing a percentage", async () => {
  const base = baseSnapshot();
  const completed = {
    ...base.candles.at(-1)!,
    close: 138.766,
  };
  const incomplete = {
    ...completed,
    timestamp: "2026-07-27T20:00:00.000Z",
    close: 999,
    complete: false,
  };
  const snapshot: ChartSnapshot = {
    ...base,
    candles: [...base.candles.slice(0, -1), completed, incomplete],
    interval: "day",
    quote: null,
  };
  const view = await render(
    <StockHeader dataStatus="live" stock={snapshot} onBack={jest.fn()} />,
  );

  expect(view.getByText("$138.77")).toBeTruthy();
  expect(view.getByText("最新日K收盘")).toBeTruthy();
  expect(view.queryByText("$999.00")).toBeNull();
  expect(view.queryByText(/[+-]\d+(?:\.\d+)?%/)).toBeNull();
  expect(view.queryByText("报价不可用")).toBeNull();
  expect(view.queryByText("实时只读")).toBeNull();
});

it("keeps a quote-only price and percentage without claiming candles", async () => {
  const snapshot: ChartSnapshot = { ...baseSnapshot(), candles: [] };
  const view = await render(
    <StockHeader dataStatus="live" stock={snapshot} onBack={jest.fn()} />,
  );

  expect(view.getByText("$143.80")).toBeTruthy();
  expect(view.getByText("+2.46%")).toBeTruthy();
  expect(view.queryByText("最新日K收盘")).toBeNull();
});
