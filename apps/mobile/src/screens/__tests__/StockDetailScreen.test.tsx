import { beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { AppStateProvider } from "@/state/AppStateProvider";

import { StockDetailScreen } from "../StockDetailScreen";

const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ symbol: "NVDA" }),
  useRouter: () => ({ back: jest.fn(), push: mockPush }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  mockPush.mockClear();
});

it("keeps chart, momentum indicators, participation methodology, and market context visible", async () => {
  const view = await render(
    <AppStateProvider>
      <StockDetailScreen />
    </AppStateProvider>,
  );

  await waitFor(() => expect(view.getByText("NVIDIA")).toBeTruthy());

  expect(view.getAllByText("演示数据 · 非实时行情")).toHaveLength(1);
  expect(view.getByText("谨慎偏多；等待量价确认，不追高。")).toBeTruthy();
  expect(view.getByTestId("stock-chart-card")).toBeTruthy();
  expect(view.getByText("九转 7 · 尚未完成")).toBeTruthy();

  expect(view.getByTestId("indicator-rsi")).toBeTruthy();
  expect(view.getByText("RSI 63.8")).toBeTruthy();
  expect(view.getByText("接近超买")).toBeTruthy();
  expect(view.getByTestId("indicator-macd")).toBeTruthy();
  expect(view.getByText("多头扩张")).toBeTruthy();

  expect(view.getByTestId("participation-proxy")).toBeTruthy();
  expect(view.getByText("估算代理")).toBeTruthy();
  expect(view.getByText("机构代理 58%")).toBeTruthy();
  expect(view.getByText("散户代理 42%")).toBeTruthy();
  expect(view.getByText(/并非真实账户身份/)).toBeTruthy();
  expect(view.getByText(/报告期 2026-06-30/)).toBeTruthy();

  expect(view.getByTestId("market-context-card")).toBeTruthy();
  expect(view.getByText("纳指短线偏强，但广度一般")).toBeTruthy();
  expect(view.getByText("出口限制消息构成双向事件风险")).toBeTruthy();

  await fireEvent.press(
    view.getByRole("button", { name: "机构流代理，已显示" }),
  );
  expect(view.queryByTestId("participation-proxy")).toBeNull();
  expect(
    view.getByRole("button", { name: "机构流代理，已隐藏" }),
  ).toBeTruthy();

  await fireEvent.press(
    view.getByRole("button", { name: "预测区间，已显示" }),
  );
  expect(view.queryByText("概率预测，不是未来价格承诺")).toBeNull();

  fireEvent.press(view.getByRole("button", { name: "问顾问 / 制定方案" }));
  expect(mockPush).toHaveBeenLastCalledWith({
    pathname: "/stocks/[symbol]/advisers",
    params: { symbol: "NVDA" },
  });
});
