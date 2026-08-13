import { beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  act,
  fireEvent,
  render,
  userEvent,
  waitFor,
} from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import {
  AnalysisRequestError,
  decodeDecisionEnvelope,
  type AnalysisSource,
} from "@/data/analysisGateway";
import {
  decodeStockSnapshotEnvelope,
} from "@/data/marketGateway";
import {
  createMarketRepository,
  MarketDataError,
  type MarketDataSource,
  type MarketRepository,
} from "@/data/marketRepository";
import type { Decision, LiveStockSnapshot } from "@/domain/models";
import { AppStateProvider } from "@/state/AppStateProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";

import { decisionFixture } from "../../data/__tests__/decision.fixture";
import { stockSnapshotFixture } from "../../data/__tests__/stockSnapshot.fixture";
import { StockDetailScreen } from "../StockDetailScreen";

const mockBack = jest.fn();
const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ symbol: "NVDA" }),
  useRouter: () => ({ back: mockBack, push: mockPush }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  mockBack.mockClear();
  mockPush.mockClear();
});

function liveSnapshot() {
  return decodeStockSnapshotEnvelope(stockSnapshotFixture(), {
    now: new Date("2026-07-25T16:00:00.000Z"),
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function unavailableMagicSnapshot() {
  const payload = stockSnapshotFixture();
  Object.assign(payload.indicators.magicNine as {
    direction: string | null;
    count: number;
    completed: boolean;
    confirmedAtIndex: number | null;
    qualityStatus: string;
  }, {
    direction: null,
    count: 0,
    completed: false,
    confirmedAtIndex: null,
    qualityStatus: "unavailable",
  });
  return decodeStockSnapshotEnvelope(payload, {
    now: new Date("2026-07-25T16:00:00.000Z"),
  });
}

function liveDecision(
  mutate: (value: ReturnType<typeof decisionFixture>) => void = () => {},
) {
  const value = decisionFixture();
  mutate(value);
  return decodeDecisionEnvelope(value, {
    now: new Date("2026-07-25T16:00:10.000Z"),
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

function analysisWith(getDecision: AnalysisSource["getDecision"]): AnalysisSource {
  return { getDecision };
}

async function renderDetail({
  repository = repositoryWithSnapshot(async () => liveSnapshot()),
  analysis = analysisWith(async () => liveDecision()),
  demoMode = false,
}: {
  repository?: MarketRepository;
  analysis?: AnalysisSource;
  demoMode?: boolean;
} = {}) {
  return render(
    <AppStateProvider>
      <MarketDataProvider
        analysis={analysis}
        development
        initialDemoMode={demoMode}
        repository={repository}
        retryDelaysMs={[]}>
        <StockDetailScreen />
      </MarketDataProvider>
    </AppStateProvider>,
  );
}

it("renders one schema-v2 live snapshot without fixture analysis", async () => {
  const queries: { symbol: string; interval: string; count: number }[] = [];
  const repository = repositoryWithSnapshot(async (query) => {
    queries.push(query);
    return liveSnapshot();
  });
  const view = await renderDetail({ repository });

  await waitFor(() => expect(view.getByText("$142.25")).toBeTruthy());

  expect(queries).toEqual([{ symbol: "NVDA", interval: "5m", count: 200 }]);
  expect(view.getAllByText("NVDA")).toHaveLength(1);
  expect(view.getByText("实时只读")).toBeTruthy();
  expect(view.getByText("+2.40%")).toBeTruthy();
  expect(view.getByText("截止 2026-07-25 15:59:48 UTC")).toBeTruthy();

  expect(view.getByRole("button", { name: /NVDA 图表摘要，2 根已完成 K 线/ })).toBeTruthy();
  expect(view.getByText("MA5 140.80")).toBeTruthy();
  expect(view.getAllByText("RSI 56.2")).toHaveLength(2);
  expect(view.getByText("中性")).toBeTruthy();
  expect(view.getByText("DIF 0.45 · DEA 0.30 · 柱 0.15")).toBeTruthy();
  expect(view.getByText("多头")).toBeTruthy();
  expect(view.getByText("九转 2 · 尚未完成")).toBeTruthy();
  expect(view.queryByText(/最近完成/)).toBeNull();

  expect(
    view.getByText("订单规模活动占比 · 深色主力代理 / 浅色散户代理"),
  ).toBeTruthy();
  expect(
    view.getAllByTestId("participation-available", {
      includeHiddenElements: true,
    }),
  ).toHaveLength(1);
  expect(
    view.getAllByTestId("participation-missing", {
      includeHiddenElements: true,
    }),
  ).toHaveLength(1);
  expect(view.getByText("主力代理 60.0% · 散户代理 40.0%")).toBeTruthy();
  expect(view.getByText(/1 根缺失 · capital flow unavailable/)).toBeTruthy();
  expect(view.getByText("机构持仓披露 · 延迟数据")).toBeTruthy();
  expect(view.getByText("2026-Q1 · 12.50% · 100 家机构")).toBeTruthy();
  expect(view.getByText(/报告期 2026-03-31 00:00:00 UTC/)).toBeTruthy();

  expect(view.getByText(/未接入基本面数据源/)).toBeTruthy();
  expect(view.getByText(/未接入宏观与地缘数据源/)).toBeTruthy();
  expect(view.queryByText("预测分析")).toBeNull();
  const adviser = view.getByRole("button", { name: "顾问分析等待大模型凭据" });
  expect(adviser.props.accessibilityState).toEqual({ disabled: true });
  expect(view.getByText("仅分析与建议 · 不连接券商 · 不会自动下单")).toBeTruthy();

  expect(view.queryByText(/DEMO/i)).toBeNull();
  expect(view.queryByText("演示数据 · 非实时行情")).toBeNull();
  expect(view.queryByText("谨慎偏多；等待量价确认，不追高。")).toBeNull();
  expect(view.queryByText("概率预测，不是未来价格承诺")).toBeNull();
  expect(view.queryByText("预测区间")).toBeNull();
  expect(view.queryByText("NVIDIA")).toBeNull();
});

it("hides and restores every participation chart surface with one tool", async () => {
  const view = await renderDetail();
  await waitFor(() =>
    expect(
      view.getByText(
        "订单规模活动占比 · 深色主力代理 / 浅色散户代理",
      ),
    ).toBeTruthy(),
  );
  const user = userEvent.setup();

  await user.press(
    view.getByRole("button", { name: "参与结构，已显示" }),
  );
  expect(
    view.queryByText(
      "订单规模活动占比 · 深色主力代理 / 浅色散户代理",
    ),
  ).toBeNull();
  expect(
    view.queryByTestId("participation-available", {
      includeHiddenElements: true,
    }),
  ).toBeNull();
  expect(
    view.queryByTestId("participation-missing", {
      includeHiddenElements: true,
    }),
  ).toBeNull();
  expect(view.queryByTestId("participation-summary")).toBeNull();

  await user.press(
    view.getByRole("button", { name: "参与结构，已隐藏" }),
  );
  expect(
    view.getByText(
      "订单规模活动占比 · 深色主力代理 / 浅色散户代理",
    ),
  ).toBeTruthy();
  expect(
    view.getAllByTestId("participation-available", {
      includeHiddenElements: true,
    }),
  ).toHaveLength(1);
  expect(view.getByTestId("participation-summary")).toBeTruthy();
});

it("shows unavailable Magic Nine honestly without a zero marker or sequence", async () => {
  const view = await renderDetail({
    repository: repositoryWithSnapshot(async () =>
      unavailableMagicSnapshot(),
    ),
  });

  await waitFor(() =>
    expect(view.getByText("九转 暂不可用")).toBeTruthy(),
  );
  expect(view.getByTestId("stock-summary-meta")).toHaveTextContent(
    /九转 暂不可用/,
  );
  expect(view.queryByText("九转 0 · 尚未完成")).toBeNull();
  expect(
    view.queryByTestId("magic-nine-marker", {
      includeHiddenElements: true,
    }),
  ).toBeNull();
});

it("keeps a finished nine visible even when the current count is unavailable", async () => {
  const payload = stockSnapshotFixture();
  Object.assign(payload.indicators.magicNine, {
    direction: null,
    count: 0,
    completed: false,
    perfected: null,
    qualityStatus: "unavailable",
    lastCompleted: {
      direction: "bearish",
      confirmedAtIndex: 0,
      perfected: true,
      barsSince: 1,
    },
  });
  const snapshot = decodeStockSnapshotEnvelope(payload, {
    now: new Date("2026-07-25T16:00:00.000Z"),
  });

  const view = await renderDetail({
    repository: repositoryWithSnapshot(async () => snapshot),
  });

  // Discarding the finished run here would defeat the field's whole purpose:
  // it exists precisely because the current count stops describing it.
  await waitFor(() =>
    expect(view.getByTestId("stock-summary-meta")).toHaveTextContent(
      /九转 暂不可用 · 最近完成 看跌九转 · 完美 · 1 根前/,
    ),
  );
});

it("tells the user to update the gateway when its contract is outdated", async () => {
  const view = await renderDetail({
    repository: repositoryWithSnapshot(async () => {
      throw new MarketDataError("contract", "snapshot is missing receivedAt");
    }),
  });

  await waitFor(() =>
    expect(view.getByText("行情不可用 · 网关版本过旧")).toBeTruthy(),
  );
  expect(view.getByText(/请更新本机网关服务后重试/)).toBeTruthy();
});

it("shows realized volatility and says when it cannot be measured", async () => {
  const view = await renderDetail({
    repository: repositoryWithSnapshot(async () => liveSnapshot()),
  });

  await waitFor(() => expect(view.getByText("年化波动 42.0%")).toBeTruthy());

  const quiet = stockSnapshotFixture();
  quiet.indicators.volatility.value = null;
  quiet.indicators.volatility.qualityStatus = "unavailable";
  quiet.indicators.volatility.missingReason = "insufficient sample: 3 of 20 returns";
  const quietView = await renderDetail({
    repository: repositoryWithSnapshot(async () =>
      decodeStockSnapshotEnvelope(quiet, {
        now: new Date("2026-07-25T16:00:00.000Z"),
      }),
    ),
  });

  await waitFor(() =>
    expect(quietView.getByText("年化波动 暂不可用")).toBeTruthy(),
  );
});

it("shows the snapshot warnings instead of decoding them into nothing", async () => {
  const payload = stockSnapshotFixture();
  payload.warnings = [
    "价格为前复权：除权除息会回溯改写这条历史序列，回测请以复权基准对齐。",
    "Capital-flow participation is partially unavailable.",
  ];
  const snapshot = decodeStockSnapshotEnvelope(payload, {
    now: new Date("2026-07-25T16:00:00.000Z"),
  });

  const view = await renderDetail({
    repository: repositoryWithSnapshot(async () => snapshot),
  });

  await waitFor(() =>
    expect(view.getByTestId("snapshot-warnings")).toHaveTextContent(/前复权/),
  );
  expect(view.getByTestId("snapshot-warnings")).toHaveTextContent(
    /Capital-flow participation is partially unavailable/,
  );
});

it("keeps a finished nine visible after the count restarts", async () => {
  const payload = stockSnapshotFixture();
  payload.indicators.magicNine.lastCompleted = {
    direction: "bearish",
    confirmedAtIndex: 0,
    perfected: true,
    barsSince: 1,
  };
  const snapshot = decodeStockSnapshotEnvelope(payload, {
    now: new Date("2026-07-25T16:00:00.000Z"),
  });

  const view = await renderDetail({
    repository: repositoryWithSnapshot(async () => snapshot),
  });

  await waitFor(() =>
    expect(view.getByTestId("stock-summary-meta")).toHaveTextContent(
      /九转 2 · 尚未完成 · 最近完成 看跌九转 · 完美 · 1 根前/,
    ),
  );
});

it("preserves the original timestamp when cached live data becomes stale", async () => {
  const cached = liveSnapshot();
  const repository: MarketRepository = {
    peekStockSnapshot: () => cached,
    getStockSnapshot: async () => {
      throw new MarketDataError("offline", "gateway offline");
    },
    peekWatchlist: () => null,
    getWatchlist: async () => {
      throw new MarketDataError("offline", "gateway offline");
    },
  };
  const view = await renderDetail({ repository });

  await waitFor(() =>
    expect(
      view.getByText("行情已延迟 · 原始时间 2026-07-25 15:59:50 UTC"),
    ).toBeTruthy(),
  );
  expect(view.getByText("$142.25")).toBeTruthy();
  expect(view.getByText("缓存数据")).toBeTruthy();
  expect(view.getByText("5m · STALE")).toBeTruthy();
  expect(view.getByText("缓存事实摘要")).toBeTruthy();
  expect(view.queryByText("实时只读")).toBeNull();
  expect(view.queryByText("实时事实摘要")).toBeNull();
  expect(view.queryByText("5m · LIVE")).toBeNull();
  expect(view.queryByText("演示数据 · 非实时行情")).toBeNull();
  expect(view.getByRole("button", { name: "刷新行情" })).toBeTruthy();
});

it("keeps stale labels and timestamp while a refresh is pending", async () => {
  const cached = liveSnapshot();
  const pendingRefresh = deferred<LiveStockSnapshot>();
  let attempts = 0;
  const repository: MarketRepository = {
    peekStockSnapshot: () => cached,
    getStockSnapshot: async () => {
      attempts += 1;
      if (attempts === 1) {
        throw new MarketDataError("offline", "gateway offline");
      }
      return pendingRefresh.promise;
    },
    peekWatchlist: () => null,
    getWatchlist: async () => {
      throw new MarketDataError("offline", "gateway offline");
    },
  };
  const view = await renderDetail({ repository });

  await waitFor(() =>
    expect(view.getByRole("button", { name: "刷新行情" })).toBeTruthy(),
  );
  fireEvent.press(view.getByRole("button", { name: "刷新行情" }));
  await waitFor(() => expect(attempts).toBe(2));

  expect(
    view.getByText("行情已延迟 · 原始时间 2026-07-25 15:59:50 UTC"),
  ).toBeTruthy();
  expect(view.getByText("缓存数据")).toBeTruthy();
  expect(view.getByText("5m · STALE")).toBeTruthy();
  expect(view.queryByText("实时只读")).toBeNull();
  expect(view.queryByText("5m · LIVE")).toBeNull();
  const refreshing = view.getByRole("button", { name: "正在刷新行情" });
  expect(refreshing.props.accessibilityState).toEqual({ disabled: true });

  fireEvent.press(refreshing);
  expect(attempts).toBe(2);

  await act(async () => {
    pendingRefresh.resolve(cached);
    await pendingRefresh.promise;
  });
  await waitFor(() => expect(view.getByText("实时只读")).toBeTruthy());
  expect(view.getByText("5m · LIVE")).toBeTruthy();
  expect(view.queryByText(/行情已延迟/)).toBeNull();
});

it("offers actionable loading and unavailable states without rendering fixture data", async () => {
  const pending = new Promise<LiveStockSnapshot>(() => undefined);
  const loadingView = await renderDetail({
    repository: repositoryWithSnapshot(async () => pending),
  });

  expect(loadingView.getByText("正在连接 moomoo 行情…")).toBeTruthy();
  const loadingBack = loadingView.getByRole("button", { name: "返回自选列表" });
  expect(StyleSheet.flatten(loadingBack.props.style).minHeight).toBeGreaterThanOrEqual(44);
  expect(loadingView.queryByText("演示数据 · 非实时行情")).toBeNull();
  await loadingView.unmount();

  const unavailableView = await renderDetail({
    repository: repositoryWithSnapshot(async () => {
      throw new MarketDataError("configuration", "market URL missing");
    }),
  });
  await waitFor(() =>
    expect(unavailableView.getByText("行情不可用 · configuration")).toBeTruthy(),
  );
  const retry = unavailableView.getByRole("button", { name: "重试行情" });
  expect(StyleSheet.flatten(retry.props.style).minHeight).toBeGreaterThanOrEqual(44);
  expect(unavailableView.queryByText("$142.25")).toBeNull();
  expect(unavailableView.queryByText("演示数据 · 非实时行情")).toBeNull();
  expect(unavailableView.toJSON()).toBeTruthy();
});

it("retries an unavailable snapshot once, shows loading, and recovers live", async () => {
  let attempts = 0;
  let resolveRetry!: (snapshot: LiveStockSnapshot) => void;
  const retryResult = new Promise<LiveStockSnapshot>((resolve) => {
    resolveRetry = resolve;
  });
  const repository = repositoryWithSnapshot(async () => {
    attempts += 1;
    if (attempts === 1) {
      throw new MarketDataError("configuration", "market URL missing");
    }
    return retryResult;
  });
  const view = await renderDetail({ repository });

  await waitFor(() =>
    expect(view.getByText("行情不可用 · configuration")).toBeTruthy(),
  );
  fireEvent.press(view.getByRole("button", { name: "重试行情" }));
  await waitFor(() => expect(attempts).toBe(2));
  expect(view.getByText("正在连接 moomoo 行情…")).toBeTruthy();
  expect(view.queryByRole("button", { name: "重试行情" })).toBeNull();

  resolveRetry(liveSnapshot());
  await waitFor(() => expect(view.getByText("$142.25")).toBeTruthy());
  expect(view.getByText("实时只读")).toBeTruthy();
});

it("uses the fixture only when runtime explicitly selects demo mode", async () => {
  const view = await renderDetail({ demoMode: true });

  await waitFor(() =>
    expect(view.getByText("演示数据 · 非实时行情")).toBeTruthy(),
  );
  expect(view.getByText("$143.80")).toBeTruthy();
  expect(view.getByText(/demo-short · DEMO/i)).toBeTruthy();
  expect(view.queryByText("实时只读")).toBeNull();
});

it("shows the real decision with the share of the picture it had", async () => {
  const requests: { symbol: string; horizon: string }[] = [];
  const view = await renderDetail({
    analysis: analysisWith(async (symbol, horizon) => {
      requests.push({ symbol, horizon });
      return liveDecision();
    }),
  });

  await waitFor(() => expect(view.getByTestId("decision-card")).toBeTruthy());

  expect(requests).toEqual([{ symbol: "NVDA", horizon: "short" }]);
  expect(view.getByTestId("decision-score")).toHaveTextContent(/72.5/);
  // A score shown without its coverage reads as a complete verdict.
  expect(view.getByTestId("decision-coverage")).toHaveTextContent(
    /因子覆盖 70%/,
  );
  expect(view.getByTestId("decision-missing-factors")).toHaveTextContent(
    /macro/,
  );
  expect(view.queryByText("预测分析")).toBeNull();
  expect(view.queryByTestId("decision-state")).toBeNull();
});

it("lets an unavailable decision speak for itself without a second placeholder", async () => {
  const view = await renderDetail({
    analysis: analysisWith(async () =>
      liveDecision((value) => {
        value.status = "unavailable";
        value.score = null;
        value.forecast = null;
        value.riskPlan = null;
        value.notes = ["No completed candles were available."];
      }),
    ),
  });

  await waitFor(() => expect(view.getByTestId("decision-card")).toBeTruthy());

  expect(view.getByText("暂不可用")).toBeTruthy();
  expect(view.getByTestId("decision-card")).toHaveTextContent(
    /No completed candles were available/,
  );
  expect(view.queryByTestId("decision-score")).toBeNull();
  expect(view.queryByText("预测分析")).toBeNull();
  expect(view.queryByTestId("decision-state")).toBeNull();
});

it("names why the analysis service could not answer and offers one retry", async () => {
  let attempts = 0;
  const view = await renderDetail({
    analysis: analysisWith(async () => {
      attempts += 1;
      if (attempts === 1) {
        throw new AnalysisRequestError("offline", "analysis service is offline");
      }
      return liveDecision();
    }),
  });

  await waitFor(() =>
    expect(view.getByTestId("decision-state")).toHaveTextContent(
      /分析不可用 · offline/,
    ),
  );
  // Rendering nothing here would read as "this stock has no conclusion", and a
  // placeholder card would claim the service is not connected at all.
  expect(view.queryByTestId("decision-card")).toBeNull();
  expect(view.queryByText("预测分析")).toBeNull();

  await act(async () => {
    fireEvent.press(view.getByRole("button", { name: "重试分析" }));
  });
  await waitFor(() => expect(view.getByTestId("decision-card")).toBeTruthy());
  expect(view.getByTestId("decision-coverage")).toHaveTextContent(
    /因子覆盖 70%/,
  );
});

it("never asks the analysis service for a decision about demo data", async () => {
  const getDecision = jest.fn<AnalysisSource["getDecision"]>(async () =>
    liveDecision(),
  );
  const view = await renderDetail({
    analysis: analysisWith(getDecision),
    demoMode: true,
  });

  await waitFor(() =>
    expect(view.getByText("演示数据 · 非实时行情")).toBeTruthy(),
  );
  expect(getDecision).not.toHaveBeenCalled();
  expect(view.queryByTestId("decision-card")).toBeNull();
  expect(view.queryByTestId("decision-state")).toBeNull();
});

it("cancels an in-flight decision request when the page leaves", async () => {
  const signals: (AbortSignal | undefined)[] = [];
  const view = await renderDetail({
    analysis: analysisWith(
      (_symbol, _horizon, signal) =>
        new Promise<Decision>((_resolve, reject) => {
          signals.push(signal);
          signal?.addEventListener(
            "abort",
            () =>
              reject(
                Object.assign(new Error("page left"), { name: "AbortError" }),
              ),
            { once: true },
          );
        }),
    ),
  });

  await waitFor(() => expect(signals).toHaveLength(1));
  await view.unmount();

  expect(signals[0]?.aborted).toBe(true);
});

it("reaches the news surface from the stock page and shows the cited reports", async () => {
  const view = await renderDetail();

  await waitFor(() => expect(view.getByTestId("decision-news")).toBeTruthy());

  expect(view.getByText("新闻与解读 · NVDA")).toBeTruthy();
  expect(
    view.getByText("NVIDIA raises full-year revenue guidance"),
  ).toBeTruthy();
  expect(view.getByRole("link", { name: "打开来源：Reuters" })).toBeTruthy();
  expect(view.getByTestId("decision-news-marker-c1")).toHaveTextContent("①");
});

it("says the news evidence failed to load rather than showing a quiet market", async () => {
  const view = await renderDetail({
    analysis: analysisWith(async () => {
      throw new AnalysisRequestError("offline", "no route to the service");
    }),
  });

  await waitFor(() =>
    expect(view.getByTestId("decision-news-unavailable")).toBeTruthy(),
  );
  expect(view.queryByTestId("decision-news-empty")).toBeNull();
});

it("keeps the demo stock page free of a news surface it cannot fill", async () => {
  const view = await renderDetail({ demoMode: true });

  await waitFor(() => expect(view.getAllByText("演示数据 · 非实时行情")).toHaveLength(1));
  expect(view.queryByTestId("decision-news")).toBeNull();
});

it("names what each still-dark card is waiting on", async () => {
  const view = await renderDetail();

  await waitFor(() => expect(view.getByTestId("decision-news")).toBeTruthy());

  // "尚未接入真实分析" was wrong on all three: the analysis service answers,
  // and each of these is short a specific input instead.
  expect(view.queryByText("尚未接入真实分析")).toBeNull();
  expect(view.getByText(/未接入基本面数据源/)).toBeTruthy();
  expect(view.getByText(/未接入宏观与地缘数据源/)).toBeTruthy();
  expect(
    view.getByRole("button", { name: /顾问分析/ }),
  ).toHaveTextContent(/ANTHROPIC_API_KEY/);
});

it("keeps the analysis and its news when only the quote feed is down", async () => {
  // Quotes and analysis come from independent services. Returning early on a
  // market failure discards a live analysis, and this screen is the only
  // route to any news at all — so one moomoo hiccup empties the whole app.
  const view = await renderDetail({
    repository: repositoryWithSnapshot(async () => {
      throw new MarketDataError("offline", "gateway offline");
    }),
    analysis: analysisWith(async () => liveDecision()),
  });

  await waitFor(() => expect(view.queryByTestId("decision-card")).not.toBeNull());
  expect(view.queryByTestId("decision-news")).not.toBeNull();
});
