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
  DecisionScore,
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
  decisionConcurrency: number;
};

type MarketDataProviderProps = PropsWithChildren<{
  repository?: MarketRepository;
  analysis?: AnalysisSource;
  development?: boolean;
  initialDemoMode?: boolean;
  demoWatchlist?: WatchlistQuote[];
  retryDelaysMs?: readonly number[];
  deviceToken?: string | null;
  decisionConcurrency?: number;
}>;

const defaultRetryDelaysMs = [1_000, 2_000, 4_000, 8_000, 30_000] as const;
/**
 * The analysis service answers one symbol per request, so a long watchlist is
 * a long queue. This is how many of those requests may be open at once.
 */
const defaultDecisionConcurrency = 4;
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
  decisionConcurrency = defaultDecisionConcurrency,
}: MarketDataProviderProps) {
  if (initialDemoMode && !development) {
    throw new Error("demo mode is developer-only");
  }
  if (!Number.isInteger(decisionConcurrency) || decisionConcurrency < 1) {
    // Zero workers would leave every row on "loading" forever, which reads as
    // a slow network rather than as the misconfiguration it is.
    throw new Error("decisionConcurrency must be a positive integer");
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
      decisionConcurrency,
    }),
    [
      decisionConcurrency,
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

export type AdviserDecisionState = {
  status: "idle" | "loading" | "live" | "unavailable";
  data: Decision | null;
  error: MarketDataError | null;
  request(): void;
};

/**
 * The only paid analysis path in the mobile app.
 *
 * It deliberately has no mount effect and no list variant: one tap asks for
 * one news interpretation for one symbol. Leaving the screen cancels it.
 */
export function useAdviserDecision(
  symbol: string,
  horizon: Horizon,
): AdviserDecisionState {
  const { analysis } = useMarketDataContext();
  const normalizedSymbol = symbol.trim().toUpperCase();
  const scope = `${normalizedSymbol}|${horizon}`;
  const requestRef = useRef<AbortController | null>(null);
  const [state, setState] = useState<{
    scope: string;
    status: AdviserDecisionState["status"];
    data: Decision | null;
    error: MarketDataError | null;
  }>({ scope, status: "idle", data: null, error: null });

  useEffect(() => () => {
    requestRef.current?.abort();
    requestRef.current = null;
  }, [scope]);

  const request = useCallback(() => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setState({ scope, status: "loading", data: null, error: null });
    void analysis
      .getDecision(normalizedSymbol, horizon, controller.signal, {
        adviser: "news",
      })
      .then((data) => {
        if (requestRef.current !== controller) return;
        requestRef.current = null;
        setState({ scope, status: "live", data, error: null });
      })
      .catch((error: unknown) => {
        if (
          requestRef.current !== controller ||
          (error instanceof Error && error.name === "AbortError")
        ) {
          return;
        }
        requestRef.current = null;
        setState({
          scope,
          status: "unavailable",
          data: null,
          error: toMarketError(error),
        });
      });
  }, [analysis, horizon, normalizedSymbol, scope]);

  if (state.scope !== scope) {
    return { status: "idle", data: null, error: null, request };
  }
  return { ...state, request };
}

export type WatchlistDecisionStatus =
  | "loading"
  | "scored"
  | "unscored"
  | "unavailable"
  | "demo";

export type WatchlistDecisionState = {
  status: WatchlistDecisionStatus;
  /** null whenever the chain answered without a score, or did not answer. */
  score: DecisionScore | null;
  error: MarketDataError | null;
  /** The chain's own words about what it could not see. */
  notes: string[];
};

const loadingDecision: WatchlistDecisionState = {
  status: "loading",
  score: null,
  error: null,
  notes: [],
};

/**
 * Demo mode has no decision counterpart on purpose: a fixture verdict beside a
 * fixture quote would be indistinguishable from a real one, so the row says it
 * has no score instead of inventing one.
 */
const demoDecision: WatchlistDecisionState = {
  status: "demo",
  score: null,
  error: null,
  notes: [],
};

const noDecisions: Record<string, WatchlistDecisionState> = {};

/**
 * Scores a list of symbols for a list screen.
 *
 * The service answers one symbol per request, so a 46-symbol watchlist is 46
 * requests: they run a few at a time, and each symbol keeps its own state so a
 * row can say "still asking", "the chain declined to score" or "the request
 * failed" rather than render an empty cell that reads as a score of nothing.
 */
export function useWatchlistDecisions(
  symbols: readonly string[],
  horizon: Horizon,
): Record<string, WatchlistDecisionState> {
  const { analysis, decisionConcurrency, demoMode } = useMarketDataContext();
  // A verdict belongs to one horizon, and never to demo data. Crossing either
  // boundary invalidates everything collected so far.
  const scope = `${demoMode ? "demo" : "live"}|${horizon}`;
  // The caller rebuilds this array on every render, so the joined symbols —
  // not the array identity — decide when the request set actually changed.
  const symbolsKey = [
    ...new Set(
      symbols
        .map((symbol) => symbol.trim().toUpperCase())
        .filter((symbol) => symbol !== ""),
    ),
  ].join(",");
  const [answers, setAnswers] = useState<{
    scope: string;
    bySymbol: Record<string, WatchlistDecisionState>;
  }>({ scope, bySymbol: noDecisions });
  const scopeRef = useRef(scope);
  const requestsRef = useRef(new Map<string, "pending" | "settled">());

  useEffect(() => {
    const requests = requestsRef.current;
    // Ticker symbols carry no comma, so the key splits back into exactly the
    // list that produced it.
    const targets = symbolsKey === "" ? [] : symbolsKey.split(",");
    if (scopeRef.current !== scope) {
      scopeRef.current = scope;
      requests.clear();
    }
    if (demoMode) return;

    const queue = targets.filter((symbol) => !requests.has(symbol));
    if (queue.length === 0) return;
    queue.forEach((symbol) => requests.set(symbol, "pending"));

    let cancelled = false;
    const controller = new AbortController();
    const settle = (symbol: string, entry: WatchlistDecisionState) => {
      requests.set(symbol, "settled");
      // Answers from an abandoned scope cannot arrive here: the effect that
      // asked for them was cancelled, so the scope is always the current one.
      setAnswers((current) =>
        current.scope === scope
          ? { scope, bySymbol: { ...current.bySymbol, [symbol]: entry } }
          : { scope, bySymbol: { [symbol]: entry } },
      );
    };

    const work = async (): Promise<void> => {
      while (!cancelled) {
        const symbol = queue.shift();
        if (symbol === undefined) return;
        try {
          const decision = await analysis.getDecision(
            symbol,
            horizon,
            controller.signal,
          );
          if (cancelled) return;
          settle(symbol, {
            status: decision.score === null ? "unscored" : "scored",
            score: decision.score,
            error: null,
            notes: decision.notes,
          });
        } catch (error) {
          if (
            cancelled ||
            (error instanceof Error && error.name === "AbortError")
          ) {
            return;
          }
          settle(symbol, {
            status: "unavailable",
            score: null,
            error: toMarketError(error),
            notes: [],
          });
        }
      }
    };

    const workers = Math.min(decisionConcurrency, queue.length);
    for (let worker = 0; worker < workers; worker += 1) {
      void work();
    }

    return () => {
      cancelled = true;
      controller.abort();
      // An aborted request produced no answer, so it must not be remembered as
      // asked; otherwise its row would sit on "loading" with nobody asking.
      requests.forEach((state, symbol) => {
        if (state === "pending") requests.delete(symbol);
      });
    };
  }, [analysis, decisionConcurrency, demoMode, horizon, scope, symbolsKey]);

  // A symbol without an answer yet is pending. That is derived here instead of
  // being written into state, so "loading" can never outlive the request that
  // justified it.
  return useMemo(() => {
    const answered = answers.scope === scope ? answers.bySymbol : noDecisions;
    const targets = symbolsKey === "" ? [] : symbolsKey.split(",");
    const bySymbol: Record<string, WatchlistDecisionState> = {};
    for (const symbol of targets) {
      bySymbol[symbol] =
        answered[symbol] ?? (demoMode ? demoDecision : loadingDecision);
    }
    return bySymbol;
  }, [answers, demoMode, scope, symbolsKey]);
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
