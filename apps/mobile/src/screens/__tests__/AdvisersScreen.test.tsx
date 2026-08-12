import { beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { AppStateProvider } from "@/state/AppStateProvider";

import { AdvisersScreen } from "../AdvisersScreen";
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


jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ symbol: "NVDA" }),
  useRouter: () => ({ back: jest.fn() }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
});

it("keeps the objective layer frozen while selecting deterministic long and short plans", async () => {
  const view = await render(
    <AppStateProvider>
      <MarketDataProvider development initialDemoMode repository={idleRepository}>
      <AdvisersScreen />
    </MarketDataProvider>
    </AppStateProvider>,
  );

  await waitFor(() => expect(view.getByTestId("adviser-council")).toBeTruthy());

  expect(view.getAllByText("演示数据 · 非实时行情")).toHaveLength(1);
  expect(view.getByText("客观算法结论")).toBeTruthy();
  expect(view.getByText("72")).toBeTruthy();
  expect(view.getByText("置信度 68%")).toBeTruthy();
  expect(view.getByText(/公开投资理念的风格模拟/)).toBeTruthy();
  expect(view.getByText("按需调用 · 当前激活 4 / 13 · 节省 Token")).toBeTruthy();

  expect(view.getByRole("button", { name: "做多方案，已选择" })).toBeTruthy();
  expect(view.getByRole("button", { name: "均衡风险偏好，已选择" })).toBeTruthy();
  expect(view.getByTestId("trade-plan-card")).toBeTruthy();
  expect(view.getByText("回踩分批限价")).toBeTruthy();
  expect(view.getByText("$139.80 – $141.20")).toBeTruthy();
  expect(view.getByText("1.25× / 上限 1.50×")).toBeTruthy();

  await fireEvent.press(view.getByRole("button", { name: "查看方案引用" }));
  expect(view.getByText("NVDA 方案证据")).toBeTruthy();
  expect(view.getByText("演示：NVDA 机构持仓与财报快照")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "关闭NVDA 方案证据" }));

  await fireEvent.press(view.getByRole("button", { name: "做空方案" }));
  await fireEvent.press(view.getByRole("button", { name: "进取风险偏好" }));

  expect(view.getByText("突破限价")).toBeTruthy();
  expect(view.getByText("$143.40 – $144.60")).toBeTruthy();
  expect(view.getByText("可借券：是")).toBeTruthy();
  expect(view.getByText("预计借券费 0.35%")).toBeTruthy();
  expect(view.getAllByText(/无限损失风险/).length).toBeGreaterThan(0);

  expect(view.getByText("72")).toBeTruthy();
  expect(view.getByText("置信度 68%")).toBeTruthy();
  expect(view.getByText("仅分析与建议，不连接券商，不会自动下单。")).toBeTruthy();
  expect(view.queryByText(/提交订单|自动交易|一键下单/)).toBeNull();
});
