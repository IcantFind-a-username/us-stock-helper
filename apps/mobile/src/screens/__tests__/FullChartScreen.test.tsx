import { beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { render, userEvent, waitFor } from "@testing-library/react-native";

import { decodeStockSnapshotEnvelope } from "@/data/marketGateway";
import {
  createMarketRepository,
  MarketDataError,
  type MarketDataSource,
  type MarketRepository,
} from "@/data/marketRepository";
import { AppStateProvider } from "@/state/AppStateProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";

import { stockSnapshotFixture } from "../../data/__tests__/stockSnapshot.fixture";
import { FullChartScreen } from "../FullChartScreen";

const mockBack = jest.fn();

jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ symbol: "NVDA" }),
  useRouter: () => ({ back: mockBack }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  mockBack.mockClear();
});

function liveSnapshot() {
  return decodeStockSnapshotEnvelope(stockSnapshotFixture(), {
    now: new Date("2026-07-25T16:00:00.000Z"),
  });
}

function repositoryWithSnapshot(
  loadSnapshot: MarketDataSource["loadSnapshot"],
) {
  return createMarketRepository({
    loadSnapshot,
    loadWatchlist: async () => ({
      source: "moomoo",
      asOf: "2026-07-25T15:59:48.000Z",
      quotes: [],
    }),
  });
}

async function renderChart({
  repository = repositoryWithSnapshot(async () => liveSnapshot()),
  demoMode = false,
}: {
  repository?: MarketRepository;
  demoMode?: boolean;
} = {}) {
  return render(
    <AppStateProvider>
      <MarketDataProvider
        development
        initialDemoMode={demoMode}
        repository={repository}
        retryDelaysMs={[]}>
        <FullChartScreen />
      </MarketDataProvider>
    </AppStateProvider>,
  );
}

it("renders the same live snapshot with selectable candles and both indicators", async () => {
  const view = await renderChart();

  await waitFor(() => expect(view.getByText("NVDA 专业图表")).toBeTruthy());
  expect(view.getByText("实时只读 · 截止 2026-07-25 15:59:50 UTC")).toBeTruthy();
  expect(view.getByText("价格 · 成交量")).toBeTruthy();
  expect(view.getByText("RSI 56.2")).toBeTruthy();
  expect(view.getByText("DIF 0.45 · DEA 0.30 · 柱 0.15")).toBeTruthy();
  expect(view.getByText("MA5 140.80")).toBeTruthy();
  expect(view.getByText("机构持仓披露 · 延迟数据")).toBeTruthy();
  expect(view.queryByText("演示数据 · 非实时行情")).toBeNull();
  expect(view.queryByText(/DEMO/i)).toBeNull();
  expect(view.queryByText("上涨概率")).toBeNull();

  const user = userEvent.setup();
  await user.press(
    view.getByRole("button", { name: /NVDA 图表摘要，2 根已完成 K 线/ }),
  );
  expect(view.getByLabelText(/NVDA 收盘时间 2026-07-25T15:50:00.000Z/)).toBeTruthy();
});

it("keeps stale data visible and unavailable data actionable without demo fallback", async () => {
  const cached = liveSnapshot();
  const staleRepository: MarketRepository = {
    peekStockSnapshot: () => cached,
    getStockSnapshot: async () => {
      throw new MarketDataError("offline", "gateway offline");
    },
    peekWatchlist: () => null,
    getWatchlist: async () => {
      throw new MarketDataError("offline", "gateway offline");
    },
  };
  const staleView = await renderChart({ repository: staleRepository });
  await waitFor(() =>
    expect(
      staleView.getByText("行情已延迟 · 原始时间 2026-07-25 15:59:50 UTC"),
    ).toBeTruthy(),
  );
  expect(staleView.getByText("价格 · 成交量")).toBeTruthy();
  expect(staleView.queryByText("演示数据 · 非实时行情")).toBeNull();
  await staleView.unmount();

  const unavailableView = await renderChart({
    repository: repositoryWithSnapshot(async () => {
      throw new MarketDataError("permission", "quote permission required");
    }),
  });
  await waitFor(() =>
    expect(unavailableView.getByText("行情不可用 · permission")).toBeTruthy(),
  );
  expect(unavailableView.getByRole("button", { name: "重试行情" })).toBeTruthy();
  expect(unavailableView.queryByText("价格 · 成交量")).toBeNull();
  expect(unavailableView.queryByText("演示数据 · 非实时行情")).toBeNull();
});

it("marks the whole chart as non-live only in explicit demo mode", async () => {
  const view = await renderChart({ demoMode: true });

  await waitFor(() =>
    expect(view.getByText("演示数据 · 非实时行情")).toBeTruthy(),
  );
  expect(view.getByText(/demo-short · DEMO/i)).toBeTruthy();
  expect(view.getByText("价格 · 成交量 · 概率预测")).toBeTruthy();
  expect(view.queryByText("实时只读")).toBeNull();
});
