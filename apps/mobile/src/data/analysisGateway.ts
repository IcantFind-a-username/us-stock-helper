import type {
  Decision,
  DecisionForecast,
  DecisionRiskPlan,
  DecisionScore,
  FactorContribution,
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
