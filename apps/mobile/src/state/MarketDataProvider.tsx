import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";

import { getMarketRuntimeConfig } from "@/config/runtimeConfig";
import {
  createGatewayMarketRepository,
  isRetryableMarketError,
  MarketDataError,
  type MarketRepository,
  type MarketWatchlist,
} from "@/data/marketRepository";
import type {
  DemoChartSnapshot,
  LiveStockSnapshot,
  WatchlistQuote,
} from "@/domain/models";
import type { CandleInterval } from "@/data/marketGateway";

export type MarketDataStatus =
  | "demo"
  | "live"
  | "loading"
  | "stale"
  | "unavailable";

export type MarketDataState<T> = {
  status: MarketDataStatus;
  data: T | null;
  error: MarketDataError | null;
  lastVerifiedAt: string | null;
  refresh(): void;
};

export type DemoMarketWatchlist = {
  source: "fixture";
  asOf: null;
  quotes: WatchlistQuote[];
};

type MarketDataContextValue = {
  repository: MarketRepository;
  demoMode: boolean;
  setDemoMode(value: boolean): void;
  development: boolean;
  demoWatchlist: WatchlistQuote[];
  retryDelaysMs: readonly number[];
};

type MarketDataProviderProps = PropsWithChildren<{
  repository?: MarketRepository;
  development?: boolean;
  initialDemoMode?: boolean;
  demoWatchlist?: WatchlistQuote[];
  retryDelaysMs?: readonly number[];
}>;

const defaultRetryDelaysMs = [1_000, 2_000, 4_000, 8_000, 30_000] as const;
const MarketDataContext = createContext<MarketDataContextValue | null>(null);

function unavailableRepository(error: unknown) {
  const marketError =
    error instanceof MarketDataError
      ? error
      : new MarketDataError(
          "configuration",
          error instanceof Error ? error.message : "invalid market configuration",
        );
  return {
    peekStockSnapshot: () => null,
    getStockSnapshot: async () => Promise.reject(marketError),
    peekWatchlist: () => null,
    getWatchlist: async () => Promise.reject(marketError),
  } satisfies MarketRepository;
}

export function MarketDataProvider({
  children,
  repository,
  development = typeof __DEV__ !== "undefined" && __DEV__,
  initialDemoMode = false,
  demoWatchlist = [],
  retryDelaysMs = defaultRetryDelaysMs,
}: MarketDataProviderProps) {
  if (initialDemoMode && !development) {
    throw new Error("demo mode is developer-only");
  }

  const defaultRepository = useMemo(() => {
    if (repository) return repository;
    try {
      return createGatewayMarketRepository(getMarketRuntimeConfig());
    } catch (error) {
      return unavailableRepository(error);
    }
  }, [repository]);
  const [demoMode, setDemoModeState] = useState(initialDemoMode);
  const setDemoMode = useCallback(
    (value: boolean) => {
      if (value && !development) {
        throw new Error("demo mode is developer-only");
      }
      setDemoModeState(value);
    },
    [development],
  );
  const value = useMemo<MarketDataContextValue>(
    () => ({
      repository: defaultRepository,
      demoMode,
      setDemoMode,
      development,
      demoWatchlist,
      retryDelaysMs,
    }),
    [
      defaultRepository,
      demoMode,
      demoWatchlist,
      development,
      retryDelaysMs,
      setDemoMode,
    ],
  );

  return (
    <MarketDataContext.Provider value={value}>
      {children}
    </MarketDataContext.Provider>
  );
}

function useMarketDataContext() {
  const value = useContext(MarketDataContext);
  if (!value) {
    throw new Error("market hooks must be used within MarketDataProvider");
  }
  return value;
}

function toMarketError(error: unknown) {
  if (error instanceof MarketDataError) return error;
  return new MarketDataError(
    "offline",
    error instanceof Error ? error.message : "market data is unavailable",
  );
}

type LoadResult<T> = {
  data: T;
  verifiedAt: string;
};

function useLiveResource<T>({
  resourceKey,
  load,
  cachedData,
  demoData,
}: {
  resourceKey: string;
  load(signal: AbortSignal, forceRefresh: boolean): Promise<LoadResult<T>>;
  cachedData: LoadResult<T> | null;
  demoData: T | null;
}): MarketDataState<T> {
  const { demoMode, retryDelaysMs } = useMarketDataContext();
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [state, setState] = useState<
    Omit<MarketDataState<T>, "refresh"> & { resourceKey: string }
  >({
    resourceKey,
    status: "loading",
    data: null,
    error: null,
    lastVerifiedAt: null,
  });
  const verifiedByKeyRef = useRef(new Map<string, {
    data: T;
    verifiedAt: string;
  }>());
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let active = true;
    let retryIndex = 0;
    const controllers = new Set<AbortController>();
    const retryTimers = new Set<ReturnType<typeof setTimeout>>();

    if (demoMode) {
      return () => {
        active = false;
      };
    }

    if (cachedData) {
      verifiedByKeyRef.current.set(resourceKey, cachedData);
    }

    const request = (forceRefresh: boolean) => {
      if (!active) return;
      const controller = new AbortController();
      controllers.add(controller);
      void loadRef
        .current(controller.signal, forceRefresh)
        .then(({ data, verifiedAt }) => {
          if (!active || controller.signal.aborted) return;
          verifiedByKeyRef.current.set(resourceKey, { data, verifiedAt });
          retryIndex = 0;
          setState({
            resourceKey,
            status: "live",
            data,
            error: null,
            lastVerifiedAt: verifiedAt,
          });
        })
        .catch((error: unknown) => {
          if (
            !active ||
            (error instanceof Error && error.name === "AbortError")
          ) {
            return;
          }
          const marketError = toMarketError(error);
          const verified = verifiedByKeyRef.current.get(resourceKey);
          setState({
            resourceKey,
            status: verified ? "stale" : "unavailable",
            data: verified?.data ?? null,
            error: marketError,
            lastVerifiedAt: verified?.verifiedAt ?? null,
          });
          const delay = retryDelaysMs[
            Math.min(retryIndex, retryDelaysMs.length - 1)
          ];
          if (
            delay !== undefined &&
            isRetryableMarketError(marketError)
          ) {
            retryIndex += 1;
            const timer = setTimeout(() => {
              retryTimers.delete(timer);
              request(true);
            }, delay);
            retryTimers.add(timer);
          }
        })
        .finally(() => {
          controllers.delete(controller);
        });
    };

    request(true);
    return () => {
      active = false;
      controllers.forEach((controller) => controller.abort());
      retryTimers.forEach((timer) => clearTimeout(timer));
    };
  }, [
    cachedData,
    demoData,
    demoMode,
    refreshVersion,
    resourceKey,
    retryDelaysMs,
  ]);

  const refresh = useCallback(() => {
    if (!demoMode) setRefreshVersion((version) => version + 1);
  }, [demoMode]);

  if (demoMode) {
    return {
      status: "demo",
      data: demoData,
      error: null,
      lastVerifiedAt: null,
      refresh,
    };
  }
  if (state.resourceKey !== resourceKey || state.status === "demo") {
    if (cachedData) {
      return {
        status: "stale",
        data: cachedData.data,
        error: null,
        lastVerifiedAt: cachedData.verifiedAt,
        refresh,
      };
    }
    return {
      status: "loading",
      data: null,
      error: null,
      lastVerifiedAt: null,
      refresh,
    };
  }
  if (state.status === "loading" && cachedData) {
    return {
      status: "stale",
      data: cachedData.data,
      error: null,
      lastVerifiedAt: cachedData.verifiedAt,
      refresh,
    };
  }
  const { resourceKey: _resourceKey, ...visibleState } = state;
  return { ...visibleState, refresh };
}

export function useStockSnapshot(
  symbol: string,
  interval: CandleInterval,
  count: number,
): MarketDataState<LiveStockSnapshot | DemoChartSnapshot> {
  const { repository } = useMarketDataContext();
  const normalizedSymbol = symbol.trim().toUpperCase();
  const query = useMemo(
    () => ({ symbol: normalizedSymbol, interval, count }),
    [count, interval, normalizedSymbol],
  );
  const cachedData = useMemo(() => {
    const data = repository.peekStockSnapshot(query);
    return data ? { data, verifiedAt: data.source.asOf } : null;
  }, [query, repository]);
  return useLiveResource({
    resourceKey: `${normalizedSymbol}|${interval}|${count}`,
    cachedData,
    demoData: null,
    load: async (signal, forceRefresh) => {
      const data = await repository.getStockSnapshot(
        query,
        { signal, forceRefresh },
      );
      return { data, verifiedAt: data.source.asOf };
    },
  });
}

export function useMarketWatchlist(): MarketDataState<
  MarketWatchlist | DemoMarketWatchlist
> {
  const { demoWatchlist, repository } = useMarketDataContext();
  const cachedData = useMemo(() => {
    const data = repository.peekWatchlist();
    return data ? { data, verifiedAt: data.asOf } : null;
  }, [repository]);
  const demoData = useMemo<DemoMarketWatchlist>(
    () => ({
      source: "fixture",
      asOf: null,
      quotes: demoWatchlist,
    }),
    [demoWatchlist],
  );
  return useLiveResource<MarketWatchlist | DemoMarketWatchlist>({
    resourceKey: "watchlist",
    cachedData,
    demoData,
    load: async (signal, forceRefresh) => {
      const data = await repository.getWatchlist({ signal, forceRefresh });
      return { data, verifiedAt: data.asOf };
    },
  });
}

export function useMarketDataMode() {
  const { demoMode, development, setDemoMode } = useMarketDataContext();
  return { demoMode, demoAvailable: development, setDemoMode };
}
