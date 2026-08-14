import { expect, it, jest } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { toDemoChartSnapshot, type ChartSnapshot } from "@/domain/models";
import { stockFixtures } from "@/fixtures/stocks";
import { StockHeader } from "../StockHeader";

it("labels a candles-only snapshot without inventing a quote", async () => {
  const snapshot: ChartSnapshot = {
    ...toDemoChartSnapshot(stockFixtures["NVDA:short"]!),
    quote: null,
  };
  const view = await render(
    <StockHeader stock={snapshot} onBack={jest.fn()} />,
  );

  expect(view.getByText("报价不可用")).toBeTruthy();
  expect(view.getByText("仅显示已完成 K 线")).toBeTruthy();
});
