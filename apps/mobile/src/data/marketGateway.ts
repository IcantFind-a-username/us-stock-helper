import type {
  Candle,
  ChartIndicatorSeries,
  ChartMacdSeries,
  DelayedInstitutionalHolding,
  Direction,
  LiveIndicatorValue,
  LiveMacdIndicator,
  LiveQuote,
  LiveStockSnapshot,
  CompletedTdSetup,
  LiveVolatilityIndicator,
  MagicNineSnapshot,
  MagicNineSeriesPoint,
  NormalizedCapitalFlowPoint,
  ParticipationBar,
  PriceAdjustment,
  SnapshotAvailability,
  SnapshotQuality,
  SnapshotSection,
  SnapshotSectionName,
  StockSnapshotSections,
  LiveTechnicalIndicators,
  SnapshotProvenance,
  WatchlistQuote,
} from "@/domain/models";

const defaultMaxAgeMs = 30_000;
const allowedSessions = new Set(["healthy"]);

type DecodeOptions = {
  now?: Date;
  maxAgeMs?: number;
  requestedCount?: number;
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

export type LiveWatchlistResult = {
  source: "moomoo";
  asOf: string;
  quotes: WatchlistQuote[];
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

/**
 * Mirrors the gateway's own error vocabulary rather than compressing it.
 *
 * These names are the ones the screen turns into sentences, so two codes share
 * a name only where the reader's next move is the same. `malformed` in
 * particular means one specific thing — the gateway judged the provider's data
 * unusable — and no longer doubles as "and also anything else we failed to
 * classify", which is what made it unexplainable.
 */
export type GatewayRequestErrorKind =
  | "auth-required"
  | "client-not-allowed"
  | "client-update-required"
  | "contract"
  | "invalid-request"
  | "login-required"
  | "malformed"
  | "offline"
  | "permission"
  | "provider-error"
  | "rate-limited"
  | "route-unsupported"
  | "sdk-unavailable"
  | "stale"
  | "timeout"
  | "unspecified"
  | "unsupported"
  | "validation";

export class GatewayRequestError extends GatewayValidationError {
  constructor(
    public readonly kind: GatewayRequestErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "GatewayRequestError";
  }
}

/**
 * The payload declares a schema version we implement but omits a field that
 * version requires — an older gateway, not corrupt data. Kept apart from
 * GatewayValidationError so the app can say "update the gateway" rather than
 * "the data is broken".
 */
export class GatewayContractError extends GatewayValidationError {
  constructor(field: string) {
    super(`snapshot is missing ${field}; the gateway may be out of date`);
    this.name = "GatewayContractError";
  }
}

export class GatewayClientUpdateRequiredError extends GatewayValidationError {
  constructor(schemaVersion: string) {
    super(`snapshot schemaVersion ${schemaVersion} requires a newer client`);
    this.name = "GatewayClientUpdateRequiredError";
  }
}

export class GatewaySnapshotUnavailableError extends GatewayValidationError {
  constructor(
    public readonly kind: GatewayRequestErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "GatewaySnapshotUnavailableError";
  }
}

class GatewayHttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`gateway returned HTTP ${status}`);
    this.name = "GatewayHttpError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireContractField(record: Record<string, unknown>, key: string) {
  if (record[key] === undefined) throw new GatewayContractError(key);
  return record[key];
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

function decodeEnvelope(value: unknown, _options: DecodeOptions = {}): GatewayEnvelope {
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

  const asOf = parseTimestamp(requireString(value, "asOf"), "asOf");
  const availableAt = parseTimestamp(
    requireString(value, "availableAt"),
    "availableAt",
  );

  if (availableAt.getTime() < asOf.getTime()) {
    throw new GatewayValidationError("availableAt cannot precede asOf");
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
): LiveWatchlistResult {
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

const snapshotStatuses = new Set(["live", "delayed", "stale", "unavailable", "demo"]);

function requireNullableFiniteNumber(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (value !== null && (typeof value !== "number" || !Number.isFinite(value))) {
    throw new GatewayValidationError(`${key} must be a finite number or null`);
  }
  return value;
}

function requireStatus(record: Record<string, unknown>, key: string) {
  const status = requireString(record, key);
  if (!snapshotStatuses.has(status)) {
    throw new GatewayValidationError(`${key} has an unsupported data status`);
  }
  return status as "live" | "delayed" | "stale" | "unavailable" | "demo";
}

function requireSnapshotMetadata(
  record: Record<string, unknown>,
  label: string,
  cutoff: Date,
) {
  const source = requireString(record, "source");
  const asOf = parseTimestamp(requireString(record, "asOf"), `${label}.asOf`);
  const availableAt = parseTimestamp(
    requireString(record, "availableAt"),
    `${label}.availableAt`,
  );
  if (asOf.getTime() > cutoff.getTime() || availableAt.getTime() > cutoff.getTime()) {
    throw new GatewayValidationError(`${label} is after snapshot decision cutoff`);
  }
  return {
    source,
    asOf: asOf.toISOString(),
    availableAt: availableAt.toISOString(),
  };
}

function rejectInstitutionalIdentity(record: Record<string, unknown>, label: string) {
  if (record.institutionalIdentity === true) {
    throw new GatewayValidationError(`${label} must not claim institutional identity`);
  }
}

function requireExpectedMethod<T extends string>(
  record: Record<string, unknown>,
  expected: T,
  label: string,
): T {
  if (requireString(record, "methodVersion") !== expected) {
    throw new GatewayValidationError(`${label} uses an unsupported method version`);
  }
  return expected;
}

/**
 * One kind per code the gateway can name, matching its ErrorCode enum.
 *
 * The former table folded a rate limit, a missing SDK and an offline OpenD
 * into "offline", and everything it did not list into "malformed" — so a
 * request rejected for its arguments and a provider whose candles broke
 * point-in-time ordering reached the screen as the same word.
 */
const kindByGatewayCode: Record<string, GatewayRequestErrorKind> = {
  INVALID_ARGUMENT: "invalid-request",
  AUTH_REQUIRED: "auth-required",
  CLIENT_NOT_ALLOWED: "client-not-allowed",
  ORIGIN_NOT_ALLOWED: "client-not-allowed",
  PERMISSION_DENIED: "permission",
  // A path and a method the gateway will not serve are one fact to the reader:
  // the service on the other end does not offer what this build asks for.
  PATH_NOT_ALLOWED: "route-unsupported",
  METHOD_NOT_ALLOWED: "route-unsupported",
  QUOTA_EXCEEDED: "rate-limited",
  UNSUPPORTED_CAPABILITY: "unsupported",
  MALFORMED_PROVIDER_DATA: "malformed",
  PROVIDER_ERROR: "provider-error",
  SDK_UNAVAILABLE: "sdk-unavailable",
  OPEND_OFFLINE: "offline",
  LOGIN_REQUIRED: "login-required",
  STALE_DATA: "stale",
};

function decodeSnapshotError(value: Record<string, unknown>): GatewayRequestError | null {
  if (value.sourceStatus === "live") return null;
  const error = isRecord(value.error) ? value.error : undefined;
  const code = error && typeof error.code === "string" ? error.code : null;
  if (code === null) {
    // A refusal that names no code used to be reported as malformed provider
    // data. That put a point-in-time explanation on screen that the gateway
    // never made, so the app states the absence instead of filling it in.
    return new GatewayRequestError(
      "unspecified",
      "gateway snapshot is unavailable and named no reason",
    );
  }
  return new GatewayRequestError(
    kindByGatewayCode[code] ?? "unspecified",
    `gateway snapshot is unavailable: ${code}`,
  );
}

function decodeVolatility(
  value: unknown,
  cutoff: Date,
  candleCount: number,
): LiveVolatilityIndicator {
  const base = decodeIndicatorValue(
    value,
    "volatility",
    "close-to-close-realized-v1",
    cutoff,
    candleCount,
  );
  const record = value as Record<string, unknown>;
  const sampleSize = requireFiniteNumber(record, "sampleSize");
  if (!Number.isInteger(sampleSize) || sampleSize < 0) {
    throw new GatewayValidationError("volatility sampleSize must be a non-negative integer");
  }
  const missingReason = record.missingReason;
  if (missingReason !== null && (typeof missingReason !== "string" || missingReason.trim() === "")) {
    throw new GatewayValidationError("volatility missingReason must be a non-empty string or null");
  }
  if (base.qualityStatus === "live") {
    if (base.value === null || base.value <= 0) {
      throw new GatewayValidationError("a live volatility must be positive");
    }
    if (missingReason !== null) {
      throw new GatewayValidationError("a live volatility cannot carry a missing reason");
    }
  } else if (base.value !== null || missingReason === null) {
    throw new GatewayValidationError("an unavailable volatility needs a null value and a reason");
  }
  return { ...base, sampleSize, missingReason };
}

function decodeCompletedTdSetup(
  value: unknown,
  candleCount: number,
): CompletedTdSetup | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) {
    throw new GatewayValidationError("magic nine lastCompleted must be an object or null");
  }
  const direction = value.direction;
  if (direction !== "bullish" && direction !== "bearish") {
    throw new GatewayValidationError("magic nine lastCompleted direction is unsupported");
  }
  const confirmedAtIndex = value.confirmedAtIndex;
  if (
    typeof confirmedAtIndex !== "number" ||
    !Number.isInteger(confirmedAtIndex) ||
    confirmedAtIndex < 0 ||
    confirmedAtIndex >= candleCount
  ) {
    throw new GatewayValidationError("magic nine lastCompleted index is outside the candle series");
  }
  const barsSince = value.barsSince;
  if (
    typeof barsSince !== "number" ||
    !Number.isInteger(barsSince) ||
    barsSince !== candleCount - 1 - confirmedAtIndex
  ) {
    throw new GatewayValidationError("magic nine lastCompleted barsSince contradicts its index");
  }
  if (typeof value.perfected !== "boolean") {
    throw new GatewayValidationError("magic nine lastCompleted perfected must be boolean");
  }
  return { direction, confirmedAtIndex, perfected: value.perfected, barsSince };
}

function decodeMagicNineSeries(
  value: unknown,
  candleCount: number,
): (MagicNineSeriesPoint | null)[] | null {
  // The first schema-2 gateway published only the current setup summary. The
  // aligned series was added later without changing schemaVersion, so an older
  // process may legitimately omit it during a rolling local upgrade. Preserve
  // the summary/badge fallback instead of discarding the entire stock detail.
  if (value === undefined) return null;
  if (!Array.isArray(value) || value.length !== candleCount) {
    throw new GatewayValidationError(
      "magic nine series must carry one value per completed candle",
    );
  }
  return value.map((item, index) => {
    if (item === null) return null;
    if (!isRecord(item)) {
      throw new GatewayValidationError(
        `magic nine series item ${index} must be an object or null`,
      );
    }
    if (item.direction !== "bullish" && item.direction !== "bearish") {
      throw new GatewayValidationError(
        `magic nine series item ${index} has an unknown direction`,
      );
    }
    const count = item.count;
    if (
      typeof count !== "number" ||
      !Number.isInteger(count) ||
      count < 1 ||
      count > 9
    ) {
      throw new GatewayValidationError(
        `magic nine series item ${index} has an invalid count`,
      );
    }
    return { direction: item.direction, count } as MagicNineSeriesPoint;
  });
}

/**
 * Reads a per-candle series, or states that the gateway published none.
 *
 * The contract is deliberately narrow: one entry per completed candle, in the
 * same order, from the same method version as the latest value it accompanies.
 * A series that does not line up cannot be drawn on these candles, and shifting
 * it by a bar would move an indicator onto a price it never described — so a
 * misaligned series is rejected rather than trimmed to fit. An absent series is
 * not an error; the app says the line is unavailable.
 */
function decodeSeriesValues(
  record: Record<string, unknown>,
  key: string,
  label: string,
  candleCount: number,
): (number | null)[] {
  const values = record[key];
  if (!Array.isArray(values) || values.length !== candleCount) {
    throw new GatewayValidationError(
      `${label} series ${key} must carry one value per completed candle`,
    );
  }
  return values.map((entry) => {
    if (entry === null) return null;
    if (typeof entry !== "number" || !Number.isFinite(entry)) {
      throw new GatewayValidationError(
        `${label} series ${key} must hold finite numbers or null`,
      );
    }
    return entry;
  });
}

function decodeSeriesMetadata(
  value: unknown,
  label: string,
  methodVersion: string,
  cutoff: Date,
) {
  if (!isRecord(value)) {
    throw new GatewayValidationError(`${label} series must be an object`);
  }
  const metadata = requireSnapshotMetadata(value, `${label} series`, cutoff);
  if (metadata.source !== "analysis-core") {
    throw new GatewayValidationError(`${label} series must identify analysis-core`);
  }
  if (requireString(value, "methodVersion") !== methodVersion) {
    throw new GatewayValidationError(
      `${label} series must use the same method version as its latest value`,
    );
  }
  const qualityStatus = requireStatus(value, "qualityStatus");
  if (qualityStatus !== "live" && qualityStatus !== "unavailable") {
    throw new GatewayValidationError(`${label} series has an unsupported quality status`);
  }
  return { record: value, metadata, qualityStatus };
}

/**
 * The gateway publishes the values as a bare array beside the indicator's own
 * source, timestamps, method version and quality. The series carries no
 * provenance of its own because it has none to carry — it is the same
 * measurement at every bar — so requiring a nested envelope only invented a
 * second copy that could disagree with the first.
 */
function decodeIndicatorSeries(
  value: unknown,
  label: string,
  parent: { asOf: string; availableAt: string },
  methodVersion: string,
  qualityStatus: string,
  candleCount: number,
): ChartIndicatorSeries | null {
  if (value === undefined || value === null) return null;
  if (qualityStatus !== "live") return null;
  const values = decodeSeriesArray(value, label, candleCount);
  return {
    asOf: parent.asOf,
    availableAt: parent.availableAt,
    source: "analysis-core",
    values,
    methodVersion,
    qualityStatus: "live",
  };
}

function decodeSeriesArray(
  value: unknown,
  label: string,
  candleCount: number,
): (number | null)[] {
  if (!Array.isArray(value)) {
    throw new GatewayValidationError(`${label}.series must be an array`);
  }
  if (value.length !== candleCount) {
    // A series one bar out of step draws every point against the wrong candle,
    // which looks like a plausible chart rather than a broken one.
    throw new GatewayValidationError(
      `${label}.series does not line up with the completed candles`,
    );
  }
  return value.map((entry) => {
    if (entry === null) return null;
    if (typeof entry !== "number" || !Number.isFinite(entry)) {
      throw new GatewayValidationError(`${label}.series holds a non-numeric value`);
    }
    return entry;
  });
}

function decodeMacdSeries(
  value: unknown,
  parent: { asOf: string; availableAt: string },
  qualityStatus: string,
  candleCount: number,
): ChartMacdSeries | null {
  if (value === undefined || value === null) return null;
  if (qualityStatus !== "live") return null;
  const label = "indicators.macd";
  if (!isRecord(value)) {
    throw new GatewayValidationError(`${label}.series must be an object`);
  }
  return {
    asOf: parent.asOf,
    availableAt: parent.availableAt,
    source: "analysis-core",
    line: decodeSeriesArray(value.line, `${label}.series.line`, candleCount),
    signal: decodeSeriesArray(value.signal, `${label}.series.signal`, candleCount),
    histogram: decodeSeriesArray(
      value.histogram,
      `${label}.series.histogram`,
      candleCount,
    ),
    methodVersion: "macd-12-26-9-v1",
    qualityStatus: "live",
  };
}

function decodeIndicatorValue(
  value: unknown,
  key: "ma5" | "rsi" | "volatility",
  methodVersion: string,
  cutoff: Date,
  candleCount: number,
): LiveIndicatorValue {
  if (!isRecord(value)) throw new GatewayValidationError(`indicators.${key} must be an object`);
  const metadata = requireSnapshotMetadata(value, `indicators.${key}`, cutoff);
  if (metadata.source !== "analysis-core") {
    throw new GatewayValidationError(`indicators.${key} must identify analysis-core`);
  }
  requireExpectedMethod(value, methodVersion, `indicators.${key}`);
  const qualityStatus = requireStatus(value, "qualityStatus");
  if (qualityStatus !== "live" && qualityStatus !== "unavailable") {
    throw new GatewayValidationError(`indicators.${key} has an unsupported quality status`);
  }
  const numericValue = requireNullableFiniteNumber(value, "value");
  if ((qualityStatus === "live") !== (numericValue !== null)) {
    throw new GatewayValidationError(`indicators.${key} quality status does not match its value`);
  }
  return {
    ...metadata,
    source: "analysis-core",
    value: numericValue,
    series: decodeIndicatorSeries(
      value.series,
      `indicators.${key}`,
      metadata,
      methodVersion,
      qualityStatus,
      candleCount,
    ),
    methodVersion,
    qualityStatus,
  };
}

const snapshotV3SectionNames: SnapshotSectionName[] = [
  "quote",
  "candles",
  "technical",
  "currentSessionFlow",
  "holdings",
  "fundamentals",
  "marketContext",
  "news",
  "forecastDecision",
];

const requestedSnapshotV3Sections: SnapshotSectionName[] = [
  "quote",
  "candles",
  "technical",
  "currentSessionFlow",
  "holdings",
];

const snapshotAvailabilities = new Set<SnapshotAvailability>([
  "live",
  "delayed",
  "stale",
  "unavailable",
]);
const snapshotQualities = new Set<SnapshotQuality>([
  "validated",
  "partial",
  "anomalous",
  "invalid",
]);

function nullableStringField(
  record: Record<string, unknown>,
  key: string,
  label: string,
) {
  const value = requireContractField(record, key);
  if (value === null) return null;
  if (typeof value !== "string" || value.trim() === "") {
    throw new GatewayValidationError(`${label}.${key} must be a string or null`);
  }
  return value;
}

function nullableSectionTimestamp(
  record: Record<string, unknown>,
  key: string,
  label: string,
  cutoff: Date,
) {
  const value = nullableStringField(record, key, label);
  if (value === null) return null;
  const timestamp = parseTimestamp(value, `${label}.${key}`);
  if (timestamp.getTime() > cutoff.getTime()) {
    throw new GatewayValidationError(`${label}.${key} is after decisionCutoff`);
  }
  return timestamp;
}

function decodeSnapshotV3SectionEnvelope(
  value: unknown,
  name: SnapshotSectionName,
  cutoff: Date,
): SnapshotSection<unknown> {
  if (!isRecord(value)) {
    throw new GatewayValidationError(`sections.${name} must be an object`);
  }
  const label = `sections.${name}`;
  const availabilityStatus = requireString(value, "availabilityStatus");
  if (!snapshotAvailabilities.has(availabilityStatus as SnapshotAvailability)) {
    throw new GatewayValidationError(`${label}.availabilityStatus is unsupported`);
  }
  const qualityStatus = requireString(value, "qualityStatus");
  if (!snapshotQualities.has(qualityStatus as SnapshotQuality)) {
    throw new GatewayValidationError(`${label}.qualityStatus is unsupported`);
  }
  const source = nullableStringField(value, "source", label);
  const asOfValue = nullableSectionTimestamp(value, "asOf", label, cutoff);
  const availableAtValue = nullableSectionTimestamp(
    value,
    "availableAt",
    label,
    cutoff,
  );
  const receivedAtValue = nullableSectionTimestamp(
    value,
    "receivedAt",
    label,
    cutoff,
  );
  if (
    asOfValue &&
    availableAtValue &&
    asOfValue.getTime() > availableAtValue.getTime()
  ) {
    throw new GatewayValidationError(`${label}.asOf follows availableAt`);
  }
  if (
    availableAtValue &&
    receivedAtValue &&
    availableAtValue.getTime() > receivedAtValue.getTime()
  ) {
    throw new GatewayValidationError(`${label}.availableAt follows receivedAt`);
  }

  const data = requireContractField(value, "data");
  const errorCode = nullableStringField(value, "errorCode", label);
  const reason = nullableStringField(value, "reason", label);
  const warningsValue = requireContractField(value, "warnings");
  if (
    !Array.isArray(warningsValue) ||
    !warningsValue.every(
      (warning) => typeof warning === "string" && warning.trim() !== "",
    )
  ) {
    throw new GatewayValidationError(`${label}.warnings must be strings`);
  }
  const anomaliesValue = requireContractField(value, "anomalies");
  if (!Array.isArray(anomaliesValue)) {
    throw new GatewayValidationError(`${label}.anomalies must be an array`);
  }
  const anomalies = anomaliesValue.map((anomaly, index) => {
    if (!isRecord(anomaly)) {
      throw new GatewayValidationError(`${label}.anomalies[${index}] must be an object`);
    }
    const code = requireString(anomaly, "code");
    const anomalyReason = requireString(anomaly, "reason");
    const rowIndex = anomaly.rowIndex;
    if (
      rowIndex !== undefined &&
      (typeof rowIndex !== "number" ||
        !Number.isInteger(rowIndex) ||
        rowIndex < 0)
    ) {
      throw new GatewayValidationError(
        `${label}.anomalies[${index}].rowIndex is invalid`,
      );
    }
    return {
      code,
      reason: anomalyReason,
      ...(rowIndex === undefined ? {} : { rowIndex }),
    };
  });
  const methodVersion = requireString(value, "methodVersion");
  const availability = availabilityStatus as SnapshotAvailability;
  const quality = qualityStatus as SnapshotQuality;
  const emptyArray = Array.isArray(data) && data.length === 0;

  if (availability === "unavailable") {
    if (
      quality !== "invalid" ||
      (data !== null && !emptyArray) ||
      errorCode === null ||
      reason === null
    ) {
      throw new GatewayValidationError(
        `${label} unavailable status contradicts its envelope`,
      );
    }
  } else if (
    quality === "invalid" ||
    data === null ||
    source === null ||
    asOfValue === null ||
    availableAtValue === null ||
    receivedAtValue === null ||
    errorCode !== null ||
    reason !== null
  ) {
    throw new GatewayValidationError(
      `${label} available status contradicts its envelope`,
    );
  }

  return {
    availabilityStatus: availability,
    qualityStatus: quality,
    source,
    asOf: asOfValue?.toISOString() ?? null,
    availableAt: availableAtValue?.toISOString() ?? null,
    receivedAt: receivedAtValue?.toISOString() ?? null,
    data,
    errorCode,
    reason,
    warnings: [...warningsValue] as string[],
    anomalies,
    methodVersion,
  };
}

function sectionCarriesData(section: SnapshotSection<unknown>) {
  return section.availabilityStatus !== "unavailable";
}

function sectionIsValidated(section: SnapshotSection<unknown>) {
  return (
    (section.availabilityStatus === "live" ||
      section.availabilityStatus === "delayed") &&
    section.qualityStatus === "validated"
  );
}

function withSectionData<T>(
  section: SnapshotSection<unknown>,
  data: T | null,
): SnapshotSection<T> {
  return { ...section, data };
}

function unavailableSection<T>(
  errorCode: string,
  reason: string,
): SnapshotSection<T> {
  return {
    availabilityStatus: "unavailable",
    qualityStatus: "invalid",
    source: null,
    asOf: null,
    availableAt: null,
    receivedAt: null,
    data: null,
    errorCode,
    reason,
    warnings: [],
    anomalies: [],
    methodVersion: "unavailable-v1",
  };
}

function unavailableTechnical(
  candles: Candle[],
  cutoff: string,
): { indicators: LiveTechnicalIndicators; magicNine: MagicNineSnapshot } {
  const asOf = candles.at(-1)?.timestamp ?? cutoff;
  const metadata = {
    source: "analysis-core" as const,
    asOf,
    availableAt: cutoff,
    qualityStatus: "unavailable" as const,
  };
  return {
    indicators: {
      ma5: {
        ...metadata,
        value: null,
        series: null,
        methodVersion: "sma-5-v1",
      },
      rsi: {
        ...metadata,
        value: null,
        series: null,
        methodVersion: "wilder-rsi-14-v1",
      },
      macd: {
        ...metadata,
        line: null,
        signal: null,
        histogram: null,
        series: null,
        methodVersion: "macd-12-26-9-v1",
      },
      volatility: {
        ...metadata,
        value: null,
        series: null,
        sampleSize: 0,
        missingReason: "technical section unavailable",
        methodVersion: "close-to-close-realized-v1",
      },
    },
    magicNine: {
      ...metadata,
      direction: null,
      count: 0,
      series: null,
      completed: false,
      perfected: null,
      confirmedAtIndex: null,
      lastCompleted: null,
      methodVersion: "td-setup-close-4-v2",
    },
  };
}

function v3ParticipationPlaceholders(candles: Candle[]): ParticipationBar[] {
  return candles.map((candle) => ({
    closedAt: candle.timestamp,
    mainShare: null,
    retailShare: null,
    mainActivity: null,
    retailActivity: null,
    netFlow: null,
    coverage: null,
    source: "moomoo",
    asOf: candle.timestamp,
    availableAt: candle.availableAt,
    methodVersion: "order-size-activity-share-v1",
    qualityStatus: "unavailable",
    missingReason: "CURRENT_SESSION_FLOW_NOT_CANDLE_ALIGNED",
  }));
}

function legacyV2Sections({
  quote,
  candles,
  priceAdjustment,
  indicators,
  magicNine,
  institutionalHoldings,
}: {
  quote: LiveQuote;
  candles: Candle[];
  priceAdjustment: PriceAdjustment;
  indicators: LiveTechnicalIndicators;
  magicNine: MagicNineSnapshot;
  institutionalHoldings: DelayedInstitutionalHolding[];
}): StockSnapshotSections {
  const lastCandle = candles[candles.length - 1];
  const firstHolding = institutionalHoldings[0];
  const notRequested = () =>
    unavailableSection<unknown>("NOT_REQUESTED", "此切片未请求该数据");

  return {
    quote: {
      availabilityStatus: "live",
      qualityStatus: "validated",
      source: quote.source,
      asOf: quote.asOf,
      availableAt: quote.availableAt,
      receivedAt: null,
      data: quote,
      errorCode: null,
      reason: null,
      warnings: [],
      anomalies: [],
      methodVersion: quote.methodVersion,
    },
    candles: lastCandle
      ? {
          availabilityStatus: "live",
          qualityStatus: "validated",
          source: "moomoo",
          asOf: lastCandle.timestamp,
          availableAt: lastCandle.availableAt,
          receivedAt: lastCandle.receivedAt ?? null,
          data: { candles, priceAdjustment },
          errorCode: null,
          reason: null,
          warnings: [],
          anomalies: [],
          methodVersion: "provider-completed-candle-v1",
        }
      : unavailableSection("LEGACY_V2_CANDLES_EMPTY", "旧版响应没有已完成 K 线"),
    technical: {
      availabilityStatus: "live",
      qualityStatus: "validated",
      source: "analysis-core",
      asOf: magicNine.asOf,
      availableAt: magicNine.availableAt,
      receivedAt: null,
      data: { indicators, magicNine },
      errorCode: null,
      reason: null,
      warnings: [],
      anomalies: [],
      methodVersion: "analysis-core-indicators-v1",
    },
    currentSessionFlow: unavailableSection(
      "LEGACY_V2_CANDLE_ALIGNED_ONLY",
      "旧版响应只有与 K 线对齐的资金参与代理值",
    ),
    holdings: firstHolding
      ? {
          availabilityStatus: "delayed",
          qualityStatus: "validated",
          source: "moomoo-delayed-institutional-disclosure",
          asOf: firstHolding.reportedAt,
          availableAt: firstHolding.availableAt,
          receivedAt: null,
          data: institutionalHoldings,
          errorCode: null,
          reason: null,
          warnings: [],
          anomalies: [],
          methodVersion: firstHolding.methodVersion,
        }
      : unavailableSection(
          "LEGACY_V2_HOLDINGS_EMPTY",
          "旧版响应没有机构持仓记录",
        ),
    fundamentals: notRequested(),
    marketContext: notRequested(),
    news: notRequested(),
    forecastDecision: notRequested(),
  };
}

/** Decodes only the gateway's versioned live contract; it never adapts fixture data. */
export function decodeStockSnapshotEnvelope(
  value: unknown,
  _options: DecodeOptions = {},
): LiveStockSnapshot {
  if (!isRecord(value)) throw new GatewayValidationError("response must be an object");
  if (value.schemaVersion !== "2") throw new GatewayValidationError("unsupported snapshot schemaVersion");
  if (value.source !== "moomoo") {
    throw new GatewayValidationError("live snapshot responses must identify source as moomoo");
  }
  rejectInstitutionalIdentity(value, "snapshot");
  const snapshotError = decodeSnapshotError(value);
  if (snapshotError) throw snapshotError;

  const cutoff = parseTimestamp(requireString(value, "decisionCutoff"), "decisionCutoff");

  const symbol = normalizeUsSymbol(requireString(value, "symbol"));
  const interval = requireString(value, "interval");
  const quoteRecord = value.quote;
  if (!isRecord(quoteRecord)) throw new GatewayValidationError("quote must be an object");
  rejectInstitutionalIdentity(quoteRecord, "quote");
  const quoteMetadata = requireSnapshotMetadata(quoteRecord, "quote", cutoff);
  if (quoteMetadata.source !== "moomoo") throw new GatewayValidationError("quote source must be moomoo");
  const price = requireFiniteNumber(quoteRecord, "price");
  if (price <= 0) throw new GatewayValidationError("quote price must be positive");
  const quote: LiveQuote = {
    ...quoteMetadata,
    source: "moomoo",
    price,
    changePercent: requireFiniteNumber(quoteRecord, "changePercent"),
    methodVersion: requireExpectedMethod(quoteRecord, "provider-quote-v1", "quote"),
    qualityStatus: "live",
  };
  if (requireStatus(quoteRecord, "qualityStatus") !== "live") {
    throw new GatewayValidationError("quote quality status must be live");
  }

  const priceAdjustment = value.priceAdjustment;
  if (priceAdjustment !== "forward-adjusted" && priceAdjustment !== "unadjusted") {
    throw new GatewayValidationError("snapshot must declare a known price adjustment basis");
  }
  if (!Array.isArray(value.completedCandles)) {
    throw new GatewayValidationError("completedCandles must be an array");
  }
  let previousTimestamp = Number.NEGATIVE_INFINITY;
  const candles = value.completedCandles.map((item) => {
    if (!isRecord(item)) throw new GatewayValidationError("completed candle must be an object");
    rejectInstitutionalIdentity(item, "completed candle");
    if (item.complete !== true) throw new GatewayValidationError("only completed candles may enter a snapshot");
    const timestamp = parseTimestamp(requireString(item, "timestamp"), "completed candle.timestamp");
    const metadata = requireSnapshotMetadata(item, "completed candle", cutoff);
    if (metadata.source !== "moomoo") throw new GatewayValidationError("completed candle source must be moomoo");
    if (timestamp.getTime() > cutoff.getTime() || timestamp.getTime() > new Date(metadata.availableAt).getTime()) {
      throw new GatewayValidationError("completed candle violates point-in-time ordering");
    }
    if (timestamp.getTime() <= previousTimestamp) {
      throw new GatewayValidationError("completed candles must be strictly ordered");
    }
    previousTimestamp = timestamp.getTime();
    const open = requireFiniteNumber(item, "open");
    const high = requireFiniteNumber(item, "high");
    const low = requireFiniteNumber(item, "low");
    const close = requireFiniteNumber(item, "close");
    const volume = requireFiniteNumber(item, "volume");
    if (Math.min(open, high, low, close) <= 0 || volume < 0 || high < Math.max(open, close) || low > Math.min(open, close)) {
      throw new GatewayValidationError("completed candle has invalid OHLCV values");
    }
    if (requireStatus(item, "qualityStatus") !== "live") {
      throw new GatewayValidationError("completed candle quality status must be live");
    }
    requireExpectedMethod(item, "provider-completed-candle-v1", "completed candle");
    requireContractField(item, "receivedAt");
    requireContractField(item, "priceAdjustment");
    const receivedAt = parseTimestamp(requireString(item, "receivedAt"), "completed candle.receivedAt");
    if (
      receivedAt.getTime() < new Date(metadata.availableAt).getTime() ||
      receivedAt.getTime() > cutoff.getTime()
    ) {
      throw new GatewayValidationError("completed candle receipt time is outside the decision cutoff");
    }
    if (item.priceAdjustment !== priceAdjustment) {
      throw new GatewayValidationError("completed candle disagrees with the snapshot price adjustment");
    }
    return {
      timestamp: timestamp.toISOString(),
      availableAt: metadata.availableAt,
      receivedAt: receivedAt.toISOString(),
      priceAdjustment,
      complete: true,
      open,
      high,
      low,
      close,
      volume,
    } satisfies Candle;
  });

  if (!Array.isArray(value.participationBars) || value.participationBars.length !== candles.length) {
    throw new GatewayValidationError("participation bars must align one-to-one with completed candles");
  }
  const participationBars = value.participationBars.map((item, index) => {
    if (!isRecord(item)) throw new GatewayValidationError("participation bar must be an object");
    rejectInstitutionalIdentity(item, "participation bar");
    const metadata = requireSnapshotMetadata(item, "participation bar", cutoff);
    if (metadata.source !== "moomoo") throw new GatewayValidationError("participation bar source must be moomoo");
    const closedAt = parseTimestamp(requireString(item, "closedAt"), "participation bar.closedAt");
    if (closedAt.toISOString() !== candles[index]!.timestamp) {
      throw new GatewayValidationError("participation bar timestamp must align to its candle close");
    }
    const qualityStatus = requireStatus(item, "qualityStatus");
    if (qualityStatus !== "live" && qualityStatus !== "unavailable") {
      throw new GatewayValidationError("participation bar has an unsupported quality status");
    }
    const mainShare = requireNullableFiniteNumber(item, "mainShare");
    const retailShare = requireNullableFiniteNumber(item, "retailShare");
    const mainActivity = requireNullableFiniteNumber(item, "mainActivity");
    const retailActivity = requireNullableFiniteNumber(item, "retailActivity");
    const netFlow = requireNullableFiniteNumber(item, "netFlow");
    const coverage = requireFiniteNumber(item, "coverage");
    if (coverage < 0 || coverage > 1) throw new GatewayValidationError("participation coverage must be in [0, 1]");
    const rawMissingReason = item.missingReason;
    if (rawMissingReason !== null && (typeof rawMissingReason !== "string" || rawMissingReason.trim() === "")) {
      throw new GatewayValidationError("participation missingReason must be a non-empty string or null");
    }
    const missingReason: string | null = rawMissingReason;
    if (qualityStatus === "live") {
      if (mainShare === null || retailShare === null || mainActivity === null || retailActivity === null || netFlow === null || mainShare + retailShare !== 1 || mainShare < 0 || mainShare > 1 || retailShare < 0 || retailShare > 1 || missingReason !== null) {
        throw new GatewayValidationError("live participation bars require complete shares that sum to one");
      }
      if (coverage !== 1) {
        throw new GatewayValidationError("live participation bars require exact complete coverage");
      }
      const activityTotal = mainActivity + retailActivity;
      if (
        mainActivity < 0 ||
        retailActivity < 0 ||
        !Number.isFinite(activityTotal) ||
        activityTotal <= 0 ||
        mainShare !== mainActivity / activityTotal ||
        retailShare !== 1 - mainShare
      ) {
        throw new GatewayValidationError("live participation shares must equal the activity-derived ratio");
      }
    } else if (mainShare !== null || retailShare !== null || mainActivity !== null || retailActivity !== null || netFlow !== null || typeof missingReason !== "string" || missingReason.trim() === "") {
      throw new GatewayValidationError("unavailable participation bars require null metrics and a missing reason");
    }
    return {
      ...metadata,
      source: "moomoo",
      closedAt: closedAt.toISOString(),
      mainShare,
      retailShare,
      mainActivity,
      retailActivity,
      netFlow,
      coverage,
      methodVersion: requireExpectedMethod(item, "order-size-activity-share-v1", "participation bar"),
      qualityStatus,
      missingReason,
    } satisfies ParticipationBar;
  });

  if (!isRecord(value.indicators)) throw new GatewayValidationError("indicators must be an object");
  const ma5 = decodeIndicatorValue(
    value.indicators.ma5,
    "ma5",
    "sma-5-v1",
    cutoff,
    candles.length,
  );
  const rsi = decodeIndicatorValue(
    value.indicators.rsi,
    "rsi",
    "wilder-rsi-14-v1",
    cutoff,
    candles.length,
  );
  const volatility = decodeVolatility(
    value.indicators.volatility,
    cutoff,
    candles.length,
  );
  const macdRecord = value.indicators.macd;
  if (!isRecord(macdRecord)) throw new GatewayValidationError("indicators.macd must be an object");
  const macdMetadata = requireSnapshotMetadata(macdRecord, "indicators.macd", cutoff);
  if (macdMetadata.source !== "analysis-core") throw new GatewayValidationError("indicators.macd must identify analysis-core");
  const macdStatus = requireStatus(macdRecord, "qualityStatus");
  if (macdStatus !== "live" && macdStatus !== "unavailable") throw new GatewayValidationError("indicators.macd has an unsupported quality status");
  const macdValues = ["line", "signal", "histogram"].map((key) => requireNullableFiniteNumber(macdRecord, key));
  if ((macdStatus === "live") !== macdValues.every((item) => item !== null)) {
    throw new GatewayValidationError("indicators.macd quality status does not match its values");
  }
  const macd: LiveMacdIndicator = {
    ...macdMetadata,
    source: "analysis-core",
    line: macdValues[0]!,
    signal: macdValues[1]!,
    histogram: macdValues[2]!,
    series: decodeMacdSeries(
      macdRecord.series,
      macdMetadata,
      macdStatus,
      candles.length,
    ),
    methodVersion: requireExpectedMethod(macdRecord, "macd-12-26-9-v1", "indicators.macd"),
    qualityStatus: macdStatus,
  };
  const magicRecord = value.indicators.magicNine;
  if (!isRecord(magicRecord)) throw new GatewayValidationError("indicators.magicNine must be an object");
  const magicMetadata = requireSnapshotMetadata(magicRecord, "indicators.magicNine", cutoff);
  if (magicMetadata.source !== "analysis-core") throw new GatewayValidationError("indicators.magicNine must identify analysis-core");
  const magicStatus = requireStatus(magicRecord, "qualityStatus");
  if (magicStatus !== "live" && magicStatus !== "unavailable") throw new GatewayValidationError("indicators.magicNine has an unsupported quality status");
  const direction = magicRecord.direction;
  if (direction !== null && direction !== "bullish" && direction !== "bearish") throw new GatewayValidationError("magic nine direction must be bullish, bearish or null");
  const count = requireFiniteNumber(magicRecord, "count");
  if (!Number.isInteger(count) || count < 0 || count > 9) {
    throw new GatewayValidationError("magic nine count must be an integer from zero to nine");
  }
  const rawConfirmedAtIndex = magicRecord.confirmedAtIndex;
  if (rawConfirmedAtIndex !== null && (typeof rawConfirmedAtIndex !== "number" || !Number.isInteger(rawConfirmedAtIndex) || rawConfirmedAtIndex < 0 || rawConfirmedAtIndex >= candles.length)) {
    throw new GatewayValidationError("magic nine confirmedAtIndex is invalid");
  }
  const confirmedAtIndex: number | null = rawConfirmedAtIndex;
  if (typeof magicRecord.completed !== "boolean") throw new GatewayValidationError("magic nine completed must be boolean");
  const perfected = magicRecord.perfected;
  if (perfected !== null && typeof perfected !== "boolean") {
    // null means the bar 8/9 comparison was not performed; only a wrong type
    // is a contract violation.
    throw new GatewayValidationError("magic nine perfected must be boolean or null");
  }
  const magicNine: MagicNineSnapshot = {
    ...magicMetadata,
    source: "analysis-core",
    direction,
    count,
    series: decodeMagicNineSeries(magicRecord.series, candles.length),
    completed: magicRecord.completed,
    perfected,
    confirmedAtIndex,
    lastCompleted: decodeCompletedTdSetup(magicRecord.lastCompleted, candles.length),
    methodVersion: requireExpectedMethod(magicRecord, "td-setup-close-4-v2", "indicators.magicNine"),
    qualityStatus: magicStatus,
  };

  if (!Array.isArray(value.institutionalHoldings)) throw new GatewayValidationError("institutionalHoldings must be an array");
  const institutionalHoldings = value.institutionalHoldings.map((item) => {
    if (!isRecord(item)) throw new GatewayValidationError("institutional holding must be an object");
    rejectInstitutionalIdentity(item, "institutional holding");
    const metadata = requireSnapshotMetadata(item, "institutional holding", cutoff);
    if (metadata.source !== "moomoo-delayed-institutional-disclosure") throw new GatewayValidationError("institutional holding source must be delayed disclosure");
    const reportedAt = parseTimestamp(requireString(item, "reportedAt"), "institutional holding.reportedAt");
    if (reportedAt.getTime() > new Date(metadata.availableAt).getTime()) throw new GatewayValidationError("institutional holding report date follows availability");
    if (item.reportedAtBasis !== "reporting-period-end") throw new GatewayValidationError("institutional holding report date basis is unsupported");
    if (requireStatus(item, "qualityStatus") !== "delayed") throw new GatewayValidationError("institutional holding must be delayed");
    const institutionCount = requireFiniteNumber(item, "institutionCount");
    const sharesHeld = requireFiniteNumber(item, "sharesHeld");
    const holdingPercent = requireFiniteNumber(item, "holdingPercent");
    if (!Number.isInteger(institutionCount) || institutionCount < 0 || sharesHeld < 0 || holdingPercent < 0 || holdingPercent > 100) {
      throw new GatewayValidationError("institutional holding values are invalid");
    }
    return {
      ...metadata,
      source: "moomoo-delayed-institutional-disclosure",
      period: requireString(item, "period"),
      reportedAt: reportedAt.toISOString(),
      reportedAtBasis: "reporting-period-end",
      institutionCount,
      institutionCountChange: requireFiniteNumber(item, "institutionCountChange"),
      sharesHeld,
      sharesHeldChange: requireFiniteNumber(item, "sharesHeldChange"),
      holdingPercent,
      holdingPercentChange: requireFiniteNumber(item, "holdingPercentChange"),
      methodVersion: requireExpectedMethod(item, "reported-holdings-v1", "institutional holding"),
      qualityStatus: "delayed",
    } satisfies DelayedInstitutionalHolding;
  });

  if (!Array.isArray(value.provenance)) throw new GatewayValidationError("provenance must be an array");
  const allowedProvenanceSources = new Set([
    "moomoo",
    "analysis-core",
    "moomoo-delayed-institutional-disclosure",
  ]);
  const provenance = value.provenance.map((item) => {
    if (!isRecord(item)) throw new GatewayValidationError("provenance entry must be an object");
    const metadata = requireSnapshotMetadata(item, "provenance entry", cutoff);
    if (!allowedProvenanceSources.has(metadata.source)) {
      throw new GatewayValidationError("provenance entry has an unsupported source");
    }
    return {
      ...metadata,
      methodVersion: requireString(item, "methodVersion"),
      qualityStatus: requireStatus(item, "qualityStatus"),
    } satisfies SnapshotProvenance;
  });
  if (!Array.isArray(value.warnings) || !value.warnings.every((warning) => typeof warning === "string")) {
    throw new GatewayValidationError("warnings must be an array of strings");
  }
  const indicators: LiveTechnicalIndicators = { ma5, rsi, macd, volatility };
  const sections = legacyV2Sections({
    quote,
    candles,
    priceAdjustment,
    indicators,
    magicNine,
    institutionalHoldings,
  });

  return {
    demoData: false,
    source: {
      source: "moomoo",
      status: "live",
      asOf: cutoff.toISOString(),
      decisionCutoff: cutoff.toISOString(),
    },
    symbol,
    interval,
    snapshotStatus: "live",
    compatibility: "v2-fallback",
    requestedCount: _options.requestedCount ?? candles.length,
    requestedSections: [...requestedSnapshotV3Sections],
    sections,
    decisionCutoff: cutoff.toISOString(),
    priceAdjustment,
    quote,
    candles,
    participationBars,
    indicators,
    magicNine,
    forecast: null,
    institutionalHoldings,
    provenance,
    warnings: value.warnings,
  };
}

function decodeV3QuoteSection(
  section: SnapshotSection<unknown>,
  cutoff: Date,
): SnapshotSection<LiveQuote> {
  if (!sectionCarriesData(section)) {
    return withSectionData<LiveQuote>(section, null);
  }
  if (
    section.source !== "moomoo" ||
    section.methodVersion !== "provider-quote-v1" ||
    !isRecord(section.data)
  ) {
    throw new GatewayValidationError("quote section has an unsupported source contract");
  }
  const record = section.data;
  rejectInstitutionalIdentity(record, "quote section data");
  const metadata = requireSnapshotMetadata(record, "quote section data", cutoff);
  if (
    metadata.source !== "moomoo" ||
    metadata.asOf !== section.asOf ||
    metadata.availableAt !== section.availableAt
  ) {
    throw new GatewayValidationError("quote section metadata contradicts its data");
  }
  const price = requireFiniteNumber(record, "price");
  if (price <= 0) {
    throw new GatewayValidationError("quote section price must be positive");
  }
  if (requireStatus(record, "qualityStatus") !== "live") {
    throw new GatewayValidationError("quote section data must be live");
  }
  const quote: LiveQuote = {
    ...metadata,
    source: "moomoo",
    price,
    changePercent: requireFiniteNumber(record, "changePercent"),
    methodVersion: requireExpectedMethod(
      record,
      "provider-quote-v1",
      "quote section data",
    ),
    qualityStatus: "live",
  };
  return withSectionData(section, quote);
}

function decodeV3CandlesSection(
  section: SnapshotSection<unknown>,
  cutoff: Date,
): SnapshotSection<{ candles: Candle[]; priceAdjustment: PriceAdjustment }> {
  if (!sectionCarriesData(section)) {
    return withSectionData<{ candles: Candle[]; priceAdjustment: PriceAdjustment }>(
      section,
      null,
    );
  }
  if (
    section.source !== "moomoo" ||
    section.methodVersion !== "provider-completed-candle-v1" ||
    !isRecord(section.data)
  ) {
    throw new GatewayValidationError("candles section has an unsupported source contract");
  }
  const priceAdjustment = section.data.priceAdjustment;
  if (
    priceAdjustment !== "forward-adjusted" &&
    priceAdjustment !== "unadjusted"
  ) {
    throw new GatewayValidationError("candles section price adjustment is unsupported");
  }
  if (!Array.isArray(section.data.candles)) {
    throw new GatewayValidationError("candles section data must contain candles");
  }
  let previousTimestamp = Number.NEGATIVE_INFINITY;
  const candles = section.data.candles.map((item) => {
    if (!isRecord(item)) {
      throw new GatewayValidationError("candles section row must be an object");
    }
    rejectInstitutionalIdentity(item, "candles section row");
    if (item.complete !== true) {
      throw new GatewayValidationError("candles section accepts completed rows only");
    }
    const timestamp = parseTimestamp(
      requireString(item, "timestamp"),
      "candles section row.timestamp",
    );
    const metadata = requireSnapshotMetadata(item, "candles section row", cutoff);
    if (metadata.source !== "moomoo") {
      throw new GatewayValidationError("candles section row source must be moomoo");
    }
    if (
      timestamp.getTime() > new Date(metadata.availableAt).getTime() ||
      timestamp.getTime() <= previousTimestamp
    ) {
      throw new GatewayValidationError("candles section rows violate ordering");
    }
    previousTimestamp = timestamp.getTime();
    const receivedAt = parseTimestamp(
      requireString(item, "receivedAt"),
      "candles section row.receivedAt",
    );
    if (
      receivedAt.getTime() < new Date(metadata.availableAt).getTime() ||
      receivedAt.getTime() > cutoff.getTime()
    ) {
      throw new GatewayValidationError("candles section receipt time is invalid");
    }
    if (item.priceAdjustment !== priceAdjustment) {
      throw new GatewayValidationError("candles section row adjustment is inconsistent");
    }
    if (requireStatus(item, "qualityStatus") !== "live") {
      throw new GatewayValidationError("candles section row must be live");
    }
    requireExpectedMethod(
      item,
      "provider-completed-candle-v1",
      "candles section row",
    );
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
      throw new GatewayValidationError("candles section row has invalid OHLCV");
    }
    return {
      timestamp: timestamp.toISOString(),
      availableAt: metadata.availableAt,
      receivedAt: receivedAt.toISOString(),
      priceAdjustment,
      complete: true,
      open,
      high,
      low,
      close,
      volume,
    } satisfies Candle;
  });
  return withSectionData(section, { candles, priceAdjustment });
}

function decodeV3TechnicalSection(
  section: SnapshotSection<unknown>,
  cutoff: Date,
  candleCount: number,
): SnapshotSection<{
  indicators: LiveTechnicalIndicators;
  magicNine: MagicNineSnapshot;
}> {
  if (!sectionCarriesData(section)) {
    return withSectionData<{
      indicators: LiveTechnicalIndicators;
      magicNine: MagicNineSnapshot;
    }>(section, null);
  }
  if (
    section.source !== "analysis-core" ||
    section.methodVersion !== "analysis-core-indicators-v1" ||
    !isRecord(section.data) ||
    !isRecord(section.data.indicators)
  ) {
    throw new GatewayValidationError("technical section has an unsupported source contract");
  }
  const indicatorsRecord = section.data.indicators;
  const ma5 = decodeIndicatorValue(
    indicatorsRecord.ma5,
    "ma5",
    "sma-5-v1",
    cutoff,
    candleCount,
  );
  const rsi = decodeIndicatorValue(
    indicatorsRecord.rsi,
    "rsi",
    "wilder-rsi-14-v1",
    cutoff,
    candleCount,
  );
  const volatility = decodeVolatility(
    indicatorsRecord.volatility,
    cutoff,
    candleCount,
  );
  const macdRecord = indicatorsRecord.macd;
  if (!isRecord(macdRecord)) {
    throw new GatewayValidationError("technical indicators.macd must be an object");
  }
  const macdMetadata = requireSnapshotMetadata(
    macdRecord,
    "indicators.macd",
    cutoff,
  );
  if (macdMetadata.source !== "analysis-core") {
    throw new GatewayValidationError("indicators.macd must identify analysis-core");
  }
  const macdStatus = requireStatus(macdRecord, "qualityStatus");
  if (macdStatus !== "live" && macdStatus !== "unavailable") {
    throw new GatewayValidationError("indicators.macd status is unsupported");
  }
  const macdValues = ["line", "signal", "histogram"].map((key) =>
    requireNullableFiniteNumber(macdRecord, key),
  );
  if ((macdStatus === "live") !== macdValues.every((item) => item !== null)) {
    throw new GatewayValidationError("indicators.macd status contradicts its values");
  }
  const macd: LiveMacdIndicator = {
    ...macdMetadata,
    source: "analysis-core",
    line: macdValues[0]!,
    signal: macdValues[1]!,
    histogram: macdValues[2]!,
    series: decodeMacdSeries(
      macdRecord.series,
      macdMetadata,
      macdStatus,
      candleCount,
    ),
    methodVersion: requireExpectedMethod(
      macdRecord,
      "macd-12-26-9-v1",
      "indicators.macd",
    ),
    qualityStatus: macdStatus,
  };
  const magicRecord = section.data.magicNine;
  if (!isRecord(magicRecord)) {
    throw new GatewayValidationError("technical magicNine must be an object");
  }
  const magicMetadata = requireSnapshotMetadata(
    magicRecord,
    "indicators.magicNine",
    cutoff,
  );
  if (magicMetadata.source !== "analysis-core") {
    throw new GatewayValidationError("indicators.magicNine must identify analysis-core");
  }
  const magicStatus = requireStatus(magicRecord, "qualityStatus");
  if (magicStatus !== "live" && magicStatus !== "unavailable") {
    throw new GatewayValidationError("indicators.magicNine status is unsupported");
  }
  const direction = magicRecord.direction;
  if (
    direction !== null &&
    direction !== "bullish" &&
    direction !== "bearish"
  ) {
    throw new GatewayValidationError("magic nine direction is unsupported");
  }
  const count = requireFiniteNumber(magicRecord, "count");
  if (!Number.isInteger(count) || count < 0 || count > 9) {
    throw new GatewayValidationError("magic nine count is invalid");
  }
  const confirmedAtIndexValue = magicRecord.confirmedAtIndex;
  if (
    confirmedAtIndexValue !== null &&
    (typeof confirmedAtIndexValue !== "number" ||
      !Number.isInteger(confirmedAtIndexValue) ||
      confirmedAtIndexValue < 0 ||
      confirmedAtIndexValue >= candleCount)
  ) {
    throw new GatewayValidationError("magic nine confirmedAtIndex is invalid");
  }
  if (typeof magicRecord.completed !== "boolean") {
    throw new GatewayValidationError("magic nine completed must be boolean");
  }
  if (magicRecord.perfected !== null && typeof magicRecord.perfected !== "boolean") {
    throw new GatewayValidationError("magic nine perfected must be boolean or null");
  }
  const magicNine: MagicNineSnapshot = {
    ...magicMetadata,
    source: "analysis-core",
    direction,
    count,
    series: decodeMagicNineSeries(magicRecord.series, candleCount),
    completed: magicRecord.completed,
    perfected: magicRecord.perfected,
    confirmedAtIndex: confirmedAtIndexValue as number | null,
    lastCompleted: decodeCompletedTdSetup(magicRecord.lastCompleted, candleCount),
    methodVersion: requireExpectedMethod(
      magicRecord,
      "td-setup-close-4-v2",
      "indicators.magicNine",
    ),
    qualityStatus: magicStatus,
  };
  return withSectionData(section, {
    indicators: { ma5, rsi, macd, volatility },
    magicNine,
  });
}

function decodeV3CurrentSessionFlowSection(
  section: SnapshotSection<unknown>,
  cutoff: Date,
): SnapshotSection<NormalizedCapitalFlowPoint[]> {
  if (!sectionCarriesData(section)) {
    return withSectionData<NormalizedCapitalFlowPoint[]>(section, null);
  }
  if (
    section.source !== "moomoo" ||
    section.methodVersion !== "provider-capital-flow-normalized-v1" ||
    !Array.isArray(section.data) ||
    section.data.length === 0
  ) {
    throw new GatewayValidationError(
      "currentSessionFlow section has an unsupported source contract",
    );
  }
  let previousTimestamp = Number.NEGATIVE_INFINITY;
  const data = section.data.map((item, index) => {
    if (!isRecord(item)) {
      throw new GatewayValidationError(
        `currentSessionFlow row ${index} must be an object`,
      );
    }
    const timestamp = parseTimestamp(
      requireString(item, "timestamp"),
      `currentSessionFlow row ${index}.timestamp`,
    );
    const availableAt = parseTimestamp(
      requireString(item, "availableAt"),
      `currentSessionFlow row ${index}.availableAt`,
    );
    if (
      timestamp.getTime() <= previousTimestamp ||
      timestamp.getTime() > availableAt.getTime() ||
      availableAt.getTime() > cutoff.getTime() ||
      (section.receivedAt !== null &&
        availableAt.getTime() > Date.parse(section.receivedAt))
    ) {
      throw new GatewayValidationError(
        "currentSessionFlow rows violate point-in-time ordering",
      );
    }
    previousTimestamp = timestamp.getTime();
    if (item.institutionalIdentity !== false) {
      throw new GatewayValidationError(
        "currentSessionFlow must declare institutionalIdentity false",
      );
    }
    return {
      timestamp: timestamp.toISOString(),
      availableAt: availableAt.toISOString(),
      session: requireString(item, "session"),
      totalNetFlow: requireFiniteNumber(item, "totalNetFlow"),
      extraLargeOrderNetFlow: requireFiniteNumber(
        item,
        "extraLargeOrderNetFlow",
      ),
      largeOrderNetFlow: requireFiniteNumber(item, "largeOrderNetFlow"),
      mediumOrderNetFlow: requireFiniteNumber(item, "mediumOrderNetFlow"),
      smallOrderNetFlow: requireFiniteNumber(item, "smallOrderNetFlow"),
      largeOrderProxyNetFlow: requireFiniteNumber(
        item,
        "largeOrderProxyNetFlow",
      ),
      institutionalIdentity: false,
    } satisfies NormalizedCapitalFlowPoint;
  });
  return withSectionData(section, data);
}

const aggregateHoldingsWarning =
  "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释";

function decodeV3HoldingsSection(
  section: SnapshotSection<unknown>,
  cutoff: Date,
): SnapshotSection<DelayedInstitutionalHolding[]> {
  if (!sectionCarriesData(section)) {
    return withSectionData<DelayedInstitutionalHolding[]>(section, null);
  }
  if (
    section.availabilityStatus !== "delayed" ||
    section.source !== "moomoo-delayed-institutional-disclosure" ||
    section.methodVersion !== "reported-holdings-v2-anomaly-aware" ||
    !Array.isArray(section.data) ||
    section.data.length === 0
  ) {
    throw new GatewayValidationError("holdings section has an unsupported source contract");
  }
  if (
    section.qualityStatus === "anomalous" &&
    section.anomalies.length === 0
  ) {
    throw new GatewayValidationError("an anomalous holdings section must name anomalies");
  }
  if (
    section.qualityStatus === "validated" &&
    section.anomalies.length !== 0
  ) {
    throw new GatewayValidationError("validated holdings cannot carry anomalies");
  }
  let previousAvailableAt = Number.POSITIVE_INFINITY;
  const data = section.data.map((item, index) => {
    if (!isRecord(item)) {
      throw new GatewayValidationError(`holdings row ${index} must be an object`);
    }
    if (item.source !== "moomoo-delayed-institutional-disclosure") {
      throw new GatewayValidationError(`holdings row ${index} has the wrong source`);
    }
    const reportedAt = parseTimestamp(
      requireString(item, "reportedAt"),
      `holdings row ${index}.reportedAt`,
    );
    const availableAt = parseTimestamp(
      requireString(item, "availableAt"),
      `holdings row ${index}.availableAt`,
    );
    if (
      reportedAt.getTime() > availableAt.getTime() ||
      availableAt.getTime() > cutoff.getTime() ||
      availableAt.getTime() > previousAvailableAt ||
      (section.receivedAt !== null &&
        availableAt.getTime() > Date.parse(section.receivedAt))
    ) {
      throw new GatewayValidationError(`holdings row ${index} violates ordering`);
    }
    previousAvailableAt = availableAt.getTime();
    if (item.reportedAtBasis !== "reporting-period-end") {
      throw new GatewayValidationError(`holdings row ${index} has the wrong date basis`);
    }
    const institutionCount = requireFiniteNumber(item, "institutionCount");
    const institutionCountChange = requireFiniteNumber(
      item,
      "institutionCountChange",
    );
    const sharesHeld = requireFiniteNumber(item, "sharesHeld");
    const sharesHeldChange = requireFiniteNumber(item, "sharesHeldChange");
    const holdingPercent = requireFiniteNumber(item, "holdingPercent");
    const holdingPercentChange = requireFiniteNumber(
      item,
      "holdingPercentChange",
    );
    if (
      !Number.isInteger(institutionCount) ||
      institutionCount < 0 ||
      sharesHeld < 0 ||
      holdingPercent < 0
    ) {
      throw new GatewayValidationError(`holdings row ${index} has invalid values`);
    }
    if (
      holdingPercent > 100 &&
      (section.qualityStatus !== "anomalous" ||
        !section.warnings.includes(aggregateHoldingsWarning) ||
        !section.anomalies.some(
          (anomaly) =>
            anomaly.rowIndex === index &&
            anomaly.code === "AGGREGATE_PERCENT_ABOVE_100",
        ))
    ) {
      throw new GatewayValidationError(
        `holdings row ${index} aggregate percentage is not explained`,
      );
    }
    return {
      period: requireString(item, "period"),
      reportedAt: reportedAt.toISOString(),
      reportedAtBasis: "reporting-period-end",
      availableAt: availableAt.toISOString(),
      source: "moomoo-delayed-institutional-disclosure",
      institutionCount,
      institutionCountChange,
      sharesHeld,
      sharesHeldChange,
      holdingPercent,
      holdingPercentChange,
      asOf: reportedAt.toISOString(),
      methodVersion: "reported-holdings-v2-anomaly-aware",
      qualityStatus: "delayed",
    } satisfies DelayedInstitutionalHolding;
  });
  return withSectionData(section, data);
}

function snapshotUnavailableKind(sections: StockSnapshotSections) {
  for (const code of [sections.quote.errorCode, sections.candles.errorCode]) {
    if (code && kindByGatewayCode[code]) return kindByGatewayCode[code];
  }
  return "unspecified" satisfies GatewayRequestErrorKind;
}

/** Decodes only the sectioned schema-v3 contract; it never adapts v2. */
export function decodeStockSnapshotV3Envelope(
  value: unknown,
  _options: DecodeOptions = {},
): LiveStockSnapshot {
  if (!isRecord(value)) {
    throw new GatewayValidationError("response must be an object");
  }
  if (
    typeof value.schemaVersion === "string" &&
    /^\d+$/.test(value.schemaVersion) &&
    !new Set(["1", "2", "3"]).has(value.schemaVersion)
  ) {
    throw new GatewayClientUpdateRequiredError(value.schemaVersion);
  }
  if (value.schemaVersion !== "3") {
    throw new GatewayValidationError("unsupported snapshot schemaVersion");
  }
  const symbol = normalizeUsSymbol(requireString(value, "symbol"));
  const interval = requireString(value, "interval");
  const requestedCount = requireFiniteNumber(value, "count");
  if (
    !Number.isInteger(requestedCount) ||
    requestedCount < 1 ||
    requestedCount > 1_000
  ) {
    throw new GatewayValidationError("snapshot count must be an integer from 1 to 1000");
  }
  const cutoff = parseTimestamp(
    requireString(value, "decisionCutoff"),
    "decisionCutoff",
  );
  const status = requireString(value, "status");
  if (status !== "live" && status !== "partial" && status !== "unavailable") {
    throw new GatewayValidationError("snapshot status is unsupported");
  }
  if (
    !Array.isArray(value.requestedSections) ||
    value.requestedSections.length !== requestedSnapshotV3Sections.length ||
    !value.requestedSections.every(
      (name, index) => name === requestedSnapshotV3Sections[index],
    )
  ) {
    throw new GatewayValidationError("snapshot requestedSections do not match the v3 slice");
  }
  if (!isRecord(value.sections)) {
    throw new GatewayValidationError("snapshot sections must be an object");
  }
  const envelopes = Object.fromEntries(
    snapshotV3SectionNames.map((name) => [
      name,
      decodeSnapshotV3SectionEnvelope(
        requireContractField(value.sections as Record<string, unknown>, name),
        name,
        cutoff,
      ),
    ]),
  ) as Record<SnapshotSectionName, SnapshotSection<unknown>>;

  for (const name of [
    "fundamentals",
    "marketContext",
    "news",
    "forecastDecision",
  ] as const) {
    const section = envelopes[name];
    if (
      section.availabilityStatus !== "unavailable" ||
      section.qualityStatus !== "invalid" ||
      section.errorCode !== "NOT_REQUESTED" ||
      section.data !== null
    ) {
      throw new GatewayValidationError(`sections.${name} must be explicitly unrequested`);
    }
  }

  const quote = decodeV3QuoteSection(envelopes.quote, cutoff);
  const candles = decodeV3CandlesSection(envelopes.candles, cutoff);
  const decodedCandles = candles.data?.candles ?? [];
  const technical = decodeV3TechnicalSection(
    envelopes.technical,
    cutoff,
    decodedCandles.length,
  );
  const currentSessionFlow = decodeV3CurrentSessionFlowSection(
    envelopes.currentSessionFlow,
    cutoff,
  );
  const holdings = decodeV3HoldingsSection(envelopes.holdings, cutoff);
  const sections: StockSnapshotSections = {
    quote,
    candles,
    technical,
    currentSessionFlow,
    holdings,
    fundamentals: withSectionData(envelopes.fundamentals, null),
    marketContext: withSectionData(envelopes.marketContext, null),
    news: withSectionData(envelopes.news, null),
    forecastDecision: withSectionData(envelopes.forecastDecision, null),
  };
  const quoteUsable = sectionIsValidated(quote) && quote.data !== null;
  const candlesUsable =
    sectionIsValidated(candles) &&
    candles.data !== null &&
    candles.data.candles.length > 0;
  const allRequestedValidated = requestedSnapshotV3Sections.every((name) =>
    sectionIsValidated(sections[name]),
  );
  const derivedStatus =
    !quoteUsable && !candlesUsable
      ? "unavailable"
      : allRequestedValidated
        ? "live"
        : "partial";
  if (status !== derivedStatus) {
    throw new GatewayValidationError("snapshot status contradicts its usable sections");
  }
  if (derivedStatus === "unavailable") {
    throw new GatewaySnapshotUnavailableError(
      snapshotUnavailableKind(sections),
      "gateway snapshot has neither a usable quote nor completed candles",
    );
  }

  const flattenedCandles = candlesUsable ? candles.data!.candles : [];
  const fallbackTechnical = unavailableTechnical(
    flattenedCandles,
    cutoff.toISOString(),
  );
  const technicalUsable =
    sectionIsValidated(technical) && technical.data !== null && candlesUsable;
  const institutionalHoldings =
    holdings.data &&
    holdings.availabilityStatus === "delayed" &&
    (holdings.qualityStatus === "validated" ||
      holdings.qualityStatus === "anomalous")
      ? holdings.data
      : [];
  const provenance = snapshotV3SectionNames.flatMap((name) => {
    const section = sections[name];
    return section.source && section.asOf && section.availableAt
      ? [
          {
            source: section.source,
            asOf: section.asOf,
            availableAt: section.availableAt,
            methodVersion: section.methodVersion,
            qualityStatus: section.availabilityStatus,
          } satisfies SnapshotProvenance,
        ]
      : [];
  });
  const warnings = [...new Set(snapshotV3SectionNames.flatMap(
    (name) => sections[name].warnings,
  ))];

  return {
    demoData: false,
    source: {
      source: "moomoo",
      status: derivedStatus,
      asOf: cutoff.toISOString(),
      decisionCutoff: cutoff.toISOString(),
    },
    symbol,
    interval,
    snapshotStatus: derivedStatus,
    compatibility: "v3",
    requestedCount,
    requestedSections: [...requestedSnapshotV3Sections],
    sections,
    decisionCutoff: cutoff.toISOString(),
    priceAdjustment: candlesUsable ? candles.data!.priceAdjustment : null,
    quote: quoteUsable ? quote.data : null,
    candles: flattenedCandles,
    participationBars: v3ParticipationPlaceholders(flattenedCandles),
    indicators: technicalUsable
      ? technical.data!.indicators
      : fallbackTechnical.indicators,
    magicNine: technicalUsable
      ? technical.data!.magicNine
      : fallbackTechnical.magicNine,
    forecast: null,
    institutionalHoldings,
    provenance,
    warnings,
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
  if (!isLoopback && (!authorizationToken || authorizationToken.length < 32)) {
    throw new GatewayValidationError(
      "a 32-character or longer ephemeral token is required for a LAN gateway",
    );
  }

  async function fetchJson(path: string, callerSignal?: AbortSignal) {
    if (callerSignal?.aborted) {
      const error = new Error("gateway request was aborted by caller");
      error.name = "AbortError";
      throw error;
    }

    const controller = new AbortController();
    let abortCause: "caller" | "timeout" | null = null;
    const abortOnce = (cause: "caller" | "timeout") => {
      if (abortCause !== null) return;
      abortCause = cause;
      controller.abort();
    };
    const abortFromCaller = () => abortOnce("caller");
    callerSignal?.addEventListener("abort", abortFromCaller, { once: true });
    const timeout = setTimeout(() => abortOnce("timeout"), timeoutMs);
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
      let payload: unknown;
      try {
        payload = (await response.json()) as unknown;
      } catch {
        throw new GatewayHttpError(response.status, null);
      }
      if (!response.ok) throw new GatewayHttpError(response.status, payload);
      return payload;
    } catch (error) {
      if (abortCause === "timeout") {
        throw new GatewayRequestError("timeout", "gateway request timed out");
      }
      if (abortCause === "caller") {
        if (error instanceof Error && error.name === "AbortError") throw error;
        const callerError = new Error("gateway request was aborted by caller");
        callerError.name = "AbortError";
        throw callerError;
      }
      if (error instanceof Error && error.name === "AbortError") {
        throw new GatewayRequestError(
          "offline",
          "gateway request was aborted without a known cause",
        );
      }
      throw error;
    } finally {
      clearTimeout(timeout);
      callerSignal?.removeEventListener("abort", abortFromCaller);
    }
  }

  function toSnapshotRequestError(error: unknown): GatewayRequestError {
    if (error instanceof GatewayRequestError) return error;
    if (error instanceof GatewayClientUpdateRequiredError) {
      return new GatewayRequestError("client-update-required", error.message);
    }
    if (error instanceof GatewaySnapshotUnavailableError) {
      return new GatewayRequestError(error.kind, error.message);
    }
    if (error instanceof GatewayHttpError) {
      const named = isRecord(error.payload)
        ? decodeSnapshotError(error.payload)
        : null;
      // The code the gateway named outranks the status it travelled with. Both
      // 401 and 403 carry two codes each — an unpaired device against an
      // unlogged-in OpenD, a blocked network against a missing quote
      // entitlement — and reading the status alone merged each pair.
      if (named && named.kind !== "unspecified") return named;
      if (error.status === 401) return new GatewayRequestError("auth-required", error.message);
      // A 403 with no code of its own is genuinely ambiguous between an
      // entitlement and an allowlist; the entitlement is the one a reader can
      // check, so the copy sends them there.
      if (error.status === 403) return new GatewayRequestError("permission", error.message);
      if (error.status === 408 || error.status === 504) return new GatewayRequestError("timeout", error.message);
      return named ?? new GatewayRequestError("unspecified", error.message);
    }
    if (error instanceof Error && error.name === "AbortError") {
      return new GatewayRequestError(
        "offline",
        "gateway request was aborted without a known cause",
      );
    }
    if (error instanceof GatewayContractError) {
      return new GatewayRequestError("contract", error.message);
    }
    if (error instanceof GatewayValidationError) {
      // This app failing to read the gateway's answer is a different fact from
      // the gateway judging the provider's data unusable, and it has a
      // different fix. Sharing "malformed" between them meant the screen
      // explained a point-in-time rejection that had never happened.
      return new GatewayRequestError("validation", error.message);
    }
    return new GatewayRequestError("offline", "gateway request is unavailable");
  }

  async function getWatchlist(signal?: AbortSignal): Promise<LiveWatchlistResult> {
    let payload: unknown;
    try {
      payload = await fetchJson("/watchlist", signal);
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") throw error;
      throw toSnapshotRequestError(error);
    }
    return decodeWatchlistEnvelope(payload, { maxAgeMs, now: now() });
  }

  return {
    getWatchlist,
    async getWatchlistOrFallback(
      fallbackQuotes: WatchlistQuote[],
    ): Promise<WatchlistResult> {
      try {
        return await getWatchlist();
      } catch (error) {
        const gatewayUnavailable =
          error instanceof GatewayRequestError &&
          (error.kind === "offline" || error.kind === "timeout");
        return {
          source: "fixture",
          asOf: null,
          quotes: fallbackQuotes,
          fallbackReason: gatewayUnavailable
            ? "gateway-unavailable"
            : "gateway-invalid",
        };
      }
    },
    async getCandles(
      symbol: string,
      interval: CandleInterval,
      count = 200,
      signal?: AbortSignal,
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
      const payload = await fetchJson(`/candles?${query.toString()}`, signal);
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
    async getStockSnapshot(
      symbol: string,
      interval: CandleInterval,
      count = 200,
      signal?: AbortSignal,
    ): Promise<LiveStockSnapshot> {
      const normalizedSymbol = normalizeUsSymbol(symbol);
      if (!Number.isInteger(count) || count < 1 || count > 1_000) {
        throw new GatewayValidationError(
          "snapshot count must be an integer between 1 and 1000",
        );
      }
      const query = new URLSearchParams({
        symbol: normalizedSymbol,
        interval,
        count: String(count),
      });
      try {
        let payload: unknown;
        try {
          payload = await fetchJson(
            `/v3/stock-snapshot?${query.toString()}`,
            signal,
          );
        } catch (error) {
          if (
            !(error instanceof GatewayHttpError) ||
            (error.status !== 404 && error.status !== 426)
          ) {
            throw error;
          }
          const legacyPayload = await fetchJson(
            `/stock-snapshot?${query.toString()}`,
            signal,
          );
          const legacySnapshot = decodeStockSnapshotEnvelope(legacyPayload, {
            maxAgeMs,
            now: now(),
            requestedCount: count,
          });
          if (
            legacySnapshot.symbol !== normalizedSymbol ||
            legacySnapshot.interval !== interval ||
            legacySnapshot.requestedCount !== count
          ) {
            throw new GatewayValidationError(
              "snapshot response does not match the requested series",
            );
          }
          return legacySnapshot;
        }
        const snapshot = decodeStockSnapshotV3Envelope(payload, {
          maxAgeMs,
          now: now(),
        });
        if (
          snapshot.symbol !== normalizedSymbol ||
          snapshot.interval !== interval ||
          snapshot.requestedCount !== count
        ) {
          throw new GatewayValidationError("snapshot response does not match the requested series");
        }
        return snapshot;
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") throw error;
        throw toSnapshotRequestError(error);
      }
    },
  };
}
