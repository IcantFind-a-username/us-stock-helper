import type { LiveStockSnapshot, WatchlistQuote } from "@/domain/models";
import {
  createMarketGatewayClient,
  GatewayRequestError,
  GatewayValidationError,
  type CandleInterval,
} from "./marketGateway";
import type { MarketRuntimeConfig } from "@/config/runtimeConfig";

/**
 * Every way a market or analysis request can fail, as the reader experiences
 * it rather than as the wire spells it.
 *
 * One category per remedy is the rule. Two server codes share a category only
 * when the reader would do the same thing about both, because a category is
 * what a screen turns into a sentence: collapsing an unlogged-in OpenD into
 * the same bucket as an unpaired phone produced a screen that could not tell
 * the reader which of the two to go fix.
 */
export const marketErrorCategories = [
  "analysis-failed",
  "auth-required",
  "auth-unavailable",
  "client-not-allowed",
  "client-update-required",
  "configuration",
  "contract",
  "invalid-request",
  "login-required",
  "malformed",
  "offline",
  "permission",
  "provider-error",
  "rate-limited",
  "route-unsupported",
  "sdk-unavailable",
  "stale",
  "timeout",
  "unspecified",
  "unsupported",
  "validation",
] as const;

export type MarketDataErrorCategory = (typeof marketErrorCategories)[number];

export class MarketDataError extends Error {
  constructor(
    public readonly category: MarketDataErrorCategory,
    message: string,
  ) {
    super(message);
    this.name = "MarketDataError";
  }
}

export type SnapshotQuery = {
  symbol: string;
  interval: CandleInterval;
  count: number;
};

export type MarketWatchlist = {
  source: "moomoo";
  asOf: string;
  quotes: WatchlistQuote[];
};

export type MarketDataSource = {
  loadSnapshot(
    query: SnapshotQuery,
    signal: AbortSignal,
  ): Promise<LiveStockSnapshot>;
  loadWatchlist(signal: AbortSignal): Promise<MarketWatchlist>;
};

type RequestOptions = {
  signal?: AbortSignal;
  forceRefresh?: boolean;
};

export type MarketRepository = {
  peekStockSnapshot(query: SnapshotQuery): LiveStockSnapshot | null;
  getStockSnapshot(
    query: SnapshotQuery,
    options?: RequestOptions,
  ): Promise<LiveStockSnapshot>;
  peekWatchlist(): MarketWatchlist | null;
  getWatchlist(options?: RequestOptions): Promise<MarketWatchlist>;
};

type InFlight<T> = {
  controller: AbortController;
  consumers: number;
  onIdle(): void;
  promise: Promise<T>;
};

function abortError() {
  const error = new Error("market request was aborted");
  error.name = "AbortError";
  return error;
}

function normalizeError(error: unknown): Error {
  if (error instanceof Error && error.name === "AbortError") return error;
  if (error instanceof MarketDataError) return error;
  if (error instanceof GatewayRequestError) {
    return new MarketDataError(error.kind, error.message);
  }
  if (error instanceof GatewayValidationError) {
    return new MarketDataError("validation", error.message);
  }
  if (error instanceof Error) {
    return new MarketDataError("offline", error.message);
  }
  return new MarketDataError("offline", "market data is unavailable");
}

function subscribe<T>(entry: InFlight<T>, signal?: AbortSignal): Promise<T> {
  if (signal?.aborted) return Promise.reject(abortError());
  entry.consumers += 1;

  return new Promise<T>((resolve, reject) => {
    let settled = false;

    const finish = () => {
      if (settled) return false;
      settled = true;
      signal?.removeEventListener("abort", onAbort);
      entry.consumers -= 1;
      return true;
    };
    const onAbort = () => {
      if (!finish()) return;
      if (entry.consumers === 0) {
        entry.controller.abort();
        entry.onIdle();
      }
      reject(abortError());
    };

    signal?.addEventListener("abort", onAbort, { once: true });
    entry.promise.then(
      (value) => {
        if (finish()) resolve(value);
      },
      (error: unknown) => {
        if (finish()) reject(normalizeError(error));
      },
    );
  });
}

export function createMarketRepository({
  loadSnapshot,
  loadWatchlist,
}: MarketDataSource): MarketRepository {
  const snapshotCache = new Map<string, LiveStockSnapshot>();
  const snapshotRequests = new Map<string, InFlight<LiveStockSnapshot>>();
  let watchlistCache: MarketWatchlist | null = null;
  let watchlistRequest: InFlight<MarketWatchlist> | null = null;

  const snapshotKey = ({ symbol, interval, count }: SnapshotQuery) =>
    `${symbol.trim().toUpperCase()}|${interval}|${count}`;

  return {
    peekStockSnapshot(query) {
      return snapshotCache.get(snapshotKey(query)) ?? null;
    },

    getStockSnapshot(query, options = {}) {
      if (options.signal?.aborted) return Promise.reject(abortError());
      const key = snapshotKey(query);
      const existing = snapshotRequests.get(key);
      if (existing) return subscribe(existing, options.signal);
      const cached = snapshotCache.get(key);
      if (cached && !options.forceRefresh) return Promise.resolve(cached);

      const controller = new AbortController();
      const entry: InFlight<LiveStockSnapshot> = {
        controller,
        consumers: 0,
        onIdle() {
          if (snapshotRequests.get(key) === entry) snapshotRequests.delete(key);
        },
        promise: Promise.resolve().then(() => loadSnapshot(query, controller.signal)),
      };
      snapshotRequests.set(key, entry);
      entry.promise = entry.promise
        .then((snapshot) => {
          if (!controller.signal.aborted) snapshotCache.set(key, snapshot);
          return snapshot;
        })
        .finally(() => {
          if (snapshotRequests.get(key) === entry) snapshotRequests.delete(key);
        });
      return subscribe(entry, options.signal);
    },

    peekWatchlist() {
      return watchlistCache;
    },

    getWatchlist(options = {}) {
      if (options.signal?.aborted) return Promise.reject(abortError());
      if (watchlistRequest) return subscribe(watchlistRequest, options.signal);
      if (watchlistCache && !options.forceRefresh) {
        return Promise.resolve(watchlistCache);
      }

      const controller = new AbortController();
      const entry: InFlight<MarketWatchlist> = {
        controller,
        consumers: 0,
        onIdle() {
          if (watchlistRequest === entry) watchlistRequest = null;
        },
        promise: Promise.resolve().then(() => loadWatchlist(controller.signal)),
      };
      watchlistRequest = entry;
      entry.promise = entry.promise
        .then((watchlist) => {
          if (!controller.signal.aborted) watchlistCache = watchlist;
          return watchlist;
        })
        .finally(() => {
          if (watchlistRequest === entry) watchlistRequest = null;
        });
      return subscribe(entry, options.signal);
    },
  };
}

export function createGatewayMarketRepository(
  config: MarketRuntimeConfig,
): MarketRepository {
  if (!config.apiUrl) {
    const unavailable = async () => {
      throw new MarketDataError(
        "configuration",
        "EXPO_PUBLIC_MARKET_API_URL is not configured",
      );
    };
    return createMarketRepository({
      loadSnapshot: unavailable,
      loadWatchlist: unavailable,
    });
  }

  const client = createMarketGatewayClient({
    baseUrl: config.apiUrl,
    ...(config.authorizationToken
      ? { authorizationToken: config.authorizationToken }
      : {}),
  });

  return createMarketRepository({
    loadSnapshot: (query, signal) =>
      client.getStockSnapshot(
        query.symbol,
        query.interval,
        query.count,
        signal,
      ),
    loadWatchlist: (signal) => client.getWatchlist(signal),
  });
}

/**
 * Only failures that can end on their own are retried.
 *
 * A missing SDK, an unlogged-in OpenD or a phone whose pairing was revoked
 * needs a person to act, and a timer that keeps asking hides that: the screen
 * looks busy instead of looking like it is waiting for its operator. Quota
 * exhaustion is on this list because it does expire by itself, and the caller
 * backs off between attempts rather than hammering the limit.
 */
export function isRetryableMarketError(error: MarketDataError) {
  return (
    error.category === "offline" ||
    error.category === "rate-limited" ||
    error.category === "stale" ||
    error.category === "timeout"
  );
}
