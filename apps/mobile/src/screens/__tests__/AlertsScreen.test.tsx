import { expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";

import { AlertsScreen } from "../AlertsScreen";
import { MarketDataProvider } from "@/state/MarketDataProvider";
import type { MarketRepository } from "@/data/marketRepository";

const idleRepository = {
  loadWatchlist: async () => {
    throw new Error("not used in this test");
  },
  loadSnapshot: async () => {
    throw new Error("not used in this test");
  },
} as unknown as MarketRepository;


const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

it("filters four evidence-gated alert classes and opens their stock context", async () => {
  const view = await render(<MarketDataProvider development initialDemoMode repository={idleRepository}>
      <AlertsScreen />
    </MarketDataProvider>);

  expect(view.getByText("提醒中心")).toBeTruthy();
  expect(view.getByText("NVDA 接近量价确认区")).toBeTruthy();
  expect(view.getByText("TSLA 事件波动与利润率分歧扩大")).toBeTruthy();
  expect(view.getByText("PLTR 进入高估值与超买观察区")).toBeTruthy();
  expect(view.getByText("机构持仓报告存在披露时滞")).toBeTruthy();

  await fireEvent.press(view.getByRole("button", { name: "只看风险提醒" }));
  expect(view.queryByText("NVDA 接近量价确认区")).toBeNull();
  expect(view.getByText("TSLA 事件波动与利润率分歧扩大")).toBeTruthy();
  expect(view.queryByText("PLTR 进入高估值与超买观察区")).toBeNull();

  await fireEvent.press(view.getByRole("button", { name: "查看 TSLA 提醒依据" }));
  expect(view.getByText("TSLA 提醒证据")).toBeTruthy();
  expect(view.getByText("失效条件")).toBeTruthy();
  expect(view.getByText("放量站稳 334.00 且利润率预期上修")).toBeTruthy();
  expect(view.getByText("演示：TSLA 事件与成交结构快照")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "关闭TSLA 提醒证据" }));

  await fireEvent.press(view.getByRole("button", { name: "打开 TSLA 个股分析" }));
  expect(mockPush).toHaveBeenLastCalledWith({
    pathname: "/stocks/[symbol]",
    params: { symbol: "TSLA" },
  });
});
