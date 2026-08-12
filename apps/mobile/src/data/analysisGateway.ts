import type {
  Decision,
  DecisionForecast,
  DecisionRiskPlan,
  DecisionScore,
  FactorContribution,
  Horizon,
} from "@/domain/models";

/**
 * Decodes the analysis service's answer.
 *
 * The service goes to some trouble to state what it could not see — a partial
 * factor coverage, a forecast it declines to invent. This decoder's job is to
 * let those survive: an absence must arrive as an absence, never as a zero or
 * a quietly dropped field, because the screen renders directly from this.
 */

const ORDER_FIELDS = [
  "submitOrder",
  "orderId",
  "quantity",
  "accountId",
  "brokerToken",
];

export class DecisionValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DecisionValidationError";
  }
}

export type AnalysisRequestErrorKind =
  | "configuration"
  | "contract"
  | "login-required"
  | "malformed"
  | "offline"
  | "permission"
  | "timeout";

export class AnalysisRequestError extends DecisionValidationError {
  constructor(
    public readonly kind: AnalysisRequestErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "AnalysisRequestError";
  }
}

class AnalysisHttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`analysis service returned HTTP ${status}`);
    this.name = "AnalysisHttpError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (typeof value !== "string" || value.trim() === "") {
    throw new DecisionValidationError(`${key} must be a non-empty string`);
  }
  return value;
}

function requireFiniteNumber(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new DecisionValidationError(`${key} must be a finite number`);
  }
  return value;
}

function parseTimestamp(value: string, label: string) {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || !/[zZ]|[+-]\d\d:\d\d$/.test(value)) {
    throw new DecisionValidationError(`${label} must be an ISO timestamp`);
  }
  return parsed;
}

function rejectOrderFields(value: unknown): void {
  if (Array.isArray(value)) {
    value.forEach(rejectOrderFields);
    return;
  }
  if (!isRecord(value)) return;
  for (const field of ORDER_FIELDS) {
    if (field in value) {
      throw new DecisionValidationError(
        `analysis payload must not carry an order field: ${field}`,
      );
    }
  }
  Object.values(value).forEach(rejectOrderFields);
}

function decodeContribution(value: unknown): FactorContribution {
  if (!isRecord(value)) {
    throw new DecisionValidationError("contribution must be an object");
  }
  const rawValue = value.rawValue;
  if (rawValue !== null && (typeof rawValue !== "number" || !Number.isFinite(rawValue))) {
    // null is the whole point: it means no source supplied the factor.
    throw new DecisionValidationError("contribution rawValue must be a number or null");
  }
  return {
    name: requireString(value, "name"),
    rawValue,
    weight: requireFiniteNumber(value, "weight"),
    points: requireFiniteNumber(value, "points"),
    explanation: requireString(value, "explanation"),
  };
}

function decodeScore(value: unknown): DecisionScore {
  if (!isRecord(value)) {
    throw new DecisionValidationError("score must be an object");
  }
  const score = requireFiniteNumber(value, "value");
  if (score < 0 || score > 100) {
    throw new DecisionValidationError("score must be between 0 and 100");
  }
  const coverage = requireFiniteNumber(value, "factorCoverage");
  if (coverage < 0 || coverage > 1) {
    throw new DecisionValidationError("factorCoverage must be between 0 and 1");
  }
  const direction = requireString(value, "direction");
  if (!["bullish", "bearish", "neutral"].includes(direction)) {
    throw new DecisionValidationError("score direction is unsupported");
  }
  if (typeof value.actionable !== "boolean") {
    throw new DecisionValidationError("score actionable must be boolean");
  }
  if (!Array.isArray(value.unavailableFactors) || !Array.isArray(value.blockedBy)) {
    throw new DecisionValidationError("score factor lists must be arrays");
  }
  if (!Array.isArray(value.contributions) || value.contributions.length === 0) {
    throw new DecisionValidationError("score must itemize its contributions");
  }
  return {
    value: score,
    direction: direction as DecisionScore["direction"],
    actionable: value.actionable,
    methodVersion: requireString(value, "methodVersion"),
    factorCoverage: coverage,
    unavailableFactors: value.unavailableFactors.map(String),
    blockedBy: value.blockedBy.map(String),
    contributions: value.contributions.map(decodeContribution),
  };
}

function decodeForecast(value: unknown): DecisionForecast | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) {
    throw new DecisionValidationError("forecast must be an object or null");
  }
  if (!Array.isArray(value.cases) || value.cases.length !== 3) {
    throw new DecisionValidationError("forecast requires bear, base and bull");
  }
  const cases = value.cases.map((item) => {
    if (!isRecord(item)) {
      throw new DecisionValidationError("scenario must be an object");
    }
    const low = requireFiniteNumber(item, "priceLow");
    const high = requireFiniteNumber(item, "priceHigh");
    if (low <= 0 || low > high) {
      throw new DecisionValidationError("scenario price range must be positive and ordered");
    }
    const probability = requireFiniteNumber(item, "probability");
    if (probability < 0 || probability > 1) {
      throw new DecisionValidationError("scenario probability must be between 0 and 1");
    }
    return {
      kind: requireString(item, "kind"),
      probability,
      priceLow: low,
      priceHigh: high,
      explanation: requireString(item, "explanation"),
    };
  });
  if (new Set(cases.map((item) => item.kind)).size !== 3) {
    throw new DecisionValidationError("forecast scenarios must be distinct");
  }
  const total = cases.reduce((sum, item) => sum + item.probability, 0);
  if (Math.abs(total - 1) > 1e-9) {
    throw new DecisionValidationError("scenario probabilities must sum to 1");
  }
  if (!Array.isArray(value.invalidationConditions) || value.invalidationConditions.length === 0) {
    throw new DecisionValidationError("forecast requires invalidation conditions");
  }
  return {
    currentPrice: requireFiniteNumber(value, "currentPrice"),
    methodVersion: requireString(value, "methodVersion"),
    calibrationStatus: requireString(value, "calibrationStatus"),
    invalidationConditions: value.invalidationConditions.map(String),
    disclaimer: requireString(value, "disclaimer"),
    cases: cases as DecisionForecast["cases"],
  };
}

function decodeRiskPlan(value: unknown): DecisionRiskPlan | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) {
    throw new DecisionValidationError("riskPlan must be an object or null");
  }
  const action = requireString(value, "action");
  if (!["long", "short", "watch", "avoid"].includes(action)) {
    throw new DecisionValidationError("risk plan action is unsupported");
  }
  if (!Array.isArray(value.warnings) || value.warnings.length === 0) {
    throw new DecisionValidationError("risk plan must carry its warnings");
  }
  return {
    action: action as DecisionRiskPlan["action"],
    direction: requireString(value, "direction"),
    entryRange: Array.isArray(value.entryRange)
      ? (value.entryRange.map(Number) as [number, number])
      : null,
    invalidationPrice:
      typeof value.invalidationPrice === "number" ? value.invalidationPrice : null,
    targetRange: Array.isArray(value.targetRange)
      ? (value.targetRange.map(Number) as [number, number])
      : null,
    maxPositionPercent: requireFiniteNumber(value, "maxPositionPercent"),
    leverage: requireFiniteNumber(value, "leverage"),
    warnings: value.warnings.map(String),
    methodVersion: requireString(value, "methodVersion"),
  };
}

export function decodeDecisionEnvelope(
  value: unknown,
  { now = new Date() }: { now?: Date } = {},
): Decision {
  if (!isRecord(value)) {
    throw new DecisionValidationError("decision must be an object");
  }
  rejectOrderFields(value);
  if (value.schemaVersion !== "1") {
    throw new DecisionValidationError("unsupported decision schemaVersion");
  }
  const status = requireString(value, "status");
  if (status !== "live" && status !== "unavailable") {
    throw new DecisionValidationError("decision status is unsupported");
  }
  const cutoff = parseTimestamp(
    requireString(value, "decisionCutoff"),
    "decisionCutoff",
  );
  if (cutoff.getTime() > now.getTime()) {
    throw new DecisionValidationError("decision cutoff is in the future");
  }
  const score = value.score === null ? null : decodeScore(value.score);
  if (status === "live" && score === null) {
    throw new DecisionValidationError("a live decision must carry a score");
  }
  if (!Array.isArray(value.notes) || !Array.isArray(value.citations)) {
    throw new DecisionValidationError("notes and citations must be arrays");
  }
  return {
    status,
    symbol: requireString(value, "symbol"),
    horizon: requireString(value, "horizon"),
    decisionCutoff: cutoff.toISOString(),
    score,
    forecast: decodeForecast(value.forecast),
    riskPlan: decodeRiskPlan(value.riskPlan),
    citations: value.citations.map((item) => {
      if (!isRecord(item)) {
        throw new DecisionValidationError("citation must be an object");
      }
      const url = requireString(item, "url");
      if (!url.startsWith("https://")) {
        throw new DecisionValidationError("citation url must be https");
      }
      return {
        id: requireString(item, "id"),
        headline: requireString(item, "headline"),
        publisher: requireString(item, "publisher"),
        url,
        availableAt: requireString(item, "availableAt"),
      };
    }),
    notes: value.notes.map(String),
  };
}

function normalizeUsSymbol(code: string) {
  const normalized = code.trim().toUpperCase();
  const match = /^(?:US\.)?([A-Z][A-Z0-9.-]{0,9})$/.exec(normalized);
  if (!match?.[1]) throw new DecisionValidationError(`unsupported US code: ${code}`);
  return match[1];
}

const kindByErrorCode: Record<string, AnalysisRequestErrorKind> = {
  INVALID_ARGUMENT: "contract",
  PATH_NOT_ALLOWED: "contract",
  METHOD_NOT_ALLOWED: "contract",
  LOGIN_REQUIRED: "login-required",
  AUTH_REQUIRED: "login-required",
  PERMISSION_DENIED: "permission",
  ANALYSIS_FAILED: "malformed",
};

function kindForPayload(payload: unknown): AnalysisRequestErrorKind {
  const error = isRecord(payload) && isRecord(payload.error) ? payload.error : null;
  const code = error && typeof error.code === "string" ? error.code : null;
  return (code ? kindByErrorCode[code] : undefined) ?? "malformed";
}

export type AnalysisSource = {
  getDecision(
    symbol: string,
    horizon: Horizon,
    signal?: AbortSignal,
  ): Promise<Decision>;
};

type AnalysisClientOptions = {
  baseUrl: string;
  authorizationToken?: string;
  fetchImpl?: typeof fetch;
  now?: () => Date;
  timeoutMs?: number;
};

export function createAnalysisClient({
  baseUrl,
  authorizationToken,
  fetchImpl = fetch,
  now = () => new Date(),
  // The chain scores, forecasts and cites before it answers, so it needs a
  // longer deadline than a quote read; the request still has to end by itself.
  timeoutMs = 8_000,
}: AnalysisClientOptions): AnalysisSource {
  const normalizedBaseUrl = baseUrl.replace(/\/+$/, "");
  let parsedBaseUrl: URL;
  try {
    parsedBaseUrl = new URL(normalizedBaseUrl);
  } catch {
    throw new DecisionValidationError("analysis baseUrl is invalid");
  }
  if (
    !["http:", "https:"].includes(parsedBaseUrl.protocol) ||
    parsedBaseUrl.username !== "" ||
    parsedBaseUrl.password !== "" ||
    (parsedBaseUrl.pathname !== "" && parsedBaseUrl.pathname !== "/") ||
    parsedBaseUrl.search !== "" ||
    parsedBaseUrl.hash !== ""
  ) {
    throw new DecisionValidationError(
      "analysis baseUrl must be a credential-free HTTP(S) origin",
    );
  }
  const isLoopback = new Set(["127.0.0.1", "localhost", "::1"]).has(
    parsedBaseUrl.hostname,
  );
  if (!isLoopback && (!authorizationToken || authorizationToken.length < 32)) {
    throw new DecisionValidationError(
      "a 32-character or longer ephemeral token is required for a LAN analysis service",
    );
  }

  async function fetchJson(path: string, callerSignal?: AbortSignal) {
    if (callerSignal?.aborted) {
      const error = new Error("analysis request was aborted by caller");
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
        throw new AnalysisHttpError(response.status, null);
      }
      if (!response.ok) throw new AnalysisHttpError(response.status, payload);
      return payload;
    } catch (error) {
      if (abortCause === "timeout") {
        throw new AnalysisRequestError("timeout", "analysis request timed out");
      }
      if (abortCause === "caller") {
        if (error instanceof Error && error.name === "AbortError") throw error;
        const callerError = new Error("analysis request was aborted by caller");
        callerError.name = "AbortError";
        throw callerError;
      }
      if (error instanceof Error && error.name === "AbortError") {
        throw new AnalysisRequestError(
          "offline",
          "analysis request was aborted without a known cause",
        );
      }
      throw error;
    } finally {
      clearTimeout(timeout);
      callerSignal?.removeEventListener("abort", abortFromCaller);
    }
  }

  function toAnalysisRequestError(error: unknown): AnalysisRequestError {
    if (error instanceof AnalysisRequestError) return error;
    if (error instanceof AnalysisHttpError) {
      if (error.status === 401) {
        return new AnalysisRequestError("login-required", error.message);
      }
      if (error.status === 403) {
        return new AnalysisRequestError("permission", error.message);
      }
      if (error.status === 408 || error.status === 504) {
        return new AnalysisRequestError("timeout", error.message);
      }
      return new AnalysisRequestError(kindForPayload(error.payload), error.message);
    }
    if (error instanceof Error && error.name === "AbortError") {
      return new AnalysisRequestError(
        "offline",
        "analysis request was aborted without a known cause",
      );
    }
    if (error instanceof DecisionValidationError) {
      return new AnalysisRequestError("malformed", error.message);
    }
    return new AnalysisRequestError("offline", "the analysis service is unavailable");
  }

  return {
    async getDecision(symbol, horizon, signal) {
      const normalizedSymbol = normalizeUsSymbol(symbol);
      const query = new URLSearchParams({
        symbol: normalizedSymbol,
        horizon,
      });
      try {
        const payload = await fetchJson(`/decision?${query.toString()}`, signal);
        const decision = decodeDecisionEnvelope(payload, { now: now() });
        if (
          decision.symbol !== normalizedSymbol ||
          decision.horizon !== horizon
        ) {
          throw new DecisionValidationError(
            "decision response does not match the requested symbol and horizon",
          );
        }
        return decision;
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") throw error;
        throw toAnalysisRequestError(error);
      }
    },
  };
}
