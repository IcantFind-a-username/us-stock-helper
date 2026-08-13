import { beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import {
  AnalysisRequestError,
  decodeDecisionEnvelope,
  type AnalysisSource,
} from "@/data/analysisGateway";
import { decisionFixture } from "@/data/__tests__/decision.fixture";
import {
  createMarketRepository,
  MarketDataError,
  type MarketDataSource,
  type MarketRepository,
} from "@/data/marketRepository";
import type { Horizon, WatchlistQuote } from "@/domain/models";
import { AppStateProvider } from "@/state/AppStateProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";

import { DashboardScreen } from "../DashboardScreen";

const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  mockPush.mockClear();
});

const SYMBOLS = Array.from(
  { length: 46 },
  (_, index) => `SYM${String(index).padStart(2, "0")}`,
);

function quotes(symbols: string[] = SYMBOLS): WatchlistQuote[] {
  return symbols.map((symbol, index) => ({
    symbol,
    price: 100 + index,
    changePercent: index % 2 === 0 ? 1.25 : -0.4,
    direction: index % 2 === 0 ? "bullish" : "bearish",
    summary: "实时只读",
  }));
}

function liveDecision(symbol: string, value: number, horizon: Horizon) {
  const payload = decisionFixture();
  payload.symbol = symbol;
  payload.horizon = horizon;
  (payload.score as Record<string, unknown>).value = value;
  return decodeDecisionEnvelope(payload);
}

function repositoryWithWatchlist(
  loadWatchlist: MarketDataSource["loadWatchlist"],
) {
  return createMarketRepository({
    loadSnapshot: async () => {
      throw new MarketDataError("configuration", "snapshot not configured");
    },
    loadWatchlist,
  });
}

const liveWatchlist = (rows: WatchlistQuote[] = quotes()) =>
  repositoryWithWatchlist(async () => ({
    source: "moomoo",
    asOf: "2026-07-25T15:59:50.000Z",
    quotes: rows,
  }));

function renderDashboard({
  repository,
  analysis = { getDecision: async (symbol, horizon) => liveDecision(symbol, 72.5, horizon) },
  demoMode = false,
  decisionConcurrency = 8,
}: {
  repository: MarketRepository;
  analysis?: AnalysisSource;
  demoMode?: boolean;
  decisionConcurrency?: number;
}) {
  return render(
    <AppStateProvider>
      <MarketDataProvider
        analysis={analysis}
        decisionConcurrency={decisionConcurrency}
        demoWatchlist={quotes(SYMBOLS.slice(0, 3))}
        development
        initialDemoMode={demoMode}
        repository={repository}
        retryDelaysMs={[]}>
        <DashboardScreen />
      </MarketDataProvider>
    </AppStateProvider>,
  );
}

it("makes all 46 watchlist symbols reachable and says how many are hidden", async () => {
  const view = await renderDashboard({ repository: liveWatchlist() });

  await waitFor(() => expect(view.getByText("实时行情")).toBeTruthy());
  expect(view.getByTestId("watchlist-count").props.children).toBe(
    "共 46 只 · 已显示 8 只",
  );

  await fireEvent.press(view.getByRole("button", { name: "查看全部 46 只自选" }));

  const rows = view.getAllByTestId("watchlist-quote");
  expect(rows).toHaveLength(46);
  expect(view.getByTestId("watchlist-count").props.children).toBe(
    "共 46 只 · 已全部显示",
  );

  for (const row of rows) {
    await fireEvent.press(row);
  }
  expect(mockPush.mock.calls.map(([call]) => call)).toEqual(
    SYMBOLS.map((symbol) => ({
      pathname: "/stocks/[symbol]",
      params: { symbol },
    })),
  );
});

it("puts the real per-symbol score on the dashboard and only asks for what it shows", async () => {
  const asked: string[] = [];
  const analysis: AnalysisSource = {
    getDecision: async (symbol, horizon) => {
      asked.push(symbol);
      if (symbol === "SYM01") {
        throw new AnalysisRequestError("timeout", "analysis request timed out");
      }
      return liveDecision(symbol, 72.5, horizon);
    },
  };
  const view = await renderDashboard({ analysis, repository: liveWatchlist() });

  await waitFor(() =>
    expect(view.getByTestId("watchlist-score-SYM00").props.children).toBe("73"),
  );
  expect(view.getAllByText("偏多 · 覆盖 70%").length).toBeGreaterThan(0);
  await waitFor(() =>
    expect(view.getByTestId("watchlist-score-SYM01").props.children).toBe("—"),
  );
  expect(view.getByText("不可用 · 超时")).toBeTruthy();
  expect(asked).toEqual(SYMBOLS.slice(0, 8));

  await fireEvent.press(view.getByRole("button", { name: "查看全部 46 只自选" }));
  await waitFor(() => expect(asked).toHaveLength(46));
  expect(asked).toEqual(SYMBOLS);
  await waitFor(() =>
    expect(view.getByTestId("watchlist-score-SYM45").props.children).toBe("73"),
  );
});

it("distinguishes connecting, an empty watchlist, and an unreachable gateway", async () => {
  const connecting = await renderDashboard({
    repository: repositoryWithWatchlist(
      () => new Promise(() => undefined),
    ),
  });
  expect(connecting.getByText("正在连接 moomoo 行情…")).toBeTruthy();
  expect(connecting.queryByTestId("watchlist-quote")).toBeNull();
  expect(connecting.queryByText("moomoo 自选为空")).toBeNull();
  expect(connecting.queryByText(/行情不可用/)).toBeNull();
  await connecting.unmount();

  const empty = await renderDashboard({ repository: liveWatchlist([]) });
  await waitFor(() => expect(empty.getByText("moomoo 自选为空")).toBeTruthy());
  expect(
    empty.getByText("moomoo 账户里没有自选标的。在 moomoo 中添加后刷新。"),
  ).toBeTruthy();
  expect(empty.getByRole("button", { name: "刷新行情" })).toBeTruthy();
  expect(empty.queryByText("正在连接 moomoo 行情…")).toBeNull();
  expect(empty.queryByText(/行情不可用/)).toBeNull();
  expect(empty.queryByTestId("watchlist-quote")).toBeNull();
  await empty.unmount();

  const unreachable = await renderDashboard({
    repository: repositoryWithWatchlist(async () => {
      throw new MarketDataError("offline", "OpenD offline");
    }),
  });
  await waitFor(() =>
    expect(unreachable.getByText("行情不可用 · 连不上")).toBeTruthy(),
  );
  expect(unreachable.getByRole("button", { name: "重试行情" })).toBeTruthy();
  expect(unreachable.queryByText("moomoo 自选为空")).toBeNull();
  expect(unreachable.queryByText("正在连接 moomoo 行情…")).toBeNull();
});

it("never scores demo rows with a real verdict", async () => {
  const getDecision = jest.fn<AnalysisSource["getDecision"]>(
    async (symbol, horizon) => liveDecision(symbol, 72.5, horizon),
  );
  const view = await renderDashboard({
    analysis: { getDecision },
    demoMode: true,
    repository: liveWatchlist(),
  });

  await waitFor(() => expect(view.getByText("演示数据 · 非实时")).toBeTruthy());
  expect(view.getAllByTestId("watchlist-quote")).toHaveLength(3);
  expect(view.getByTestId("watchlist-score-SYM00").props.children).toBe("—");
  expect(view.getAllByText("演示无评分")).toHaveLength(3);
  expect(getDecision).not.toHaveBeenCalled();
});

it("names a declined analysis in the row without printing the wire code", async () => {
  // LULU, ETSY and GPCR fail exactly this way on the real watchlist: the
  // service answers, and what it answers is that it could not evaluate.
  const analysis: AnalysisSource = {
    getDecision: async (symbol, horizon) => {
      if (symbol === "SYM01") {
        throw new AnalysisRequestError(
          "analysis-failed",
          "The decision chain could not be evaluated",
        );
      }
      return liveDecision(symbol, 72.5, horizon);
    },
  };
  const view = await renderDashboard({ analysis, repository: liveWatchlist() });

  await waitFor(() =>
    expect(view.getByTestId("watchlist-score-SYM01").props.children).toBe("—"),
  );
  expect(view.getByText("不可用 · 分析失败")).toBeTruthy();
  expect(view.queryByText(/analysis-failed/)).toBeNull();
  expect(view.queryByText(/malformed/)).toBeNull();
  // A screen reader gets the sentence, not the four-character column label.
  expect(
    view.getByLabelText(/评分不可用 · 分析服务没能算出结论/),
  ).toBeTruthy();
});

it("explains a point-in-time rejection of the whole watchlist in Chinese", async () => {
  const view = await renderDashboard({
    repository: repositoryWithWatchlist(async () => {
      throw new MarketDataError(
        "malformed",
        "MALFORMED_PROVIDER_DATA: Market data failed point-in-time validation",
      );
    }),
  });

  await waitFor(() =>
    expect(view.getByText("行情不可用 · 数据被拒")).toBeTruthy(),
  );
  const body = view.getByTestId("watchlist-unavailable-body");
  expect(body).toHaveTextContent(/不准确/);
  expect(body).toHaveTextContent(/不是你的操作问题/);
  expect(view.queryByText(/malformed/i)).toBeNull();
  expect(view.getByRole("button", { name: "重试行情" })).toBeTruthy();
});

it("keeps a rejected payload apart from an undecodable one on the same row", async () => {
  const analysis: AnalysisSource = {
    getDecision: async (symbol, horizon) => {
      if (symbol === "SYM00") {
        throw new AnalysisRequestError("analysis-failed", "chain failed");
      }
      if (symbol === "SYM01") {
        throw new AnalysisRequestError("validation", "unreadable body");
      }
      return liveDecision(symbol, 72.5, horizon);
    },
  };
  const view = await renderDashboard({ analysis, repository: liveWatchlist() });

  await waitFor(() =>
    expect(view.getByText("不可用 · 分析失败")).toBeTruthy(),
  );
  expect(view.getByText("不可用 · 响应异常")).toBeTruthy();
});
