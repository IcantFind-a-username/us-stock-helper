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
  createMarketGatewayClient,
  decodeStockSnapshotEnvelope,
  GatewayRequestError,
} from "@/data/marketGateway";
import { decisionFixture } from "@/data/__tests__/decision.fixture";
import { stockSnapshotFixture } from "@/data/__tests__/stockSnapshot.fixture";
import type { LiveStockSnapshot, WatchlistQuote } from "@/domain/models";
import {
  MarketDataProvider,
  useDecision,
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
      <Text testID={`${symbol}-error-message`}>
        {result.error?.message ?? "none"}
      </Text>
      <Text testID={`${symbol}-refreshing`}>
        {result.refreshing ? "yes" : "no"}
      </Text>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled: result.refreshing }}
        disabled={result.refreshing}
        onPress={result.refresh}>
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

it("keeps stale truth visible while refreshing and blocks duplicate refreshes", async () => {
  const original = liveSnapshot();
  const recovered = liveSnapshot("NVDA", "2026-07-25T15:59:55.000Z");
  const failedRefresh = deferred<LiveStockSnapshot>();
  const pendingRefresh = deferred<LiveStockSnapshot>();
  let attempt = 0;
  const loadSnapshot = jest.fn<MarketDataSource["loadSnapshot"]>(async () => {
    attempt += 1;
    if (attempt === 1) return original;
    if (attempt === 2) return failedRefresh.promise;
    return pendingRefresh.promise;
  });
  const repository = repositoryWith(loadSnapshot);
  const view = await render(
    <MarketDataProvider repository={repository} retryDelaysMs={[]}>
      <SnapshotProbe symbol="NVDA" />
    </MarketDataProvider>,
  );

  await waitFor(() =>
    expect(view.getByTestId("NVDA-status").props.children).toBe("live"),
  );
  await act(async () => {
    fireEvent.press(view.getByText("refresh-NVDA"));
    await Promise.resolve();
  });
  await act(async () => {
    failedRefresh.reject(
      new GatewayRequestError("offline", "OpenD is offline"),
    );
    await failedRefresh.promise.catch(() => undefined);
  });
  expect(view.getByTestId("NVDA-status").props.children).toBe("stale");

  fireEvent.press(view.getByText("refresh-NVDA"));
  await waitFor(() => expect(loadSnapshot).toHaveBeenCalledTimes(3));
  expect(view.getByTestId("NVDA-status").props.children).toBe("stale");
  expect(view.getByTestId("NVDA-refreshing").props.children).toBe("yes");
  expect(view.getByTestId("NVDA-data-symbol").props.children).toBe("NVDA");
  expect(view.getByTestId("NVDA-verified").props.children).toBe(
    original.source.asOf,
  );
  expect(view.getByTestId("NVDA-cutoff").props.children).toBe(
    original.decisionCutoff,
  );
  expect(view.getByTestId("NVDA-error").props.children).toBe("offline");

  fireEvent.press(view.getByText("refresh-NVDA"));
  expect(loadSnapshot).toHaveBeenCalledTimes(3);

  await act(async () => {
    pendingRefresh.resolve(recovered);
    await pendingRefresh.promise;
  });
  await waitFor(() =>
    expect(view.getByTestId("NVDA-status").props.children).toBe("live"),
  );
  expect(view.getByTestId("NVDA-refreshing").props.children).toBe("no");
  expect(view.getByTestId("NVDA-verified").props.children).toBe(
    recovered.source.asOf,
  );
  expect(view.getByTestId("NVDA-cutoff").props.children).toBe(
    recovered.decisionCutoff,
  );
  expect(view.getByTestId("NVDA-error").props.children).toBe("none");
});

it("runs automatic stale retries through the guarded refreshing state", async () => {
  jest.useFakeTimers();
  try {
    const original = liveSnapshot();
    const recovered = liveSnapshot("NVDA", "2026-07-25T15:59:55.000Z");
    const initial = deferred<LiveStockSnapshot>();
    const manualFailure = deferred<LiveStockSnapshot>();
    const automaticFailure = deferred<LiveStockSnapshot>();
    const automaticSuccess = deferred<LiveStockSnapshot>();
    const responses = [
      initial.promise,
      manualFailure.promise,
      automaticFailure.promise,
      automaticSuccess.promise,
    ];
    let attempt = 0;
    const loadSnapshot = jest.fn<MarketDataSource["loadSnapshot"]>(
      async () => {
        const response = responses[attempt]!;
        attempt += 1;
        return response;
      },
    );
    const repository = repositoryWith(loadSnapshot);
    const view = await render(
      <MarketDataProvider repository={repository} retryDelaysMs={[10, 20]}>
        <SnapshotProbe symbol="NVDA" />
      </MarketDataProvider>,
    );

    await act(async () => {
      initial.resolve(original);
      await initial.promise;
    });
    expect(view.getByTestId("NVDA-status").props.children).toBe("live");

    await act(async () => {
      fireEvent.press(view.getByText("refresh-NVDA"));
      await Promise.resolve();
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(2);
    await act(async () => {
      manualFailure.reject(
        new GatewayRequestError("offline", "OpenD is offline"),
      );
      await manualFailure.promise.catch(() => undefined);
    });
    expect(view.getByTestId("NVDA-status").props.children).toBe("stale");
    expect(view.getByTestId("NVDA-refreshing").props.children).toBe("no");

    await act(async () => {
      await jest.advanceTimersByTimeAsync(10);
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(3);
    expect(view.getByTestId("NVDA-status").props.children).toBe("stale");
    expect(view.getByTestId("NVDA-refreshing").props.children).toBe("yes");
    expect(view.getByTestId("NVDA-data-symbol").props.children).toBe("NVDA");
    expect(view.getByTestId("NVDA-verified").props.children).toBe(
      original.source.asOf,
    );
    expect(view.getByTestId("NVDA-error").props.children).toBe("offline");

    fireEvent.press(view.getByText("refresh-NVDA"));
    expect(loadSnapshot).toHaveBeenCalledTimes(3);

    await act(async () => {
      automaticFailure.reject(
        new GatewayRequestError("offline", "automatic retry timed out"),
      );
      await automaticFailure.promise.catch(() => undefined);
    });
    expect(view.getByTestId("NVDA-status").props.children).toBe("stale");
    expect(view.getByTestId("NVDA-refreshing").props.children).toBe("no");
    expect(view.getByTestId("NVDA-verified").props.children).toBe(
      original.source.asOf,
    );
    expect(view.getByTestId("NVDA-error-message").props.children).toContain(
      "automatic retry timed out",
    );

    await act(async () => {
      await jest.advanceTimersByTimeAsync(19);
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(3);
    await act(async () => {
      await jest.advanceTimersByTimeAsync(1);
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(4);
    expect(view.getByTestId("NVDA-status").props.children).toBe("stale");
    expect(view.getByTestId("NVDA-refreshing").props.children).toBe("yes");

    await act(async () => {
      automaticSuccess.resolve(recovered);
      await automaticSuccess.promise;
    });
    expect(view.getByTestId("NVDA-status").props.children).toBe("live");
    expect(view.getByTestId("NVDA-refreshing").props.children).toBe("no");
    expect(view.getByTestId("NVDA-verified").props.children).toBe(
      recovered.source.asOf,
    );
    expect(view.getByTestId("NVDA-error").props.children).toBe("none");
    await view.unmount();
  } finally {
    jest.useRealTimers();
  }
});

it("recovers automatically after a typed mid-operation OpenD offline response", async () => {
  jest.useFakeTimers();
  try {
    const fetchImpl = jest
      .fn<typeof fetch>()
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => ({
          schemaVersion: "2",
          source: "moomoo",
          sourceStatus: "unavailable",
          symbol: "NVDA",
          interval: "5m",
          decisionCutoff: "2026-07-25T15:59:50.000Z",
          error: {
            code: "OPEND_OFFLINE",
            message: "moomoo OpenD is offline",
            retriable: true,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => stockSnapshotFixture(),
      } as Response);
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl: fetchImpl as unknown as typeof fetch,
      now: () => now,
    });
    const repository = repositoryWith((query, signal) =>
      client.getStockSnapshot(
        query.symbol,
        query.interval,
        query.count,
        signal,
      ),
    );
    const view = await render(
      <MarketDataProvider repository={repository} retryDelaysMs={[10]}>
        <SnapshotProbe symbol="NVDA" />
      </MarketDataProvider>,
    );

    await waitFor(() =>
      expect(view.getByTestId("NVDA-error").props.children).toBe("offline"),
    );
    expect(view.getByTestId("NVDA-status").props.children).toBe("unavailable");

    await act(async () => {
      await jest.advanceTimersByTimeAsync(10);
    });
    await waitFor(() =>
      expect(view.getByTestId("NVDA-status").props.children).toBe("live"),
    );
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(view.getByTestId("NVDA-error").props.children).toBe("none");
    await view.unmount();
  } finally {
    jest.useRealTimers();
  }
});

it("cancels a queued retry when a manual refresh supersedes it and succeeds", async () => {
  jest.useFakeTimers();
  try {
    const original = liveSnapshot();
    const recovered = liveSnapshot("NVDA", "2026-07-25T15:59:55.000Z");
    const initial = deferred<LiveStockSnapshot>();
    const firstFailure = deferred<LiveStockSnapshot>();
    const manualSuccess = deferred<LiveStockSnapshot>();
    const responses = [
      initial.promise,
      firstFailure.promise,
      manualSuccess.promise,
    ];
    let attempt = 0;
    const loadSnapshot = jest.fn<MarketDataSource["loadSnapshot"]>(
      async () => {
        const response = responses[attempt];
        attempt += 1;
        if (response) return response;
        throw new GatewayRequestError("offline", "superseded retry fired");
      },
    );
    const repository = repositoryWith(loadSnapshot);
    const view = await render(
      <MarketDataProvider repository={repository} retryDelaysMs={[10]}>
        <SnapshotProbe symbol="NVDA" />
      </MarketDataProvider>,
    );

    await act(async () => {
      initial.resolve(original);
      await initial.promise;
    });
    await act(async () => {
      fireEvent.press(view.getByText("refresh-NVDA"));
      await Promise.resolve();
    });
    await act(async () => {
      firstFailure.reject(
        new GatewayRequestError("offline", "OpenD is offline"),
      );
      await firstFailure.promise.catch(() => undefined);
    });
    expect(view.getByTestId("NVDA-status").props.children).toBe("stale");

    await act(async () => {
      await jest.advanceTimersByTimeAsync(5);
      fireEvent.press(view.getByText("refresh-NVDA"));
      await Promise.resolve();
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(3);
    expect(view.getByTestId("NVDA-refreshing").props.children).toBe("yes");

    await act(async () => {
      await jest.advanceTimersByTimeAsync(4);
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(3);

    await act(async () => {
      manualSuccess.resolve(recovered);
      await manualSuccess.promise;
    });
    expect(view.getByTestId("NVDA-status").props.children).toBe("live");

    await act(async () => {
      await jest.advanceTimersByTimeAsync(2);
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(3);
    expect(view.getByTestId("NVDA-status").props.children).toBe("live");
    expect(view.getByTestId("NVDA-verified").props.children).toBe(
      recovered.source.asOf,
    );
    await view.unmount();
  } finally {
    jest.useRealTimers();
  }
});

it("replaces a queued retry with one backoff chain after a manual failure", async () => {
  jest.useFakeTimers();
  try {
    const original = liveSnapshot();
    const initial = deferred<LiveStockSnapshot>();
    const firstFailure = deferred<LiveStockSnapshot>();
    const manualFailure = deferred<LiveStockSnapshot>();
    const responses = [
      initial.promise,
      firstFailure.promise,
      manualFailure.promise,
    ];
    let attempt = 0;
    const loadSnapshot = jest.fn<MarketDataSource["loadSnapshot"]>(
      async () => {
        const response = responses[attempt];
        attempt += 1;
        if (response) return response;
        throw new GatewayRequestError("offline", "automatic retry failed");
      },
    );
    const repository = repositoryWith(loadSnapshot);
    const view = await render(
      <MarketDataProvider repository={repository} retryDelaysMs={[10]}>
        <SnapshotProbe symbol="NVDA" />
      </MarketDataProvider>,
    );

    await act(async () => {
      initial.resolve(original);
      await initial.promise;
    });
    await act(async () => {
      fireEvent.press(view.getByText("refresh-NVDA"));
      await Promise.resolve();
    });
    await act(async () => {
      firstFailure.reject(
        new GatewayRequestError("offline", "OpenD is offline"),
      );
      await firstFailure.promise.catch(() => undefined);
    });

    await act(async () => {
      await jest.advanceTimersByTimeAsync(5);
      fireEvent.press(view.getByText("refresh-NVDA"));
      await Promise.resolve();
    });
    await act(async () => {
      manualFailure.reject(
        new GatewayRequestError("timeout", "manual refresh timed out"),
      );
      await manualFailure.promise.catch(() => undefined);
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(3);

    await act(async () => {
      await jest.advanceTimersByTimeAsync(10);
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(4);

    await view.unmount();
    await act(async () => {
      await jest.advanceTimersByTimeAsync(100);
    });
    expect(loadSnapshot).toHaveBeenCalledTimes(4);
  } finally {
    jest.useRealTimers();
  }
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
    await act(async () => {
      await jest.advanceTimersByTimeAsync(100);
    });
    expect(loadWatchlist).toHaveBeenCalledTimes(2);
  } finally {
    jest.useRealTimers();
  }
});

function DecisionProbe() {
  const result = useDecision("NVDA", "short");
  return (
    <View>
      <Text testID="decision-status">{result.status}</Text>
      <Text testID="decision-error">{result.error?.message ?? "none"}</Text>
    </View>
  );
}

it("attaches the paired device token to every analysis request it makes", async () => {
  const originalUrl = process.env.EXPO_PUBLIC_ANALYSIS_API_URL;
  const originalFetch = globalThis.fetch;
  const deviceToken = "8f4c1d2e6b7a09835c4d1e2f6a7b8c9d0e1f2a3b4c5d6e7f";
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "https://api.example.com";
  const fetchImpl = jest.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => decisionFixture(),
  })) as unknown as typeof fetch;
  globalThis.fetch = fetchImpl;
  try {
    const repository = repositoryWith(async () => liveSnapshot());
    const view = await render(
      <MarketDataProvider deviceToken={deviceToken} repository={repository}>
        <DecisionProbe />
      </MarketDataProvider>,
    );

    await waitFor(() =>
      expect(view.getByTestId("decision-status").props.children).toBe("live"),
    );
    const [, init] = (fetchImpl as jest.Mock).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect((init.headers as Record<string, string>).Authorization).toBe(
      `Bearer ${deviceToken}`,
    );
  } finally {
    globalThis.fetch = originalFetch;
    if (originalUrl === undefined) {
      delete process.env.EXPO_PUBLIC_ANALYSIS_API_URL;
    } else {
      process.env.EXPO_PUBLIC_ANALYSIS_API_URL = originalUrl;
    }
  }
});

it("sends no authorization at all when no device has been paired", async () => {
  const originalUrl = process.env.EXPO_PUBLIC_ANALYSIS_API_URL;
  const originalFetch = globalThis.fetch;
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "https://api.example.com";
  const fetchImpl = jest.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => decisionFixture(),
  })) as unknown as typeof fetch;
  globalThis.fetch = fetchImpl;
  try {
    const repository = repositoryWith(async () => liveSnapshot());
    const view = await render(
      <MarketDataProvider repository={repository}>
        <DecisionProbe />
      </MarketDataProvider>,
    );

    // Without a token the client refuses the origin outright rather than
    // sending an anonymous request that the server would answer with a 401.
    await waitFor(() =>
      expect(view.getByTestId("decision-status").props.children).toBe(
        "unavailable",
      ),
    );
    expect(fetchImpl).not.toHaveBeenCalled();
  } finally {
    globalThis.fetch = originalFetch;
    if (originalUrl === undefined) {
      delete process.env.EXPO_PUBLIC_ANALYSIS_API_URL;
    } else {
      process.env.EXPO_PUBLIC_ANALYSIS_API_URL = originalUrl;
    }
  }
});
