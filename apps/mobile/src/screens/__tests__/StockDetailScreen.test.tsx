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

import {
  decisionFixture,
  newsInterpretationFixture,
} from "../../data/__tests__/decision.fixture";
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

  expect(queries).toEqual([{ symbol: "NVDA", interval: "day", count: 250 }]);
  expect(
    view.getByRole("tab", { name: "日K" }).props.accessibilityState,
  ).toEqual({ selected: true });
  expect(view.getAllByText("NVDA")).toHaveLength(1);
  expect(view.getByText("实时只读")).toBeTruthy();
  expect(view.getByText("+2.40%")).toBeTruthy();
  expect(view.getByText("截止 2026-07-25 15:59:48 UTC")).toBeTruthy();

  expect(view.getByRole("button", { name: /NVDA 图表摘要，2 根已完成 K 线/ })).toBeTruthy();
  // The latest values are stated once, in the fact row; the chart carries the
  // series and no longer repeats the numbers in a second card.
  expect(view.getByText("MA5 140.80")).toBeTruthy();
  expect(view.getAllByText("RSI 56.2")).toHaveLength(1);
  expect(view.getByText("MACD 0.15")).toBeTruthy();
  expect(view.queryByText("DIF 0.45 · DEA 0.30 · 柱 0.15")).toBeNull();
  expect(view.getByTestId("macd-panel", { includeHiddenElements: true })).toBeTruthy();
  expect(view.getByText("九转 看涨 2/9")).toBeTruthy();
  expect(view.queryByText(/最近完成/)).toBeNull();

  expect(view.getByText("主力代理")).toBeTruthy();
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
  // A reason this app has no translation for still has to reach the reader.
  expect(view.getByText(/1 根缺失 · 本次快照没有资金流数据/)).toBeTruthy();
  expect(view.getByTestId("institutional-holdings-card")).toBeTruthy();
  expect(view.getByTestId("institutional-holdings-percent")).toHaveTextContent(
    "12.50%",
  );

  expect(view.getByTestId("decision-factor-breakdown")).toHaveTextContent(
    /技术趋势/,
  );
  expect(view.queryByText("预测分析")).toBeNull();
  expect(
    view.getByRole("button", { name: "为 NVDA 生成一次 Claude 新闻解读" }),
  ).toBeTruthy();
  expect(view.getByText("仅供分析与建议 · 不连接券商 · 不会自动下单")).toBeTruthy();

  expect(view.queryByText("演示数据 · 非实时行情")).toBeNull();
  expect(view.queryByText(/短线 · 演示数据/)).toBeNull();
  expect(view.queryByText("谨慎偏多；等待量价确认，不追高。")).toBeNull();
  expect(view.queryByText("概率预测，不是未来价格承诺")).toBeNull();
  expect(view.queryByText("预测区间")).toBeNull();
  expect(view.queryByText("NVIDIA")).toBeNull();
});

it("calls Claude only after a single-stock button press", async () => {
  const calls: Array<{ symbol: string; adviser: string | undefined }> = [];
  const analysis = analysisWith(async (symbol, _horizon, _signal, options) => {
    calls.push({ symbol, adviser: options?.adviser });
    return liveDecision((value) => {
      if (options?.adviser === "news") {
        value.newsInterpretation = newsInterpretationFixture();
        value.adviserUsage = {
          model: "claude-opus-4-8",
          inputTokens: 4000,
          outputTokens: 900,
          cacheCreationInputTokens: 0,
          cacheReadInputTokens: 0,
          costUsd: 0.0425,
        };
      }
    });
  });
  const view = await renderDetail({ analysis });

  await waitFor(() => expect(calls).toEqual([{ symbol: "NVDA", adviser: undefined }]));
  await userEvent.setup().press(
    view.getByRole("button", { name: "为 NVDA 生成一次 Claude 新闻解读" }),
  );

  await waitFor(() =>
    expect(calls).toEqual([
      { symbol: "NVDA", adviser: undefined },
      { symbol: "NVDA", adviser: "news" },
    ]),
  );
  await waitFor(() =>
    expect(view.getByTestId("decision-interpretation-reading")).toBeTruthy(),
  );
  expect(
    view.getByTestId("decision-interpretation-reading").props.children,
  ).toContain("两条报道指向同一件事");
  expect(view.getByText(/4900 tokens/)).toBeTruthy();
});

it("hides and restores every participation chart surface with one tool", async () => {
  const view = await renderDetail();
  await waitFor(() => expect(view.getByText("主力代理")).toBeTruthy());
  const user = userEvent.setup();

  await user.press(
    view.getByRole("button", { name: "参与结构，已显示" }),
  );
  expect(view.queryByText("主力代理")).toBeNull();
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
  expect(view.getByText("主力代理")).toBeTruthy();
  expect(
    view.getAllByTestId("participation-available", {
      includeHiddenElements: true,
    }),
  ).toHaveLength(1);
  expect(view.getByTestId("participation-summary")).toBeTruthy();
});

it("puts the chart first and keeps its caption behind a disclosure", async () => {
  const view = await renderDetail();

  await waitFor(() => expect(view.getByTestId("stock-chart-card")).toBeTruthy());
  // The chart outranks the fact summary on the page, which is the whole point
  // of the layout: the reader should meet the price series first.
  const order = view
    .getAllByTestId(/^(stock-chart-card|stock-fact-summary)$/)
    .map((node) => node.props.testID);
  expect(order).toEqual(["stock-chart-card", "stock-fact-summary"]);

  expect(view.queryByText(/每根活动柱与已完成 K 线一一对应/)).toBeNull();
  await userEvent.setup().press(
    view.getByRole("button", { name: "图表口径与免责，已折叠" }),
  );
  expect(view.getByText(/每根活动柱与已完成 K 线一一对应/)).toBeTruthy();
});

it("adds the RSI subchart only when the reader asks for it", async () => {
  const view = await renderDetail();
  const hidden = { includeHiddenElements: true } as const;

  await waitFor(() => expect(view.getByTestId("macd-panel", hidden)).toBeTruthy());
  expect(view.queryByTestId("rsi-panel", hidden)).toBeNull();

  await userEvent.setup().press(view.getByRole("button", { name: "RSI，已隐藏" }));
  expect(view.getByTestId("rsi-panel", hidden)).toBeTruthy();
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
    expect(view.getByText("行情不可用 · 网关过旧")).toBeTruthy(),
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
    "Capital-flow participation is unavailable for this snapshot.",
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
  // The gateway's own sentence turns; the wording it has not written down yet
  // reaches the reader untranslated rather than not at all.
  expect(view.getByTestId("snapshot-warnings")).toHaveTextContent(
    /本次快照没有资金流参与结构数据/,
  );
  expect(view.getByTestId("snapshot-warnings")).toHaveTextContent(
    /Capital-flow participation is partially unavailable/,
  );
});

it("names a missing participation bar's reason in Chinese", async () => {
  const payload = stockSnapshotFixture();
  payload.participationBars[1]!.missingReason = "incomplete minute coverage";
  const snapshot = decodeStockSnapshotEnvelope(payload, {
    now: new Date("2026-07-25T16:00:00.000Z"),
  });

  const view = await renderDetail({
    repository: repositoryWithSnapshot(async () => snapshot),
  });

  await waitFor(() =>
    expect(view.getByText(/1 根缺失 · 分钟级覆盖不完整/)).toBeTruthy(),
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
  expect(view.getByText("5 分钟 · 缓存数据")).toBeTruthy();
  expect(view.getByText("缓存事实摘要")).toBeTruthy();
  expect(view.queryByText("实时只读")).toBeNull();
  expect(view.queryByText("实时事实摘要")).toBeNull();
  expect(view.queryByText("5 分钟 · 实时只读")).toBeNull();
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
  expect(view.getByText("5 分钟 · 缓存数据")).toBeTruthy();
  expect(view.queryByText("实时只读")).toBeNull();
  expect(view.queryByText("5 分钟 · 实时只读")).toBeNull();
  const refreshing = view.getByRole("button", { name: "正在刷新行情" });
  expect(refreshing.props.accessibilityState).toEqual({ disabled: true });

  fireEvent.press(refreshing);
  expect(attempts).toBe(2);

  await act(async () => {
    pendingRefresh.resolve(cached);
    await pendingRefresh.promise;
  });
  await waitFor(() => expect(view.getByText("实时只读")).toBeTruthy());
  expect(view.getByText("5 分钟 · 实时只读")).toBeTruthy();
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
    expect(unavailableView.getByText("行情不可用 · 未配置")).toBeTruthy(),
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
    expect(view.getByText("行情不可用 · 未配置")).toBeTruthy(),
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
  expect(view.getByText(/日线 · 演示数据/)).toBeTruthy();
  // The fixture snapshot names its source `fixture`; the reader is told what
  // that means rather than shown the identifier.
  expect(view.getByTestId("stock-summary-meta")).toHaveTextContent(/来源 演示数据/);
  expect(view.getByTestId("stock-summary-meta")).not.toHaveTextContent(/fixture/);
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
    /宏观/,
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
      /分析不可用 · 连不上/,
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
  expect(view.getByTestId("institutional-holdings-card")).toBeTruthy();
  expect(view.queryByTestId("institutional-holdings-empty")).toBeNull();
  expect(
    view.getAllByTestId("magic-nine-series-marker", {
      includeHiddenElements: true,
    }),
  ).toHaveLength(7);
});

it("names what each still-dark card is waiting on", async () => {
  const view = await renderDetail();

  await waitFor(() => expect(view.getByTestId("decision-news")).toBeTruthy());

  // "尚未接入真实分析" was wrong on all three: the analysis service answers,
  // and each of these is short a specific input instead.
  expect(view.queryByText("尚未接入真实分析")).toBeNull();
  expect(view.queryByText(/服务端未接入基本面数据源/)).toBeNull();
  expect(view.queryByText(/服务端未接入宏观与地缘数据源/)).toBeNull();
  expect(view.getByTestId("decision-factor-breakdown")).toBeTruthy();
  expect(
    view.getByRole("button", { name: "为 NVDA 生成一次 Claude 新闻解读" }),
  ).toHaveTextContent(/只调用 1 次模型/);
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

it("says why a symbol will not open when the gateway rejected its candles", async () => {
  // The gateway is doing its job here: moomoo's candles failed point-in-time
  // validation and it refused to serve them. The page has to carry that whole
  // sentence, because "malformed" told the reader nothing.
  const view = await renderDetail({
    repository: repositoryWithSnapshot(async () => {
      throw new MarketDataError(
        "malformed",
        "MALFORMED_PROVIDER_DATA: Market data failed point-in-time validation",
      );
    }),
  });

  await waitFor(() =>
    expect(view.getByText("行情不可用 · 数据被拒")).toBeTruthy(),
  );
  const body = view.getByTestId("stock-state-body");
  // The gateway rejects on roughly twenty checks and names none of them, so
  // the screen says the data was refused without inventing which check failed.
  expect(body).toHaveTextContent(/没有说明具体是哪一项/);
  expect(body).toHaveTextContent(/不准确/);
  expect(body).toHaveTextContent(/不是你的操作问题/);
  expect(body).not.toHaveTextContent(/时序/);
  expect(view.queryByText(/malformed/i)).toBeNull();
  expect(view.getByRole("button", { name: "重试行情" })).toBeTruthy();
});

it("reports a declined analysis as its own state, not as a broken payload", async () => {
  const view = await renderDetail({
    analysis: analysisWith(async () => {
      throw new AnalysisRequestError(
        "analysis-failed",
        "The decision chain could not be evaluated",
      );
    }),
  });

  await waitFor(() =>
    expect(view.getByTestId("decision-state")).toHaveTextContent(
      /分析不可用 · 分析失败/,
    ),
  );
  const state = view.getByTestId("decision-state");
  expect(state).toHaveTextContent(/没有说明/);
  expect(state).not.toHaveTextContent(/时序校验/);
  expect(state).not.toHaveTextContent(/analysis-failed/);
  expect(view.getByRole("button", { name: "重试分析" })).toBeTruthy();
});

it("carries the same explanation into the news surface", async () => {
  const view = await renderDetail({
    analysis: analysisWith(async () => {
      throw new AnalysisRequestError("analysis-failed", "chain failed");
    }),
  });

  await waitFor(() =>
    expect(view.getByTestId("decision-news-unavailable")).toHaveTextContent(
      /新闻证据不可用 · 分析失败/,
    ),
  );
  expect(view.getByTestId("decision-news-unavailable")).not.toHaveTextContent(
    /analysis-failed/,
  );
});
