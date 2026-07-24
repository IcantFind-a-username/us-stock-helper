import type { Candle, Direction, WatchlistQuote } from "@/domain/models";

const defaultMaxAgeMs = 30_000;
const allowedSessions = new Set(["healthy"]);

type DecodeOptions = {
  now?: Date;
  maxAgeMs?: number;
};

type GatewayEnvelope = {
  asOf: Date;
  availableAt: Date;
  items: unknown[];
};

export type MarketDataSource = "moomoo" | "fixture";

export type WatchlistResult = {
  source: MarketDataSource;
  asOf: string | null;
  quotes: WatchlistQuote[];
  fallbackReason?: "gateway-unavailable" | "gateway-invalid";
};

export type CandleResult = {
  source: "moomoo";
  symbol: string;
  interval: string;
  asOf: string;
  candles: Candle[];
};

export type CandleInterval = "1m" | "5m" | "15m" | "30m" | "60m" | "day" | "week";

export class GatewayValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GatewayValidationError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (typeof value !== "string" || value.trim() === "") {
    throw new GatewayValidationError(`${key} must be a non-empty string`);
  }
  return value;
}

function requireFiniteNumber(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new GatewayValidationError(`${key} must be a finite number`);
  }
  return value;
}

function parseTimestamp(value: string, label: string) {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || !/[zZ]|[+-]\d\d:\d\d$/.test(value)) {
    throw new GatewayValidationError(`${label} must be an ISO timestamp with timezone`);
  }
  return parsed;
}

function decodeEnvelope(value: unknown, options: DecodeOptions = {}): GatewayEnvelope {
  if (!isRecord(value)) throw new GatewayValidationError("response must be an object");
  if (value.schemaVersion !== "1") {
    throw new GatewayValidationError("unsupported schemaVersion");
  }
  if (value.source !== "moomoo") {
    throw new GatewayValidationError("live responses must identify source as moomoo");
  }
  if (typeof value.session !== "string" || !allowedSessions.has(value.session)) {
    throw new GatewayValidationError("moomoo session is not healthy");
  }
  if (!Array.isArray(value.items)) {
    throw new GatewayValidationError("items must be an array");
  }

  const now = options.now ?? new Date();
  const maxAgeMs = options.maxAgeMs ?? defaultMaxAgeMs;
  const asOf = parseTimestamp(requireString(value, "asOf"), "asOf");
  const availableAt = parseTimestamp(
    requireString(value, "availableAt"),
    "availableAt",
  );
  const futureToleranceMs = 1_000;

  if (availableAt.getTime() < asOf.getTime()) {
    throw new GatewayValidationError("availableAt cannot precede asOf");
  }
  if (availableAt.getTime() > now.getTime() + futureToleranceMs) {
    throw new GatewayValidationError("response is not yet available at this decision time");
  }
  if (now.getTime() - availableAt.getTime() > maxAgeMs) {
    throw new GatewayValidationError("response is stale");
  }

  return { asOf, availableAt, items: value.items };
}

function normalizeUsSymbol(code: string) {
  const normalized = code.trim().toUpperCase();
  const match = /^(?:US\.)?([A-Z][A-Z0-9.-]{0,9})$/.exec(normalized);
  if (!match?.[1]) throw new GatewayValidationError(`unsupported US code: ${code}`);
  return match[1];
}

function directionFor(changePercent: number): Direction {
  if (changePercent > 0) return "bullish";
  if (changePercent < 0) return "bearish";
  return "neutral";
}

export function decodeWatchlistEnvelope(
  value: unknown,
  options: DecodeOptions = {},
): WatchlistResult {
  const envelope = decodeEnvelope(value, options);
  const quotes = envelope.items.map((item) => {
    if (!isRecord(item)) throw new GatewayValidationError("watchlist item must be an object");
    const itemAvailableAt = parseTimestamp(
      requireString(item, "availableAt"),
      "item.availableAt",
    );
    if (itemAvailableAt.getTime() > envelope.asOf.getTime()) {
      throw new GatewayValidationError("watchlist item arrived after snapshot cutoff");
    }
    const price = requireFiniteNumber(item, "price");
    const changePercent = requireFiniteNumber(item, "changePercent");
    if (price <= 0) throw new GatewayValidationError("price must be positive");

    return {
      symbol: normalizeUsSymbol(requireString(item, "code")),
      price,
      changePercent,
      direction: directionFor(changePercent),
      summary: "实时只读",
    } satisfies WatchlistQuote;
  });

  return {
    source: "moomoo",
    asOf: envelope.asOf.toISOString(),
    quotes,
  };
}

export function decodeCandleEnvelope(
  value: unknown,
  options: DecodeOptions = {},
): CandleResult {
  if (!isRecord(value)) throw new GatewayValidationError("response must be an object");
  const envelope = decodeEnvelope(value, options);
  const symbol = normalizeUsSymbol(requireString(value, "symbol"));
  const interval = requireString(value, "interval");
  let previousTimestamp = Number.NEGATIVE_INFINITY;

  const candles = envelope.items.map((item) => {
    if (!isRecord(item)) throw new GatewayValidationError("candle item must be an object");
    if (item.complete !== true) {
      throw new GatewayValidationError("only completed candles may enter the app");
    }
    const timestamp = parseTimestamp(requireString(item, "timestamp"), "candle.timestamp");
    const availableAt = parseTimestamp(
      requireString(item, "availableAt"),
      "candle.availableAt",
    );
    if (timestamp.getTime() > availableAt.getTime()) {
      throw new GatewayValidationError("candle cannot be available before bar close");
    }
    if (availableAt.getTime() > envelope.asOf.getTime()) {
      throw new GatewayValidationError("candle arrived after snapshot cutoff");
    }
    if (timestamp.getTime() <= previousTimestamp) {
      throw new GatewayValidationError("candles must be strictly ordered");
    }
    previousTimestamp = timestamp.getTime();

    const open = requireFiniteNumber(item, "open");
    const high = requireFiniteNumber(item, "high");
    const low = requireFiniteNumber(item, "low");
    const close = requireFiniteNumber(item, "close");
    const volume = requireFiniteNumber(item, "volume");
    if (
      Math.min(open, high, low, close) <= 0 ||
      volume < 0 ||
      high < Math.max(open, close) ||
      low > Math.min(open, close) ||
      high < low
    ) {
      throw new GatewayValidationError("invalid OHLCV candle");
    }

    return {
      timestamp: timestamp.toISOString(),
      availableAt: availableAt.toISOString(),
      complete: true,
      open,
      high,
      low,
      close,
      volume,
    } satisfies Candle;
  });

  return {
    source: "moomoo",
    symbol,
    interval,
    asOf: envelope.asOf.toISOString(),
    candles,
  };
}

type MarketGatewayClientOptions = {
  baseUrl: string;
  authorizationToken?: string;
  fetchImpl?: typeof fetch;
  now?: () => Date;
  maxAgeMs?: number;
  timeoutMs?: number;
};

export function createMarketGatewayClient({
  baseUrl,
  authorizationToken,
  fetchImpl = fetch,
  now = () => new Date(),
  maxAgeMs = defaultMaxAgeMs,
  timeoutMs = 4_000,
}: MarketGatewayClientOptions) {
  const normalizedBaseUrl = baseUrl.replace(/\/+$/, "");
  let parsedBaseUrl: URL;
  try {
    parsedBaseUrl = new URL(normalizedBaseUrl);
  } catch {
    throw new GatewayValidationError("gateway baseUrl is invalid");
  }
  if (
    !["http:", "https:"].includes(parsedBaseUrl.protocol) ||
    parsedBaseUrl.username !== "" ||
    parsedBaseUrl.password !== "" ||
    (parsedBaseUrl.pathname !== "" && parsedBaseUrl.pathname !== "/") ||
    parsedBaseUrl.search !== "" ||
    parsedBaseUrl.hash !== ""
  ) {
    throw new GatewayValidationError(
      "gateway baseUrl must be a credential-free HTTP(S) origin",
    );
  }
  const isLoopback = new Set(["127.0.0.1", "localhost", "::1"]).has(
    parsedBaseUrl.hostname,
  );
  if (!isLoopback && (!authorizationToken || authorizationToken.length < 16)) {
    throw new GatewayValidationError(
      "a 16-character or longer ephemeral token is required for a LAN gateway",
    );
  }

  async function fetchJson(path: string) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetchImpl(`${normalizedBaseUrl}${path}`, {
        method: "GET",
        headers: {
          Accept: "application/json",
          ...(authorizationToken
            ? { Authorization: `Bearer ${authorizationToken}` }
            : {}),
        },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`gateway returned HTTP ${response.status}`);
      return (await response.json()) as unknown;
    } finally {
      clearTimeout(timeout);
    }
  }

  return {
    async getWatchlistOrFallback(
      fallbackQuotes: WatchlistQuote[],
    ): Promise<WatchlistResult> {
      try {
        const payload = await fetchJson("/watchlist");
        return decodeWatchlistEnvelope(payload, { maxAgeMs, now: now() });
      } catch (error) {
        return {
          source: "fixture",
          asOf: null,
          quotes: fallbackQuotes,
          fallbackReason:
            error instanceof GatewayValidationError
              ? "gateway-invalid"
              : "gateway-unavailable",
        };
      }
    },
    async getCandles(
      symbol: string,
      interval: CandleInterval,
      count = 200,
    ): Promise<CandleResult> {
      const normalizedSymbol = normalizeUsSymbol(symbol);
      if (!Number.isInteger(count) || count < 1 || count > 1_000) {
        throw new GatewayValidationError(
          "candle count must be an integer between 1 and 1000",
        );
      }
      const query = new URLSearchParams({
        symbol: normalizedSymbol,
        interval,
        count: String(count),
      });
      const payload = await fetchJson(`/candles?${query.toString()}`);
      const result = decodeCandleEnvelope(payload, {
        maxAgeMs,
        now: now(),
      });
      if (
        result.symbol !== normalizedSymbol ||
        result.interval !== interval
      ) {
        throw new GatewayValidationError(
          "candle response does not match the requested series",
        );
      }
      return result;
    },
  };
}
