import { expect, it, jest } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { StockSearchSheet, type StockSearchOption } from "../StockSearchSheet";

const mockOptions: StockSearchOption[] = [
  { symbol: "AAPL", company: "Apple Inc.", price: 150.0, changePercent: 2.5 },
];

it("renders real mode without any 演示 labels", async () => {
  const view = await render(
    <StockSearchSheet
      demoMode={false}
      visible={true}
      options={mockOptions}
      onClose={jest.fn()}
      onSelect={jest.fn()}
    />,
  );

  // In real mode, should NOT contain any 演示 text
  expect(() => view.getByText(/演示/)).toThrow();

  // Should show watchlist-scoped copy and note that global search is not yet served
  expect(view.getByText(/我的关注/)).toBeTruthy();
  expect(view.getByText(/全市场搜索尚未接入|搜索范围/)).toBeTruthy();
});

it("renders demo mode with 演示 labels in the header", async () => {
  const view = await render(
    <StockSearchSheet
      demoMode={true}
      visible={true}
      options={mockOptions}
      onClose={jest.fn()}
      onSelect={jest.fn()}
    />,
  );

  // In demo mode, should contain 演示 labels
  expect(view.getByText(/本地关注列表 · 演示/)).toBeTruthy();
});

it("shows real mode empty copy without 演示 when no results match", async () => {
  const view = await render(
    <StockSearchSheet
      demoMode={false}
      visible={true}
      options={[]}
      onClose={jest.fn()}
      onSelect={jest.fn()}
    />,
  );

  // In real mode with empty results, should NOT have 演示 in empty state
  expect(() => view.getByText(/没有匹配的演示标的/)).toThrow();

  // Should show honest empty message for watchlist scope
  expect(view.getByText(/关注列表里没有匹配的标的/)).toBeTruthy();
});

it("shows demo mode empty copy with 演示 when no results match", async () => {
  const view = await render(
    <StockSearchSheet
      demoMode={true}
      visible={true}
      options={[]}
      onClose={jest.fn()}
      onSelect={jest.fn()}
    />,
  );

  // In demo mode with empty results, should keep the 演示 label
  expect(view.getByText(/没有匹配的演示标的/)).toBeTruthy();
});
