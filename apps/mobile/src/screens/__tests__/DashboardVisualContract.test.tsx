import { beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import {
  createMarketRepository,
  MarketDataError,
} from "@/data/marketRepository";
import { fixtureRepository } from "@/fixtures/repository";
import { AppStateProvider } from "@/state/AppStateProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";

import { DashboardScreen } from "../DashboardScreen";

const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const demoRepository = createMarketRepository({
  loadSnapshot: async () => {
    throw new MarketDataError("configuration", "dashboard visual test");
  },
  loadWatchlist: async () => {
    throw new MarketDataError("configuration", "dashboard visual test");
  },
});

beforeEach(async () => {
  await AsyncStorage.clear();
  mockPush.mockClear();
});

it("renders the approved compact hierarchy and hides research detail by default", async () => {
  const view = await render(
    <AppStateProvider>
      <MarketDataProvider
        demoWatchlist={fixtureRepository.getDashboard("short").watchlist}
        development
        initialDemoMode
        repository={demoRepository}>
        <DashboardScreen />
      </MarketDataProvider>
    </AppStateProvider>,
  );

  await waitFor(() => expect(view.getByTestId("market-regime-hero")).toBeTruthy());

  expect(view.getByTestId("dashboard-header")).toBeTruthy();
  expect(view.getByTestId("priority-alert-card")).toBeTruthy();
  expect(view.getByTestId("watchlist-grid")).toBeTruthy();
  expect(view.getByTestId("candidate-list")).toBeTruthy();
  expect(view.getAllByText("演示数据 · 非实时行情")).toHaveLength(1);

  expect(view.queryByText("为什么")).toBeNull();
  expect(view.queryByText("最强反证")).toBeNull();
  expect(view.queryByText("固定刻度 −100 至 +100")).toBeNull();
  expect(view.queryByText("宏观、信用、能源与商品")).toBeNull();
  expect(view.queryByText("流动性与相关性压力")).toBeNull();

  await fireEvent.press(view.getByRole("button", { name: "查看完整依据" }));
  expect(view.getByText("市场完整依据")).toBeTruthy();
  expect(view.getByText("最强反证")).toBeTruthy();
  expect(view.getByText("失效条件")).toBeTruthy();
  expect(view.getByText("宏观、信用、能源与商品")).toBeTruthy();
});

it("keeps alert, watchlist, and candidates actionable without expanding memos", async () => {
  const view = await render(
    <AppStateProvider>
      <MarketDataProvider
        demoWatchlist={fixtureRepository.getDashboard("short").watchlist}
        development
        initialDemoMode
        repository={demoRepository}>
        <DashboardScreen />
      </MarketDataProvider>
    </AppStateProvider>,
  );

  await waitFor(() => expect(view.getByText("接近量价确认区")).toBeTruthy());
  expect(view.queryByText("NVDA 接近量价确认区")).toBeNull();

  expect(view.queryByText("催化、量价和短线市场环境同向。")).toBeNull();
  expect(view.queryByText("估值拥挤，若成交量未确认则动量可能快速反转。")).toBeNull();

  await fireEvent.press(view.getByRole("button", { name: /查看 TSLA 行情详情/ }));
  expect(mockPush).toHaveBeenLastCalledWith({
    pathname: "/stocks/[symbol]",
    params: { symbol: "TSLA" },
  });

  await fireEvent.press(view.getByRole("button", { name: /查看 NVDA 候选依据/ }));
  expect(view.getByText("NVDA 候选依据")).toBeTruthy();
  expect(view.getByText("最强反例")).toBeTruthy();
  expect(view.getByText("收盘跌破 136.40 且大盘趋势同步转弱。")).toBeTruthy();
});
