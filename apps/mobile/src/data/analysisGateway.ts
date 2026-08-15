import { ADVISER_SCORE_CAP } from "@/domain/models";
import type {
  AdviserBlock,
  AdviserBlockStatus,
  AdviserCitation,
  AdviserConclusion,
  AdviserUsage,
  CouncilFrameworkOpinion,
  DataHealth,
  Decision,
  DecisionAdviserCouncil,
  DecisionForecast,
  DecisionNewsInterpretation,
  DecisionRiskPlan,
  DecisionScore,
  FactorContribution,
  Horizon,
  MarketBrief,
  MarketBriefCitation,
  MarketBriefDriverCoverage,
  MarketBriefSentiment,
  MarketDriverCategory,
} from "@/domain/models";

/**
 * Decodes the analysis service's answer.
 *
 * The service goes to some trouble to state what it could not see — a partial
 * factor coverage, a forecast it declines to invent. This decoder's job is to
 * let those survive: an absence must arrive as an absence, never as a zero or
 * a quietly dropped field, because the screen renders directly from this.
 */

const CLOCK_SKEW_TOLERANCE_MS = 5 * 60_000;

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

/**
 * The analysis service's error vocabulary, kept distinct all the way to the
 * screen.
 *
 * `analysis-failed` is the one that matters most and the one that used to be
 * missing: the service answering "the decision chain could not be evaluated"
 * is a statement about the chain, not about the bytes it sent, and reporting
 * it as a malformed payload sent the reader hunting for corrupt data that was
 * never there.
 */
export type AnalysisRequestErrorKind =
  | "analysis-failed"
  | "auth-required"
  | "auth-unavailable"
  | "client-not-allowed"
  | "invalid-request"
  | "login-required"
  | "offline"
  | "permission"
  | "route-unsupported"
  | "timeout"
  | "unspecified"
  | "validation";

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

/** Same shape as `score`; null when the engine had nothing to baseline. */
function decodeOptionalScore(value: unknown): DecisionScore | null {
  if (value === null || value === undefined) return null;
  return decodeScore(value);
}

/**
 * Null is the whole point: it means no adviser council ran for this
 * response, a fact the server states explicitly rather than folding into a
 * measured zero. A council that ran and was voided by a hard gate reports
 * 0.0, a real number distinct from "nobody asked" -- so this only rejects
 * shapes that are neither null nor a number, or a number the server's own
 * ±ADVISER_SCORE_CAP invariant forbids.
 */
function decodeAdviserAdjustment(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new DecisionValidationError(
      "adviserAdjustment must be null or a finite number",
    );
  }
  if (Math.abs(value) > ADVISER_SCORE_CAP) {
    throw new DecisionValidationError(
      `adviserAdjustment must not exceed the shared ±${ADVISER_SCORE_CAP} adviser cap`,
    );
  }
  return value;
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

/**
 * Null passes through unchanged; anything else must be exactly a two-element
 * array of finite numbers, ordered low to high. There is no coercion path: a
 * shape that does not already satisfy this is refused, not patched into one
 * that does.
 */
function decodeOrderedRange(value: unknown, key: string): [number, number] | null {
  if (value === null || value === undefined) return null;
  if (!Array.isArray(value) || value.length !== 2) {
    throw new DecisionValidationError(`${key} must be null or a two-element array`);
  }
  const [low, high] = value;
  if (
    typeof low !== "number" ||
    !Number.isFinite(low) ||
    typeof high !== "number" ||
    !Number.isFinite(high)
  ) {
    throw new DecisionValidationError(`${key} must contain two finite numbers`);
  }
  if (low > high) {
    throw new DecisionValidationError(`${key} bounds must be ordered low to high`);
  }
  return [low, high];
}

/** Null passes through unchanged; anything else must be a finite number. */
function decodeOptionalFiniteNumber(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new DecisionValidationError(`${key} must be null or a finite number`);
  }
  return value;
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
    entryRange: decodeOrderedRange(value.entryRange, "entryRange"),
    invalidationPrice: decodeOptionalFiniteNumber(value, "invalidationPrice"),
    targetRange: decodeOrderedRange(value.targetRange, "targetRange"),
    maxPositionPercent: requireFiniteNumber(value, "maxPositionPercent"),
    leverage: requireFiniteNumber(value, "leverage"),
    warnings: value.warnings.map(String),
    methodVersion: requireString(value, "methodVersion"),
  };
}

const ADVISER_STATUSES = ["not-requested", "available", "unavailable"];

function decodeAdviserCitation(value: unknown): AdviserCitation {
  if (!isRecord(value)) {
    throw new DecisionValidationError("adviser citation must be an object");
  }
  const url = requireString(value, "url");
  if (!url.startsWith("https://")) {
    throw new DecisionValidationError("adviser citation url must be https");
  }
  return {
    evidenceId: requireString(value, "evidenceId"),
    quote: requireString(value, "quote"),
    url,
    publisher: requireString(value, "publisher"),
    availableAt: requireString(value, "availableAt"),
    isCounterEvidence: value.isCounterEvidence === true,
  };
}

function decodeAdviserConclusion(value: unknown): AdviserConclusion {
  if (!isRecord(value)) {
    throw new DecisionValidationError("adviser conclusion must be an object");
  }
  if (!Array.isArray(value.citations) || value.citations.length === 0) {
    // The server refuses an unsourced conclusion before it is serialized. This
    // is the same rule restated where the rendering happens, because a
    // sentence on the screen with nothing to open is exactly what the
    // traceability rule exists to prevent.
    throw new DecisionValidationError(
      "an adviser conclusion must carry at least one citation",
    );
  }
  const counter = value.counterEvidence;
  if (counter !== undefined && !Array.isArray(counter)) {
    throw new DecisionValidationError("counterEvidence must be an array");
  }
  return {
    statement: requireString(value, "statement"),
    confidence: requireString(value, "confidence"),
    citations: value.citations.map(decodeAdviserCitation),
    counterEvidence: (counter ?? []).map(decodeAdviserCitation),
  };
}

/**
 * Decodes one adviser block, keeping its three states apart.
 *
 * A field that is absent entirely means the server has never heard of the
 * adviser layer, which is neither an error nor an opinion; it decodes to null
 * and the screen says so in its own words. Anything present has to be
 * well-formed: a block claiming to be available with nothing inside it, or a
 * degraded block that will not say why, is refused rather than rendered as an
 * empty card.
 */
function decodeAdviserBlock<T>(
  value: unknown,
  decodeValue: (raw: Record<string, unknown>) => T,
): AdviserBlock<T> | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) {
    throw new DecisionValidationError("adviser block must be an object or null");
  }
  const status = requireString(value, "status");
  if (!ADVISER_STATUSES.includes(status)) {
    throw new DecisionValidationError(`unsupported adviser status: ${status}`);
  }
  const reason = value.reason;
  if (reason !== null && typeof reason !== "string") {
    throw new DecisionValidationError("adviser reason must be a string or null");
  }
  if (status === "available") {
    if (!isRecord(value.value)) {
      throw new DecisionValidationError(
        "an available adviser block must carry its value",
      );
    }
    return {
      status: status as AdviserBlockStatus,
      reason: reason ?? null,
      value: decodeValue(value.value),
    };
  }
  if (value.value !== null && value.value !== undefined) {
    throw new DecisionValidationError(
      "an adviser block that is not available must not carry a value",
    );
  }
  if (typeof reason !== "string" || reason.trim() === "") {
    // Silence here is the failure mode: without a reason the reader cannot
    // tell an unasked question from an unreachable model.
    throw new DecisionValidationError(
      "an adviser block without a value must say why",
    );
  }
  return { status: status as AdviserBlockStatus, reason, value: null };
}

function decodeNewsInterpretation(
  value: Record<string, unknown>,
): DecisionNewsInterpretation {
  if (
    !Array.isArray(value.investmentImpact) ||
    value.investmentImpact.length === 0
  ) {
    throw new DecisionValidationError(
      "a news interpretation must carry its investment impact",
    );
  }
  if (!Array.isArray(value.unknowns)) {
    throw new DecisionValidationError("unknowns must be an array");
  }
  return {
    headlineSummary: requireString(value, "headlineSummary"),
    crossSourceReading: requireString(value, "crossSourceReading"),
    investmentImpact: value.investmentImpact.map(decodeAdviserConclusion),
    unknowns: value.unknowns.map(String),
  };
}

function decodeAdviserCouncil(
  value: Record<string, unknown>,
): DecisionAdviserCouncil {
  if (!Array.isArray(value.opinions) || value.opinions.length === 0) {
    throw new DecisionValidationError("a council brief must carry its opinions");
  }
  if (!Array.isArray(value.blockedBy)) {
    throw new DecisionValidationError("blockedBy must be an array");
  }
  if (typeof value.actionable !== "boolean") {
    throw new DecisionValidationError("council actionable must be boolean");
  }
  return {
    summary: requireString(value, "summary"),
    opinions: value.opinions.map((item): CouncilFrameworkOpinion => {
      if (!isRecord(item)) {
        throw new DecisionValidationError("council opinion must be an object");
      }
      if (!Array.isArray(item.conclusions) || item.conclusions.length === 0) {
        throw new DecisionValidationError(
          "a council opinion must carry its conclusions",
        );
      }
      return {
        frameworkId: requireString(item, "frameworkId"),
        displayName: requireString(item, "displayName"),
        stance: requireString(item, "stance"),
        // A framework that names nothing it cannot see is being presented as
        // omniscient, which is the failure the council was built to avoid.
        blindSpot: requireString(item, "blindSpot"),
        conclusions: item.conclusions.map(decodeAdviserConclusion),
      };
    }),
    baselineScore: requireFiniteNumber(value, "baselineScore"),
    adjustedScore: requireFiniteNumber(value, "adjustedScore"),
    scoreAdjustment: requireFiniteNumber(value, "scoreAdjustment"),
    objectiveDirection: requireString(value, "objectiveDirection"),
    actionable: value.actionable,
    blockedBy: value.blockedBy.map(String),
    disclaimer: requireString(value, "disclaimer"),
  };
}

function decodeAdviserUsage(value: unknown): AdviserUsage | null {
  // Null is "no call reported what it spent". Zeros would claim a call was
  // measured and cost nothing, which is a different statement about money.
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) {
    throw new DecisionValidationError("adviserUsage must be an object or null");
  }
  const cost = requireFiniteNumber(value, "costUsd");
  if (cost < 0) {
    throw new DecisionValidationError("adviser cost cannot be negative");
  }
  const model = value.model;
  if (model !== null && model !== undefined && typeof model !== "string") {
    throw new DecisionValidationError("adviser model must be a string or null");
  }
  return {
    model: typeof model === "string" && model.trim() !== "" ? model : null,
    inputTokens: requireFiniteNumber(value, "inputTokens"),
    outputTokens: requireFiniteNumber(value, "outputTokens"),
    cacheCreationInputTokens: requireFiniteNumber(
      value,
      "cacheCreationInputTokens",
    ),
    cacheReadInputTokens: requireFiniteNumber(value, "cacheReadInputTokens"),
    costUsd: cost,
  };
}

const MARKET_SESSIONS = ["premarket", "regular", "afterhours", "closed"];
const DATA_HEALTH_VALUES = ["fresh", "stale", "conflict", "insufficient"];
const MARKET_DRIVER_CATEGORIES = [
  "news-sentiment",
  "breadth",
  "volatility-options",
  "sector",
  "rates-dollar",
  "macro-credit-energy",
  "liquidity-correlation",
  "broad-market-trend",
  "geopolitics",
];

function decodeMarketBriefSentiment(value: unknown): MarketBriefSentiment {
  if (!isRecord(value)) {
    throw new DecisionValidationError("market brief sentiment must be an object");
  }
  if (!Array.isArray(value.uncertainty)) {
    throw new DecisionValidationError("sentiment uncertainty must be an array");
  }
  return {
    conclusion: requireString(value, "conclusion"),
    // Always a measured float, never null, exactly like a decision's
    // sentiment: 0.0 means unmeasured, and the "情绪未测量" string inside
    // uncertainty -- not a null value here -- is what says so.
    actionScore: requireFiniteNumber(value, "actionScore"),
    uncertainty: value.uncertainty.map(String),
  };
}

function decodeMarketBriefDriverCoverage(
  value: unknown,
): MarketBriefDriverCoverage {
  if (!isRecord(value)) {
    throw new DecisionValidationError("driver coverage entry must be an object");
  }
  const category = requireString(value, "category");
  if (!MARKET_DRIVER_CATEGORIES.includes(category)) {
    throw new DecisionValidationError(
      `unsupported market driver category: ${category}`,
    );
  }
  if (typeof value.available !== "boolean") {
    throw new DecisionValidationError("driver coverage available must be boolean");
  }
  const conclusion = value.conclusion;
  if (conclusion !== null && typeof conclusion !== "string") {
    throw new DecisionValidationError(
      "driver coverage conclusion must be a string or null",
    );
  }
  const actionScore = decodeOptionalFiniteNumber(value, "actionScore");
  const missingReason = value.missingReason;
  if (missingReason !== null && typeof missingReason !== "string") {
    throw new DecisionValidationError(
      "driver coverage missingReason must be a string or null",
    );
  }
  if (value.available) {
    // A sourced category must carry the values it claims to have; an
    // "available: true" entry with nothing inside it is exactly the kind of
    // fabricated-looking gap this envelope exists to avoid.
    if (conclusion === null || actionScore === null) {
      throw new DecisionValidationError(
        "an available driver category must carry its conclusion and score",
      );
    }
    if (missingReason !== null) {
      throw new DecisionValidationError(
        "an available driver category must not carry a missing reason",
      );
    }
  } else {
    if (conclusion !== null || actionScore !== null) {
      throw new DecisionValidationError(
        "an unavailable driver category must not carry a conclusion or score",
      );
    }
    // Silence here is the failure mode this whole disclosure exists to
    // prevent: a category with no source and no stated reason reads as an
    // oversight, not an honest gap.
    if (typeof missingReason !== "string" || missingReason.trim() === "") {
      throw new DecisionValidationError(
        "an unavailable driver category must say why",
      );
    }
  }
  return {
    category: category as MarketDriverCategory,
    available: value.available,
    conclusion,
    actionScore,
    missingReason,
  };
}

function decodeMarketBriefCitation(value: unknown): MarketBriefCitation {
  if (!isRecord(value)) {
    throw new DecisionValidationError("market brief citation must be an object");
  }
  const url = requireString(value, "url");
  if (!url.startsWith("https://")) {
    throw new DecisionValidationError("market brief citation url must be https");
  }
  const freshnessSeconds = decodeOptionalFiniteNumber(value, "freshnessSeconds");
  const stale = value.stale;
  if (stale !== null && typeof stale !== "boolean") {
    throw new DecisionValidationError(
      "market brief citation stale must be boolean or null",
    );
  }
  return {
    id: requireString(value, "id"),
    headline: requireString(value, "headline"),
    publisher: requireString(value, "publisher"),
    url,
    availableAt: requireString(value, "availableAt"),
    freshnessSeconds,
    stale,
  };
}

/**
 * Decodes `GET /market-brief`'s envelope with the same strictness discipline
 * `decodeDecisionEnvelope` already uses: null means an honest absence, never
 * a coerced zero; an order or credential field anywhere in the payload
 * rejects the whole response; a citation is refused rather than served over
 * plain http; the cutoff tolerates the same few minutes of clock skew a
 * decision's does. The wire shape is frozen by
 * `.superpowers/sdd/2026-08-15-stage5-objective-review/market-brief-contract.md`.
 */
export function decodeMarketBriefEnvelope(
  value: unknown,
  { now = new Date() }: { now?: Date } = {},
): MarketBrief {
  if (!isRecord(value)) {
    throw new DecisionValidationError("market brief must be an object");
  }
  rejectOrderFields(value);
  if (value.schemaVersion !== "1") {
    throw new DecisionValidationError("unsupported market brief schemaVersion");
  }
  const status = requireString(value, "status");
  if (status !== "available" && status !== "unavailable") {
    throw new DecisionValidationError("market brief status is unsupported");
  }
  const cutoff = parseTimestamp(
    requireString(value, "decisionCutoff"),
    "decisionCutoff",
  );
  // Same tolerance as a decision's cutoff, for the same reason: the service
  // stamps this the instant it answers, so a few milliseconds of latency --
  // or of this device's clock lagging -- is not the service claiming to know
  // the future. That claim is measured in minutes.
  if (cutoff.getTime() - now.getTime() > CLOCK_SKEW_TOLERANCE_MS) {
    throw new DecisionValidationError("market brief cutoff is in the future");
  }
  const marketSession = requireString(value, "marketSession");
  if (!MARKET_SESSIONS.includes(marketSession)) {
    throw new DecisionValidationError("market brief session is unsupported");
  }
  const reason = value.reason;
  if (reason !== null && typeof reason !== "string") {
    throw new DecisionValidationError(
      "market brief reason must be a string or null",
    );
  }
  if (!Array.isArray(value.driverCoverage) || value.driverCoverage.length !== 9) {
    throw new DecisionValidationError(
      "market brief must name all nine driver categories",
    );
  }
  const driverCoverage = value.driverCoverage.map(decodeMarketBriefDriverCoverage);
  if (new Set(driverCoverage.map((item) => item.category)).size !== 9) {
    // Nine entries by count alone lets a duplicate category silently stand
    // in for a dropped one -- the reader would see nine rows and never
    // notice one of the nine designed categories never actually showed up.
    throw new DecisionValidationError(
      "market brief driver categories must be nine distinct categories",
    );
  }
  if (!Array.isArray(value.citations)) {
    throw new DecisionValidationError("market brief citations must be an array");
  }
  if (!Array.isArray(value.sourceGaps)) {
    throw new DecisionValidationError("market brief sourceGaps must be an array");
  }

  let dataHealth: DataHealth | null;
  let sentiment: MarketBriefSentiment | null;
  if (status === "unavailable") {
    // The fail-closed path: every configured source failed, so an outage
    // must never be served looking like a quiet market. The reason names
    // every failed source, and none of the readings a real sweep would have
    // produced may ride along with it.
    if (typeof reason !== "string" || reason.trim() === "") {
      throw new DecisionValidationError(
        "an unavailable market brief must say why",
      );
    }
    if (value.dataHealth !== null) {
      throw new DecisionValidationError(
        "an unavailable market brief must not carry a data health reading",
      );
    }
    if (value.sentiment !== null) {
      throw new DecisionValidationError(
        "an unavailable market brief must not carry a sentiment reading",
      );
    }
    if (value.citations.length !== 0) {
      throw new DecisionValidationError(
        "an unavailable market brief must not carry citations",
      );
    }
    if (driverCoverage.some((item) => item.available)) {
      // Same rule decodeDecisionEnvelope already holds for a decision's own
      // score: the two states render differently, so a payload claiming
      // both -- the whole brief unavailable, one driver category available
      // -- reads as sourced on one screen and as an outage on another.
      throw new DecisionValidationError(
        "an unavailable market brief must not carry an available driver category",
      );
    }
    dataHealth = null;
    sentiment = null;
  } else {
    if (reason !== null) {
      throw new DecisionValidationError(
        "an available market brief must not carry a reason",
      );
    }
    const dataHealthRaw = value.dataHealth;
    if (
      typeof dataHealthRaw !== "string" ||
      !DATA_HEALTH_VALUES.includes(dataHealthRaw)
    ) {
      throw new DecisionValidationError(
        "market brief data health is unsupported",
      );
    }
    if (value.sentiment === null || value.sentiment === undefined) {
      throw new DecisionValidationError(
        "an available market brief must carry a sentiment reading",
      );
    }
    dataHealth = dataHealthRaw as DataHealth;
    sentiment = decodeMarketBriefSentiment(value.sentiment);
  }

  return {
    status,
    reason: reason ?? null,
    decisionCutoff: cutoff.toISOString(),
    marketSession: marketSession as MarketBrief["marketSession"],
    dataHealth,
    sentiment,
    driverCoverage,
    citations: value.citations.map(decodeMarketBriefCitation),
    sourceGaps: value.sourceGaps.map(String),
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
  // The service stamps this at the instant it answers, so it arrives a few
  // milliseconds old — or a few milliseconds ahead if this device's clock
  // lags behind the service's. Rejecting on that rejected every decision.
  // The check is here to catch a service claiming to know the future, and
  // that claim is measured in minutes.
  if (cutoff.getTime() - now.getTime() > CLOCK_SKEW_TOLERANCE_MS) {
    throw new DecisionValidationError("decision cutoff is in the future");
  }
  const score = value.score === null ? null : decodeScore(value.score);
  if (status === "live" && score === null) {
    throw new DecisionValidationError("a live decision must carry a score");
  }
  if (status === "unavailable" && score !== null) {
    // The two states are rendered differently, so a payload claiming both
    // reads as a live score on one screen and as unavailable on another.
    throw new DecisionValidationError(
      "an unavailable decision must not carry a score",
    );
  }
  if (!Array.isArray(value.notes) || !Array.isArray(value.citations)) {
    throw new DecisionValidationError("notes and citations must be arrays");
  }
  const baselineScore = decodeOptionalScore(value.baselineScore);
  const adviserAdjustment = decodeAdviserAdjustment(value.adviserAdjustment);
  return {
    status,
    symbol: requireString(value, "symbol"),
    horizon: requireString(value, "horizon"),
    interval: requireString(value, "interval"),
    decisionCutoff: cutoff.toISOString(),
    score,
    baselineScore,
    adviserAdjustment,
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
    newsInterpretation: decodeAdviserBlock(
      value.newsInterpretation,
      decodeNewsInterpretation,
    ),
    adviserCouncil: decodeAdviserBlock(value.adviserCouncil, decodeAdviserCouncil),
    adviserUsage: decodeAdviserUsage(value.adviserUsage),
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
  INVALID_ARGUMENT: "invalid-request",
  // A path and a method this service will not serve are the same fact to the
  // reader: this build is asking for something the server does not offer.
  PATH_NOT_ALLOWED: "route-unsupported",
  METHOD_NOT_ALLOWED: "route-unsupported",
  CLIENT_NOT_ALLOWED: "client-not-allowed",
  LOGIN_REQUIRED: "login-required",
  // The device gate refusing this phone's token and the brokerage session
  // being logged out are unrelated problems with unrelated fixes.
  AUTH_REQUIRED: "auth-required",
  AUTH_UNAVAILABLE: "auth-unavailable",
  PERMISSION_DENIED: "permission",
  ANALYSIS_FAILED: "analysis-failed",
};

/**
 * The kind a failed response names, or null when it names nothing this app
 * recognizes — the caller then falls back to the HTTP status rather than
 * guessing here.
 */
function kindForPayload(payload: unknown): AnalysisRequestErrorKind | null {
  const error = isRecord(payload) && isRecord(payload.error) ? payload.error : null;
  const code = error && typeof error.code === "string" ? error.code : null;
  return (code ? kindByErrorCode[code] : undefined) ?? null;
}

export type AnalysisSource = {
  getDecision(
    symbol: string,
    horizon: Horizon,
    signal?: AbortSignal,
    options?: AnalysisRequestOptions,
  ): Promise<Decision>;
  /**
   * Optional because the fakes elsewhere in this codebase only ever exercise
   * `getDecision`; the real client below always implements it. `GET
   * /market-brief` takes no symbol or horizon -- it is the Dashboard's
   * real-mode market hero, safe to call on every load.
   */
  getMarketBrief?(signal?: AbortSignal): Promise<MarketBrief>;
};

export type AnalysisRequestOptions = {
  /**
   * One explicit, single-stock model call. Never set this on list requests.
   *
   * `"news"` asks for the single-report interpretation and rides the
   * client's normal deadline. `"full"` asks for the thirteen-seat council: on
   * the wire it becomes `&adviser=true`, not the literal word "full" -- the
   * server's `_flag` parser only knows `1/true/yes/0/false/no/news`, and
   * `_adviser_mode` already resolves the boolean `True` to the full council --
   * and it gets the longer `COUNCIL_TIMEOUT_MS` deadline instead.
   */
  adviser?: "news" | "full";
};

/**
 * The server's own ceiling for a full council run (up to 300s, ~$0.10/run —
 * services/analysis_api/README.md). A plain decision or a single-report news
 * call answers in a few seconds and keeps the client's normal `timeoutMs`;
 * only the thirteen-seat council needs a deadline this long.
 */
const COUNCIL_TIMEOUT_MS = 300_000;

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
  // The deterministic chain reads public evidence and factors before it
  // answers. A single factor fetch is allowed up to 30 seconds server-side,
  // so the old eight-second client deadline guaranteed that a healthy but
  // uncached first request could be abandoned before the server's own budget.
  // This still ends by itself and does not change the separately opt-in model
  // path; market quotes continue to use their much shorter deadline.
  timeoutMs = 45_000,
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

  async function fetchJson(
    path: string,
    callerSignal?: AbortSignal,
    timeoutOverrideMs?: number,
  ) {
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
    const timeout = setTimeout(
      () => abortOnce("timeout"),
      timeoutOverrideMs ?? timeoutMs,
    );
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
      // The named code wins over the status: this service answers 401 only for
      // an unusable device token, and 403 for a network it will not talk to,
      // neither of which is the brokerage login the old mapping implied.
      const named = kindForPayload(error.payload);
      if (named) return new AnalysisRequestError(named, error.message);
      if (error.status === 401) {
        return new AnalysisRequestError("auth-required", error.message);
      }
      if (error.status === 403) {
        return new AnalysisRequestError("permission", error.message);
      }
      if (error.status === 408 || error.status === 504) {
        return new AnalysisRequestError("timeout", error.message);
      }
      // A body that would not parse is this app's reading problem; a body that
      // parsed and named a code nothing here knows is the service's own
      // vocabulary moving on. The reader is told which of the two happened.
      if (error.payload === null) {
        return new AnalysisRequestError("validation", error.message);
      }
      return new AnalysisRequestError("unspecified", error.message);
    }
    if (error instanceof Error && error.name === "AbortError") {
      return new AnalysisRequestError(
        "offline",
        "analysis request was aborted without a known cause",
      );
    }
    if (error instanceof DecisionValidationError) {
      // This app refusing the answer is not the service declining to produce
      // one; only the latter is `analysis-failed`.
      return new AnalysisRequestError("validation", error.message);
    }
    return new AnalysisRequestError("offline", "the analysis service is unavailable");
  }

  return {
    async getDecision(symbol, horizon, signal, options) {
      const normalizedSymbol = normalizeUsSymbol(symbol);
      const query = new URLSearchParams({
        symbol: normalizedSymbol,
        horizon,
      });
      // "full" is this client's name for the mode; the wire only understands
      // the boolean switch the server's `_flag` parser accepts, which
      // `_adviser_mode` then resolves to the full council.
      if (options?.adviser === "full") {
        query.set("adviser", "true");
      } else if (options?.adviser) {
        query.set("adviser", options.adviser);
      }
      try {
        const payload = await fetchJson(
          `/decision?${query.toString()}`,
          signal,
          options?.adviser === "full" ? COUNCIL_TIMEOUT_MS : undefined,
        );
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
    async getMarketBrief(signal) {
      try {
        const payload = await fetchJson("/market-brief", signal);
        return decodeMarketBriefEnvelope(payload, { now: now() });
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") throw error;
        throw toAnalysisRequestError(error);
      }
    },
  };
}
