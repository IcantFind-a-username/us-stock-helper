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

import {
  getAnalysisRuntimeConfig,
  getMarketRuntimeConfig,
} from "@/config/runtimeConfig";
import {
  AnalysisRequestError,
  createAnalysisClient,
  DecisionValidationError,
  type AnalysisSource,
} from "@/data/analysisGateway";
import {
  createGatewayMarketRepository,
  isRetryableMarketError,
  MarketDataError,
  type MarketRepository,
  type MarketWatchlist,
} from "@/data/marketRepository";
import type {
  Decision,
  DemoChartSnapshot,
  Horizon,
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
  refreshing: boolean;
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
  analysis: AnalysisSource;
  demoMode: boolean;
  setDemoMode(value: boolean): void;
  development: boolean;
  demoWatchlist: WatchlistQuote[];
  retryDelaysMs: readonly number[];
};

type MarketDataProviderProps = PropsWithChildren<{
  repository?: MarketRepository;
  analysis?: AnalysisSource;
  development?: boolean;
  initialDemoMode?: boolean;
  demoWatchlist?: WatchlistQuote[];
  retryDelaysMs?: readonly number[];
  deviceToken?: string | null;
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

function unavailableAnalysis(error: unknown) {
  const analysisError = new MarketDataError(
    "configuration",
    error instanceof Error ? error.message : "invalid analysis configuration",
  );
  return {
    getDecision: async () => Promise.reject(analysisError),
  } satisfies AnalysisSource;
}

export function MarketDataProvider({
  children,
  repository,
  analysis,
  development = typeof __DEV__ !== "undefined" && __DEV__,
  initialDemoMode = false,
  demoWatchlist = [],
  retryDelaysMs = defaultRetryDelaysMs,
  deviceToken = null,
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
  const defaultAnalysis = useMemo(() => {
    if (analysis) return analysis;
    try {
      const config = getAnalysisRuntimeConfig();
      if (!config.apiUrl) {
        throw new Error("EXPO_PUBLIC_ANALYSIS_API_URL is not configured");
      }
      // The paired device token outranks any development token: once a device
      // has been bound to the server, that binding is the identity every later
      // request is answered against.
      const token = deviceToken ?? config.authorizationToken;
      return createAnalysisClient({
        baseUrl: config.apiUrl,
        ...(token ? { authorizationToken: token } : {}),
      });
    } catch (error) {
      return unavailableAnalysis(error);
    }
  }, [analysis, deviceToken]);
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
      analysis: defaultAnalysis,
      demoMode,
      setDemoMode,
      development,
      demoWatchlist,
      retryDelaysMs,
    }),
    [
      defaultAnalysis,
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
  if (error instanceof AnalysisRequestError) {
    return new MarketDataError(error.kind, error.message);
  }
  if (error instanceof DecisionValidationError) {
    return new MarketDataError("validation", error.message);
  }
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
  const [state, setState] = useState<
    Omit<MarketDataState<T>, "refresh"> & { resourceKey: string }
  >({
    resourceKey,
    status: "loading",
    refreshing: false,
    data: null,
    error: null,
    lastVerifiedAt: null,
  });
  const verifiedByKeyRef = useRef(new Map<string, {
    data: T;
    verifiedAt: string;
  }>());
  const inFlightRef = useRef(false);
  const requestRef = useRef<((showRefreshing: boolean) => boolean) | null>(
    null,
  );
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });
  useEffect(() => {
    inFlightRef.current = false;
  }, [demoMode, resourceKey]);

  useEffect(() => {
    let active = true;
    let retryIndex = 0;
    const controllers = new Set<AbortController>();
    const retryTimers = new Set<ReturnType<typeof setTimeout>>();
    const clearRetryTimers = () => {
      retryTimers.forEach((timer) => clearTimeout(timer));
      retryTimers.clear();
    };

    if (demoMode) {
      return () => {
        active = false;
      };
    }

    if (cachedData) {
      verifiedByKeyRef.current.set(resourceKey, cachedData);
    }

    const request = (showRefreshing: boolean) => {
      if (!active || inFlightRef.current) return false;
      clearRetryTimers();
      inFlightRef.current = true;
      if (showRefreshing) {
        const verified = verifiedByKeyRef.current.get(resourceKey);
        setState((current) => ({
          resourceKey,
          status: verified
            ? current.resourceKey === resourceKey &&
              current.status === "live"
              ? "live"
              : "stale"
            : "loading",
          refreshing: true,
          data: verified?.data ?? null,
          error: verified ? current.error : null,
          lastVerifiedAt: verified?.verifiedAt ?? null,
        }));
      }
      const controller = new AbortController();
      controllers.add(controller);
      void loadRef
        .current(controller.signal, true)
        .then(({ data, verifiedAt }) => {
          if (!active || controller.signal.aborted) return;
          verifiedByKeyRef.current.set(resourceKey, { data, verifiedAt });
          clearRetryTimers();
          retryIndex = 0;
          setState({
            resourceKey,
            status: "live",
            refreshing: false,
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
            refreshing: false,
            data: verified?.data ?? null,
            error: marketError,
            lastVerifiedAt: verified?.verifiedAt ?? null,
          });
          clearRetryTimers();
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
          if (active) {
            inFlightRef.current = false;
          }
        });
      return true;
    };

    requestRef.current = request;
    request(false);
    return () => {
      active = false;
      if (requestRef.current === request) {
        requestRef.current = null;
      }
      inFlightRef.current = false;
      controllers.forEach((controller) => controller.abort());
      clearRetryTimers();
    };
  }, [
    cachedData,
    demoData,
    demoMode,
    resourceKey,
    retryDelaysMs,
  ]);

  const refresh = useCallback(() => {
    if (demoMode) return;
    requestRef.current?.(true);
  }, [demoMode]);

  if (demoMode) {
    return {
      status: "demo",
      refreshing: false,
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
        refreshing: false,
        data: cachedData.data,
        error: null,
        lastVerifiedAt: cachedData.verifiedAt,
        refresh,
      };
    }
    return {
      status: "loading",
      refreshing: false,
      data: null,
      error: null,
      lastVerifiedAt: null,
      refresh,
    };
  }
  if (state.status === "loading" && cachedData) {
    return {
      status: "stale",
      refreshing: state.refreshing,
      data: cachedData.data,
      error: state.error,
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

/**
 * A decision is never cached across mounts and never has a demo counterpart:
 * a stored conclusion about a live market goes stale in a way the reader
 * cannot see, and a fixture conclusion would be indistinguishable from a real
 * one on the page.
 */
export function useDecision(
  symbol: string,
  horizon: Horizon,
): MarketDataState<Decision> {
  const { analysis } = useMarketDataContext();
  const normalizedSymbol = symbol.trim().toUpperCase();
  return useLiveResource<Decision>({
    resourceKey: `${normalizedSymbol}|${horizon}`,
    cachedData: null,
    demoData: null,
    load: async (signal) => {
      const data = await analysis.getDecision(normalizedSymbol, horizon, signal);
      return { data, verifiedAt: data.decisionCutoff };
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
