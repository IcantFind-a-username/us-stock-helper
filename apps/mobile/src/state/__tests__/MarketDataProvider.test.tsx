import { expect, it, jest } from "@jest/globals";
import {
  act,
  fireEvent,
  render,
  waitFor,
} from "@testing-library/react-native";
import { Pressable, Text, View } from "react-native";

import { readRuntimeConfig } from "@/config/runtimeConfig";
import {
  createGatewayMarketRepository,
  createMarketRepository,
  MarketDataError,
  type MarketDataSource,
} from "@/data/marketRepository";
import {
  decodeStockSnapshotEnvelope,
  GatewayRequestError,
} from "@/data/marketGateway";
import { stockSnapshotFixture } from "@/data/__tests__/stockSnapshot.fixture";
import type { LiveStockSnapshot, WatchlistQuote } from "@/domain/models";
import {
  MarketDataProvider,
  useMarketWatchlist,
  useStockSnapshot,
} from "../MarketDataProvider";

const now = new Date("2026-07-25T16:00:00.000Z");

function liveSnapshot(
  symbol = "NVDA",
  decisionCutoff = "2026-07-25T15:59:50.000Z",
) {
  const payload = stockSnapshotFixture();
  payload.symbol = symbol;
  payload.decisionCutoff = decisionCutoff;
  payload.quote.asOf = decisionCutoff;
  payload.quote.availableAt = decisionCutoff;
  return decodeStockSnapshotEnvelope(payload, { now, maxAgeMs: 60_000 });
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

function repositoryWith(
  loadSnapshot: MarketDataSource["loadSnapshot"],
  loadWatchlist: MarketDataSource["loadWatchlist"] = async () => ({
    source: "moomoo",
    asOf: "2026-07-25T15:59:50.000Z",
    quotes: [],
  }),
) {
  return createMarketRepository({ loadSnapshot, loadWatchlist });
}

function SnapshotProbe({ symbol }: { symbol: string }) {
  const result = useStockSnapshot(symbol, "5m", 200);
  return (
    <View>
      <Text testID={`${symbol}-status`}>{result.status}</Text>
      <Text testID={`${symbol}-data-symbol`}>{result.data?.symbol ?? "none"}</Text>
      <Text testID={`${symbol}-verified`}>{result.lastVerifiedAt ?? "none"}</Text>
      <Text testID={`${symbol}-cutoff`}>
        {"decisionCutoff" in (result.data ?? {})
          ? (result.data as LiveStockSnapshot).decisionCutoff
          : "none"}
      </Text>
      <Text testID={`${symbol}-error`}>{result.error?.category ?? "none"}</Text>
      <Pressable accessibilityRole="button" onPress={result.refresh}>
        <Text>refresh-{symbol}</Text>
      </Pressable>
    </View>
  );
}

function WatchlistProbe() {
  const result = useMarketWatchlist();
  return (
    <View>
      <Text testID="watchlist-status">{result.status}</Text>
      <Text testID="watchlist-source">{result.data?.source ?? "none"}</Text>
      <Text testID="watchlist-count">{result.data?.quotes.length ?? 0}</Text>
      <Text testID="watchlist-verified">{result.lastVerifiedAt ?? "none"}</Text>
      <Text testID="watchlist-error">{result.error?.category ?? "none"}</Text>
    </View>
  );
}

it("moves loading to live while preserving the verified asOf and decision cutoff", async () => {
  const snapshot = liveSnapshot();
  const pending = deferred<LiveStockSnapshot>();
  const repository = repositoryWith(async () => pending.promise);
  const view = await render(
    <MarketDataProvider repository={repository}>
      <SnapshotProbe symbol="NVDA" />
    </MarketDataProvider>,
  );

  expect(view.getByTestId("NVDA-status").props.children).toBe("loading");
  pending.resolve(snapshot);
  await waitFor(() =>
    expect(view.getByTestId("NVDA-status").props.children).toBe("live"),
  );
  expect(view.getByTestId("NVDA-verified").props.children).toBe(
    snapshot.source.asOf,
  );
  expect(view.getByTestId("NVDA-cutoff").props.children).toBe(
    snapshot.decisionCutoff,
  );
});

it("keeps the last verified snapshot stale after refresh fails", async () => {
  const snapshot = liveSnapshot();
  let attempt = 0;
  const repository = repositoryWith(async () => {
    attempt += 1;
    if (attempt === 1) return snapshot;
    throw new GatewayRequestError("offline", "OpenD is offline");
  });
  const view = await render(
    <MarketDataProvider repository={repository} retryDelaysMs={[]}>
      <SnapshotProbe symbol="NVDA" />
    </MarketDataProvider>,
  );

  await waitFor(() =>
    expect(view.getByTestId("NVDA-status").props.children).toBe("live"),
  );
  await fireEvent.press(view.getByText("refresh-NVDA"));
  await waitFor(() =>
    expect(view.getByTestId("NVDA-status").props.children).toBe("stale"),
  );

  expect(view.getByTestId("NVDA-data-symbol").props.children).toBe("NVDA");
  expect(view.getByTestId("NVDA-verified").props.children).toBe(
    snapshot.source.asOf,
  );
  expect(view.getByTestId("NVDA-cutoff").props.children).toBe(
    snapshot.decisionCutoff,
  );
  expect(view.getByTestId("NVDA-error").props.children).toBe("offline");
});

it("never relabels a cached snapshot live until a new request verifies it", async () => {
  const snapshot = liveSnapshot();
  let attempt = 0;
  const loadSnapshot = jest.fn<MarketDataSource["loadSnapshot"]>(async () => {
    attempt += 1;
    if (attempt === 1) return snapshot;
    throw new GatewayRequestError("offline", "OpenD is offline");
  });
  const repository = repositoryWith(loadSnapshot);
  const first = await render(
    <MarketDataProvider repository={repository} retryDelaysMs={[]}>
      <SnapshotProbe symbol="NVDA" />
    </MarketDataProvider>,
  );
  await waitFor(() =>
    expect(first.getByTestId("NVDA-status").props.children).toBe("live"),
  );
  await first.unmount();

  const second = await render(
    <MarketDataProvider repository={repository} retryDelaysMs={[]}>
      <SnapshotProbe symbol="NVDA" />
    </MarketDataProvider>,
  );
  await waitFor(() =>
    expect(second.getByTestId("NVDA-status").props.children).toBe("stale"),
  );
  expect(loadSnapshot).toHaveBeenCalledTimes(2);
  expect(second.getByTestId("NVDA-verified").props.children).toBe(
    snapshot.source.asOf,
  );
  expect(second.getByTestId("NVDA-cutoff").props.children).toBe(
    snapshot.decisionCutoff,
  );
});

it("reports unavailable when the first request fails", async () => {
  const repository = repositoryWith(async () => {
    throw new GatewayRequestError("permission", "permission denied");
  });
  const view = await render(
    <MarketDataProvider repository={repository}>
      <SnapshotProbe symbol="NVDA" />
    </MarketDataProvider>,
  );

  await waitFor(() =>
    expect(view.getByTestId("NVDA-status").props.children).toBe("unavailable"),
  );
  expect(view.getByTestId("NVDA-data-symbol").props.children).toBe("none");
  expect(view.getByTestId("NVDA-error").props.children).toBe("permission");
});

it("ignores an old response and aborts its subscription after the symbol changes", async () => {
  const nvda = deferred<LiveStockSnapshot>();
  const tsla = deferred<LiveStockSnapshot>();
  const signals: AbortSignal[] = [];
  const repository = repositoryWith((query, signal) => {
    signals.push(signal);
    return query.symbol === "NVDA" ? nvda.promise : tsla.promise;
  });
  const view = await render(
    <MarketDataProvider repository={repository}>
      <SnapshotProbe symbol="NVDA" />
    </MarketDataProvider>,
  );

  await view.rerender(
    <MarketDataProvider repository={repository}>
      <SnapshotProbe symbol="TSLA" />
    </MarketDataProvider>,
  );
  expect(signals[0]?.aborted).toBe(true);

  nvda.resolve(liveSnapshot("NVDA"));
  tsla.resolve(liveSnapshot("TSLA"));
  await waitFor(() =>
    expect(view.getByTestId("TSLA-status").props.children).toBe("live"),
  );
  expect(view.getByTestId("TSLA-data-symbol").props.children).toBe("TSLA");
  expect(view.queryByTestId("NVDA-data-symbol")).toBeNull();
});

it("shares one in-flight snapshot request between concurrent consumers", async () => {
  const pending = deferred<LiveStockSnapshot>();
  const loadSnapshot = jest.fn<MarketDataSource["loadSnapshot"]>(
    async () => pending.promise,
  );
  const repository = repositoryWith(loadSnapshot);
  const view = await render(
    <MarketDataProvider repository={repository}>
      <SnapshotProbe symbol="NVDA" />
      <SnapshotProbe symbol="NVDA" />
    </MarketDataProvider>,
  );

  expect(loadSnapshot).toHaveBeenCalledTimes(1);
  pending.resolve(liveSnapshot());
  await waitFor(() =>
    expect(view.getAllByTestId("NVDA-status").map((node) => node.props.children)).toEqual([
      "live",
      "live",
    ]),
  );
});

it("starts a new request when the same key remounts after every consumer cancels", async () => {
  const firstRequest = deferred<LiveStockSnapshot>();
  const secondRequest = deferred<LiveStockSnapshot>();
  let attempt = 0;
  const loadSnapshot = jest.fn<MarketDataSource["loadSnapshot"]>(async () => {
    attempt += 1;
    return attempt === 1 ? firstRequest.promise : secondRequest.promise;
  });
  const repository = repositoryWith(loadSnapshot);
  const first = await render(
    <MarketDataProvider repository={repository}>
      <SnapshotProbe symbol="NVDA" />
    </MarketDataProvider>,
  );
  await first.unmount();

  const second = await render(
    <MarketDataProvider repository={repository}>
      <SnapshotProbe symbol="NVDA" />
    </MarketDataProvider>,
  );
  expect(loadSnapshot).toHaveBeenCalledTimes(2);
  secondRequest.resolve(liveSnapshot());
  await waitFor(() =>
    expect(second.getByTestId("NVDA-status").props.children).toBe("live"),
  );
  firstRequest.resolve(liveSnapshot());
});

it("aborts the production fetch when its last mounted consumer unmounts", async () => {
  const originalFetch = globalThis.fetch;
  let fetchSignal: AbortSignal | undefined;
  let resolveFetch!: (response: Response) => void;
  const fetchImpl = jest.fn(
    async (_url: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        resolveFetch = resolve;
        fetchSignal = init?.signal as AbortSignal;
        fetchSignal.addEventListener(
          "abort",
          () =>
            reject(
              Object.assign(new Error("consumer cancelled"), {
                name: "AbortError",
              }),
            ),
          { once: true },
        );
      }),
  ) as unknown as typeof fetch;
  globalThis.fetch = fetchImpl;

  try {
    const repository = createGatewayMarketRepository({
      apiUrl: "http://127.0.0.1:8765",
    });
    const view = await render(
      <MarketDataProvider repository={repository}>
        <SnapshotProbe symbol="NVDA" />
      </MarketDataProvider>,
    );
    await waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(1));

    await view.unmount();
    const aborted = fetchSignal?.aborted;
    if (!aborted) {
      resolveFetch({
        ok: true,
        status: 200,
        json: async () => stockSnapshotFixture(),
      } as Response);
      await Promise.resolve();
    }
    expect(aborted).toBe(true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

it("rejects embedded development tokens from production runtime configuration", () => {
  expect(() =>
    readRuntimeConfig({
      apiUrl: "https://market.example.com",
      development: false,
      developmentToken: "development-only-token",
    }),
  ).toThrow(/development token/i);
});

it("labels developer fixture data as demo and never as live", async () => {
  const demoQuotes: WatchlistQuote[] = [
    {
      symbol: "NVDA",
      price: 142.25,
      changePercent: 2.4,
      direction: "bullish",
      summary: "演示",
    },
  ];
  const loadWatchlist = jest.fn<MarketDataSource["loadWatchlist"]>();
  const repository = repositoryWith(async () => liveSnapshot(), loadWatchlist);
  const view = await render(
    <MarketDataProvider
      development
      initialDemoMode
      demoWatchlist={demoQuotes}
      repository={repository}>
      <WatchlistProbe />
    </MarketDataProvider>,
  );

  expect(view.getByTestId("watchlist-status").props.children).toBe("demo");
  expect(view.getByTestId("watchlist-source").props.children).toBe("fixture");
  expect(view.getByTestId("watchlist-count").props.children).toBe(1);
  expect(view.getByTestId("watchlist-verified").props.children).toBe("none");
  expect(loadWatchlist).not.toHaveBeenCalled();
});

it("does not schedule endless retries for permission or validation failures", async () => {
  jest.useFakeTimers();
  const loadSnapshot = jest.fn<MarketDataSource["loadSnapshot"]>(async () => {
    throw new MarketDataError("validation", "invalid response");
  });
  const repository = repositoryWith(loadSnapshot);
  const view = await render(
    <MarketDataProvider repository={repository} retryDelaysMs={[1, 2, 4, 8, 30]}>
      <SnapshotProbe symbol="NVDA" />
    </MarketDataProvider>,
  );

  await waitFor(() =>
    expect(view.getByTestId("NVDA-status").props.children).toBe("unavailable"),
  );
  jest.runOnlyPendingTimers();
  expect(loadSnapshot).toHaveBeenCalledTimes(1);
  jest.useRealTimers();
});

it.each(["login-required", "permission", "validation"] as const)(
  "does not retry a watchlist %s failure",
  async (category) => {
    jest.useFakeTimers();
    try {
      const loadWatchlist = jest.fn<MarketDataSource["loadWatchlist"]>(
        async () => {
          throw new MarketDataError(category, category);
        },
      );
      const repository = repositoryWith(
        async () => liveSnapshot(),
        loadWatchlist,
      );
      const view = await render(
        <MarketDataProvider
          repository={repository}
          retryDelaysMs={[1, 2, 4, 8, 30]}>
          <WatchlistProbe />
        </MarketDataProvider>,
      );

      await waitFor(() =>
        expect(view.getByTestId("watchlist-status").props.children).toBe(
          "unavailable",
        ),
      );
      jest.runOnlyPendingTimers();
      expect(loadWatchlist).toHaveBeenCalledTimes(1);
      expect(view.getByTestId("watchlist-error").props.children).toBe(category);
    } finally {
      jest.useRealTimers();
    }
  },
);

it("retries an offline watchlist while a consumer remains mounted", async () => {
  jest.useFakeTimers();
  try {
    const loadWatchlist = jest.fn<MarketDataSource["loadWatchlist"]>(
      async () => {
        throw new MarketDataError("offline", "offline");
      },
    );
    const repository = repositoryWith(
      async () => liveSnapshot(),
      loadWatchlist,
    );
    const view = await render(
      <MarketDataProvider repository={repository} retryDelaysMs={[10]}>
        <WatchlistProbe />
      </MarketDataProvider>,
    );
    await waitFor(() =>
      expect(view.getByTestId("watchlist-status").props.children).toBe(
        "unavailable",
      ),
    );

    await act(async () => {
      await jest.advanceTimersByTimeAsync(10);
    });
    expect(loadWatchlist).toHaveBeenCalledTimes(2);
    await view.unmount();
  } finally {
    jest.useRealTimers();
  }
});
