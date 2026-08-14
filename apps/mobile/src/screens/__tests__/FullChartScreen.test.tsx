import { beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  act,
  fireEvent,
  render,
  userEvent,
  waitFor,
} from "@testing-library/react-native";

import {
  decodeStockSnapshotEnvelope,
  decodeStockSnapshotV3Envelope,
} from "@/data/marketGateway";
import {
  createMarketRepository,
  MarketDataError,
  type MarketDataSource,
  type MarketRepository,
} from "@/data/marketRepository";
import type { LiveStockSnapshot } from "@/domain/models";
import { AppStateProvider } from "@/state/AppStateProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";

import { stockSnapshotFixture } from "../../data/__tests__/stockSnapshot.fixture";
import { stockSnapshotV3Fixture } from "../../data/__tests__/stockSnapshotV3.fixture";
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

function completedDailyCandlesSnapshot() {
  const payload = stockSnapshotV3Fixture();
  payload.interval = "day";
  payload.count = 250;
  const sections = payload.sections as unknown as Record<string, unknown>;
  sections.quote = {
    availabilityStatus: "unavailable",
    qualityStatus: "invalid",
    source: null,
    asOf: null,
    availableAt: null,
    receivedAt: null,
    data: null,
    errorCode: "QUOTE_UNAVAILABLE",
    reason: "实时报价不可用",
    warnings: [],
    anomalies: [],
    methodVersion: "unavailable-v1",
  };
  payload.status = "partial";
  return decodeStockSnapshotV3Envelope(payload);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
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
  retryDelaysMs = [],
}: {
  repository?: MarketRepository;
  demoMode?: boolean;
  retryDelaysMs?: readonly number[];
} = {}) {
  return render(
    <AppStateProvider>
      <MarketDataProvider
        development
        initialDemoMode={demoMode}
        repository={repository}
        retryDelaysMs={retryDelaysMs}>
        <FullChartScreen />
      </MarketDataProvider>
    </AppStateProvider>,
  );
}

it("renders the same live snapshot with selectable candles and both indicators", async () => {
  const view = await renderChart();

  await waitFor(() => expect(view.getByText("NVDA 专业图表")).toBeTruthy());
  expect(view.getByText("实时只读 · 截止 2026-07-25 15:59:50 UTC")).toBeTruthy();
  expect(view.getByTestId("stock-chart-card")).toBeTruthy();
  expect(view.getByText("RSI 56.2")).toBeTruthy();
  expect(view.getByText("MACD 0.15")).toBeTruthy();
  expect(view.getByText("MA5 140.80")).toBeTruthy();
  expect(view.getByText("机构持仓披露 · 延迟数据")).toBeTruthy();
  // Nothing on a live chart may read as demo, in any wording.
  expect(view.queryByText(/演示/)).toBeNull();
  expect(view.queryByText("上涨概率")).toBeNull();

  const user = userEvent.setup();
  await user.press(
    view.getByRole("button", { name: /NVDA 图表摘要，2 根已完成 K 线/ }),
  );
  expect(view.getByLabelText(/NVDA 收盘时间 2026-07-25T15:50:00.000Z/)).toBeTruthy();
});

it("labels a verified candles-only daily chart as completed K lines", async () => {
  const queries: { symbol: string; interval: string; count: number }[] = [];
  const view = await renderChart({
    repository: repositoryWithSnapshot(async (query) => {
      queries.push(query);
      return completedDailyCandlesSnapshot();
    }),
  });

  await waitFor(() => expect(view.getByText("NVDA 专业图表")).toBeTruthy());
  expect(queries).toEqual([{ symbol: "NVDA", interval: "day", count: 250 }]);
  expect(
    view.getByText("已完成K线 · 截止 2026-07-25 15:59:50 UTC"),
  ).toBeTruthy();
  expect(view.getByText("日线 · 已完成K线")).toBeTruthy();
  expect(view.toJSON()).not.toHaveTextContent(/实时只读|实时行情/);
  expect(view.getByTestId("stock-chart-card")).toBeTruthy();
  expect(
    view.getByRole("button", { name: /NVDA 图表摘要/ }).props.accessibilityLabel,
  ).toContain("最新日K收盘 141.50，实时报价不可用");
});

it("starts on daily candles and loads intraday only after the reader asks", async () => {
  const queries: { symbol: string; interval: string; count: number }[] = [];
  const repository = repositoryWithSnapshot(async (query) => {
    queries.push(query);
    return liveSnapshot();
  });
  const view = await renderChart({ repository });

  await waitFor(() => expect(queries).toEqual([
    { symbol: "NVDA", interval: "day", count: 250 },
  ]));
  await userEvent.setup().press(view.getByRole("tab", { name: "5分" }));
  await waitFor(() => expect(queries).toEqual([
    { symbol: "NVDA", interval: "day", count: 250 },
    { symbol: "NVDA", interval: "5m", count: 200 },
  ]));
});

it("always renders unavailable Magic Nine as unavailable without a zero marker", async () => {
  const view = await renderChart({
    repository: repositoryWithSnapshot(async () =>
      unavailableMagicSnapshot(),
    ),
  });

  await waitFor(() =>
    expect(view.getByText("九转 暂不可用")).toBeTruthy(),
  );
  expect(view.queryByText("九转 0 · 尚未完成")).toBeNull();
  expect(
    view.queryByTestId("magic-nine-marker", {
      includeHiddenElements: true,
    }),
  ).toBeNull();
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
  expect(staleView.getByTestId("stock-chart-card")).toBeTruthy();
  expect(
    staleView.getByText(
      "缓存数据 · 截止 2026-07-25 15:59:50 UTC",
    ),
  ).toBeTruthy();
  expect(staleView.getByText("5 分钟 · 缓存数据")).toBeTruthy();
  expect(staleView.queryByText(/实时只读/)).toBeNull();
  expect(staleView.queryByText("5 分钟 · 实时只读")).toBeNull();
  expect(staleView.queryByText("演示数据 · 非实时行情")).toBeNull();
  await staleView.unmount();

  const unavailableView = await renderChart({
    repository: repositoryWithSnapshot(async () => {
      throw new MarketDataError("permission", "quote permission required");
    }),
  });
  await waitFor(() =>
    expect(unavailableView.getByText("行情不可用 · 无权限")).toBeTruthy(),
  );
  expect(unavailableView.getByRole("button", { name: "重试行情" })).toBeTruthy();
  // The big chart explains the failure as fully as the stock page does.
  expect(unavailableView.getByTestId("chart-state-body")).toHaveTextContent(
    /行情权限/,
  );
  expect(unavailableView.queryByText(/permission/)).toBeNull();
  expect(unavailableView.queryByTestId("stock-chart-card")).toBeNull();
  expect(unavailableView.queryByText("演示数据 · 非实时行情")).toBeNull();
});

it("keeps the full chart stale while an automatic refresh is pending", async () => {
  jest.useFakeTimers();
  try {
    const cached = liveSnapshot();
    const initialFailure = deferred<LiveStockSnapshot>();
    const automaticSuccess = deferred<LiveStockSnapshot>();
    let attempts = 0;
    const repository: MarketRepository = {
      peekStockSnapshot: () => cached,
      getStockSnapshot: async () => {
        attempts += 1;
        return attempts === 1
          ? initialFailure.promise
          : automaticSuccess.promise;
      },
      peekWatchlist: () => null,
      getWatchlist: async () => {
        throw new MarketDataError("offline", "gateway offline");
      },
    };
    const view = await renderChart({
      repository,
      retryDelaysMs: [10],
    });

    await act(async () => {
      initialFailure.reject(
        new MarketDataError("offline", "gateway offline"),
      );
      await initialFailure.promise.catch(() => undefined);
    });
    expect(view.getByText("5 分钟 · 缓存数据")).toBeTruthy();
    expect(view.queryByText("5 分钟 · 实时只读")).toBeNull();

    await act(async () => {
      await jest.advanceTimersByTimeAsync(10);
    });
    expect(attempts).toBe(2);
    expect(
      view.getByText("行情已延迟 · 原始时间 2026-07-25 15:59:50 UTC"),
    ).toBeTruthy();
    expect(
      view.getByText("缓存数据 · 截止 2026-07-25 15:59:50 UTC"),
    ).toBeTruthy();
    expect(view.getByText("5 分钟 · 缓存数据")).toBeTruthy();
    expect(view.queryByText(/实时只读/)).toBeNull();
    expect(view.queryByText("5 分钟 · 实时只读")).toBeNull();
    const refreshing = view.getByRole("button", {
      name: "正在刷新行情",
    });
    expect(refreshing.props.accessibilityState).toEqual({ disabled: true });

    fireEvent.press(refreshing);
    expect(attempts).toBe(2);

    await act(async () => {
      automaticSuccess.resolve(cached);
      await automaticSuccess.promise;
    });
    expect(view.getByText("5 分钟 · 实时只读")).toBeTruthy();
    expect(view.queryByText(/行情已延迟/)).toBeNull();
    await view.unmount();
  } finally {
    jest.useRealTimers();
  }
});

it("wires retry through loading to a recovered full live chart", async () => {
  let attempts = 0;
  let resolveRetry!: (snapshot: LiveStockSnapshot) => void;
  const retryResult = new Promise<LiveStockSnapshot>((resolve) => {
    resolveRetry = resolve;
  });
  const repository = repositoryWithSnapshot(async () => {
    attempts += 1;
    if (attempts === 1) {
      throw new MarketDataError("permission", "quote permission required");
    }
    return retryResult;
  });
  const view = await renderChart({ repository });

  await waitFor(() =>
    expect(view.getByText("行情不可用 · 无权限")).toBeTruthy(),
  );
  fireEvent.press(view.getByRole("button", { name: "重试行情" }));
  await waitFor(() => expect(attempts).toBe(2));
  expect(view.getByText("正在连接 moomoo 行情…")).toBeTruthy();
  expect(view.queryByRole("button", { name: "重试行情" })).toBeNull();

  resolveRetry(liveSnapshot());
  await waitFor(() => expect(view.getByText("NVDA 专业图表")).toBeTruthy());
  expect(
    view.getByText("实时只读 · 截止 2026-07-25 15:59:50 UTC"),
  ).toBeTruthy();
});

it("marks the whole chart as non-live only in explicit demo mode", async () => {
  const view = await renderChart({ demoMode: true });

  await waitFor(() =>
    expect(view.getByText("演示数据 · 非实时行情")).toBeTruthy(),
  );
  expect(view.getByText(/日线 · 演示数据/)).toBeTruthy();
  expect(view.getByText(/上涨概率/)).toBeTruthy();
  expect(view.queryByText("实时只读")).toBeNull();
});
