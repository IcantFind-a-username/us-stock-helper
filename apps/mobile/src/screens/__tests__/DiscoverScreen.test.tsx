import { beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { AppStateProvider } from "@/state/AppStateProvider";

import { DiscoverScreen } from "../DiscoverScreen";
import { MarketDataProvider } from "@/state/MarketDataProvider";
import {
  createMarketRepository,
  MarketDataError,
  type MarketRepository,
} from "@/data/marketRepository";
import type { WatchlistQuote } from "@/domain/models";

// A real repository over sources that refuse: screens now read the watchlist,
// so a bare source object would fail on the methods only a repository has.
const idleRepository: MarketRepository = createMarketRepository({
  loadWatchlist: async () => {
    throw new MarketDataError("configuration", "not used in this test");
  },
  loadSnapshot: async () => {
    throw new MarketDataError("configuration", "not used in this test");
  },
});


const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  mockPush.mockClear();
});

async function renderDiscover() {
  return render(
    <AppStateProvider>
      <MarketDataProvider development initialDemoMode repository={idleRepository}>
      <DiscoverScreen />
    </MarketDataProvider>
    </AppStateProvider>,
  );
}

it("filters horizon candidates and preserves evidence-gated stock navigation", async () => {
  const view = await renderDiscover();

  await waitFor(() => expect(view.getByText("机会发现")).toBeTruthy());
  expect(view.getByText("NVDA · NVIDIA")).toBeTruthy();
  expect(view.getByText("TSLA · Tesla")).toBeTruthy();
  expect(view.getByText("PLTR · Palantir")).toBeTruthy();
  expect(view.getByText(/不对称候选不代表收益承诺/)).toBeTruthy();

  await fireEvent.press(view.getByRole("button", { name: "只看做空" }));
  expect(view.queryByText("NVDA · NVIDIA")).toBeNull();
  expect(view.getByText("TSLA · Tesla")).toBeTruthy();
  expect(view.queryByText("PLTR · Palantir")).toBeNull();

  await fireEvent.press(view.getByRole("button", { name: "全部方向" }));
  await fireEvent.press(view.getByRole("button", { name: "只看非对称上行" }));
  expect(view.getByText("NVDA · NVIDIA")).toBeTruthy();
  expect(view.queryByText("TSLA · Tesla")).toBeNull();

  await fireEvent.press(view.getByRole("button", { name: "查看 NVDA 候选依据" }));
  expect(view.getByText("NVDA 候选证据")).toBeTruthy();
  expect(view.getByText("最强反证")).toBeTruthy();
  expect(view.getByText("失效条件")).toBeTruthy();
  expect(view.getByText("演示：短线 NVDA 量价确认快照")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "关闭NVDA 候选证据" }));

  await fireEvent.press(view.getByRole("button", { name: "打开 NVDA 个股分析" }));
  expect(mockPush).toHaveBeenLastCalledWith({
    pathname: "/stocks/[symbol]",
    params: { symbol: "NVDA" },
  });
});


function quote(symbol: string, changePercent: number): WatchlistQuote {
  return {
    symbol,
    price: 100 + changePercent,
    changePercent,
    direction: changePercent >= 0 ? "bullish" : "bearish",
    summary: `${symbol} 摘要`,
  };
}

function watchlistRepository(quotes: WatchlistQuote[]) {
  return createMarketRepository({
    loadSnapshot: async () => {
      throw new MarketDataError("configuration", "not used in this test");
    },
    loadWatchlist: async () => ({
      source: "moomoo" as const,
      asOf: "2026-08-13T15:59:48.000Z",
      quotes,
    }),
  });
}

async function renderRealDiscover(repository = watchlistRepository([])) {
  return render(
    <AppStateProvider>
      <MarketDataProvider development repository={repository} retryDelaysMs={[]}>
        <DiscoverScreen />
      </MarketDataProvider>
    </AppStateProvider>,
  );
}

it("scans the real watchlist by size of move and opens the stock behind a row", async () => {
  const view = await renderRealDiscover(
    watchlistRepository([
      quote("AAPL", 0.4),
      quote("TSLA", -5.2),
      quote("NVDA", 2.1),
    ]),
  );

  await waitFor(() => expect(view.getByTestId("market-scan")).toBeTruthy());

  const rows = view.getAllByTestId(/^market-scan-row-/);
  expect(rows.map((row) => row.props.testID)).toEqual([
    "market-scan-row-TSLA",
    "market-scan-row-NVDA",
    "market-scan-row-AAPL",
  ]);

  await fireEvent.press(view.getByRole("button", { name: "打开 TSLA 个股分析" }));
  expect(mockPush).toHaveBeenLastCalledWith({
    pathname: "/stocks/[symbol]",
    params: { symbol: "TSLA" },
  });
});

it("keeps the unbuilt candidate ranking honest while showing the real scan", async () => {
  const view = await renderRealDiscover(watchlistRepository([quote("NVDA", 2.1)]));

  await waitFor(() => expect(view.getByTestId("market-scan")).toBeTruthy());

  expect(view.getByTestId("analysis-not-connected")).toHaveTextContent(/全市场/);
  expect(view.queryByText("NVDA · NVIDIA")).toBeNull();
  expect(view.queryByText("演示数据 · 非实时行情")).toBeNull();
});

it("says the quotes are unavailable rather than showing an empty scan", async () => {
  const failing = createMarketRepository({
    loadSnapshot: async () => {
      throw new MarketDataError("configuration", "not used in this test");
    },
    loadWatchlist: async () => {
      throw new MarketDataError("offline", "no route to the gateway");
    },
  });
  const view = await renderRealDiscover(failing);

  await waitFor(() =>
    expect(view.getByTestId("market-scan-unavailable")).toBeTruthy(),
  );
  expect(view.getByText("自选行情不可用 · 连不上")).toBeTruthy();
  expect(view.getByTestId("market-scan-unavailable-body")).toHaveTextContent(
    /OpenD/,
  );
  expect(view.queryByText(/offline/)).toBeNull();
  expect(view.queryByTestId("market-scan-empty")).toBeNull();
});
