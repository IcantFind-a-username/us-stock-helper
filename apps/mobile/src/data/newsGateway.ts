import type {
  NewsBriefing,
  NewsClaim,
  NewsClaimStatus,
  NewsFeedSection,
  NewsInterpretationSection,
  NewsSource,
  NewsStory,
} from "@/domain/news";

/**
 * Decodes the news service's answer.
 *
 * The decoder is where "unverifiable information must not appear" becomes
 * structural: a report with no link is removed here and counted, so no screen
 * downstream is able to render one by accident. Everything else follows the
 * other gateways — one versioned contract, strict validation, and no path that
 * substitutes fixture data for a service that did not answer.
 */

export class NewsValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NewsValidationError";
  }
}

export type NewsRequestErrorKind =
  | "configuration"
  | "contract"
  | "login-required"
  | "malformed"
  | "offline"
  | "permission"
  | "timeout";

export class NewsRequestError extends NewsValidationError {
  constructor(
    public readonly kind: NewsRequestErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "NewsRequestError";
  }
}

const claimStatuses = new Set<NewsClaimStatus>(["verified", "reported", "rumor"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (typeof value !== "string" || value.trim() === "") {
    throw new NewsValidationError(`${key} must be a non-empty string`);
  }
  return value;
}

function requireFiniteNumber(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new NewsValidationError(`${key} must be a finite number`);
  }
  return value;
}

function parseTimestamp(value: string, label: string) {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || !/[zZ]|[+-]\d\d:\d\d$/.test(value)) {
    throw new NewsValidationError(`${label} must be an ISO timestamp with timezone`);
  }
  return parsed;
}

function normalizeUsSymbol(code: string) {
  const normalized = code.trim().toUpperCase();
  const match = /^(?:US\.)?([A-Z][A-Z0-9.-]{0,9})$/.exec(normalized);
  if (!match?.[1]) throw new NewsValidationError(`unsupported US code: ${code}`);
  return match[1];
}

type DecodedReport = NewsSource | { linked: false };

function decodeReport(value: unknown, cutoff: Date): DecodedReport {
  if (!isRecord(value)) {
    throw new NewsValidationError("report must be an object");
  }
  const publisherId = requireString(value, "publisherId");
  const publisher = requireString(value, "publisher");
  const reliability = requireFiniteNumber(value, "reliability");
  if (reliability < 0 || reliability > 1) {
    throw new NewsValidationError("report reliability must be between 0 and 1");
  }
  const availableAt = parseTimestamp(
    requireString(value, "availableAt"),
    "report.availableAt",
  );
  const receivedAt = parseTimestamp(
    requireString(value, "receivedAt"),
    "report.receivedAt",
  );
  if (receivedAt.getTime() < availableAt.getTime()) {
    throw new NewsValidationError(
      "report.receivedAt cannot precede its publication",
    );
  }
  if (receivedAt.getTime() > cutoff.getTime()) {
    throw new NewsValidationError("report arrived after the snapshot cutoff");
  }
  const url = value.url;
  if (url === null) return { linked: false };
  if (typeof url !== "string" || !url.startsWith("https://")) {
    throw new NewsValidationError("report url must be an https link or null");
  }
  return {
    publisherId,
    publisher,
    url,
    reliability,
    availableAt: availableAt.toISOString(),
    receivedAt: receivedAt.toISOString(),
  };
}

function decodeStory(value: unknown, cutoff: Date): NewsStory | null {
  if (!isRecord(value)) {
    throw new NewsValidationError("story must be an object");
  }
  const id = requireString(value, "id");
  const headline = requireString(value, "headline");
  const claimStatus = requireString(value, "claimStatus");
  if (!claimStatuses.has(claimStatus as NewsClaimStatus)) {
    throw new NewsValidationError(`story claimStatus is unsupported: ${claimStatus}`);
  }
  if (!Array.isArray(value.reports) || value.reports.length === 0) {
    throw new NewsValidationError("story must carry at least one report");
  }
  const decoded = value.reports.map((report) => decodeReport(report, cutoff));
  const sources = decoded.filter((report): report is NewsSource => "url" in report);
  if (sources.length === 0) return null;
  const ordered = [...sources].sort(
    (left, right) => Date.parse(left.availableAt) - Date.parse(right.availableAt),
  );
  const earliest = ordered[0]!;
  return {
    id,
    headline,
    claimStatus: claimStatus as NewsClaimStatus,
    // Timed by the earliest openable copy: a timestamp taken from a report the
    // reader cannot reach would put an unverifiable moment at the top of a
    // list sorted by time.
    availableAt: earliest.availableAt,
    receivedAt: earliest.receivedAt,
    sources: ordered,
    sourceCount: new Set(ordered.map((source) => source.publisherId)).size,
    omittedSourceCount: decoded.length - sources.length,
  };
}

function decodeFeed(
  value: unknown,
  cutoff: Date,
): { section: NewsFeedSection; knownStoryIds: Set<string> } {
  if (!isRecord(value)) throw new NewsValidationError("feed must be an object");
  const status = requireString(value, "status");
  if (status !== "connected" && status !== "not-connected") {
    throw new NewsValidationError(`feed status is unsupported: ${status}`);
  }
  if (!Array.isArray(value.stories)) {
    throw new NewsValidationError("feed stories must be an array");
  }
  if (status === "not-connected") {
    if (value.stories.length > 0) {
      throw new NewsValidationError(
        "a not-connected feed must not carry stories",
      );
    }
    const reason = value.reason;
    if (typeof reason !== "string" || reason.trim() === "") {
      throw new NewsValidationError(
        "a not-connected feed must state its reason",
      );
    }
    return {
      section: { status: "not-connected", reason },
      knownStoryIds: new Set<string>(),
    };
  }

  const knownStoryIds = new Set<string>();
  const stories: NewsStory[] = [];
  let hiddenStoryCount = 0;
  for (const item of value.stories) {
    const story = decodeStory(item, cutoff);
    const id = isRecord(item) ? requireString(item, "id") : "";
    if (knownStoryIds.has(id)) {
      throw new NewsValidationError(`feed carries a duplicate story id: ${id}`);
    }
    knownStoryIds.add(id);
    if (story === null) {
      hiddenStoryCount += 1;
      continue;
    }
    stories.push(story);
  }
  return {
    section: { status: "connected", stories, hiddenStoryCount },
    knownStoryIds,
  };
}

function decodeClaim(value: unknown, knownStoryIds: Set<string>): NewsClaim {
  if (!isRecord(value)) throw new NewsValidationError("claim must be an object");
  const evidenceIds = value.evidenceIds;
  if (!Array.isArray(evidenceIds) || evidenceIds.length === 0) {
    throw new NewsValidationError("claim evidenceIds must be a non-empty array");
  }
  const ids = evidenceIds.map((id) => {
    if (typeof id !== "string" || id.trim() === "") {
      throw new NewsValidationError("claim evidenceIds must be non-empty strings");
    }
    if (!knownStoryIds.has(id)) {
      throw new NewsValidationError(`claim cites unknown evidence: ${id}`);
    }
    return id;
  });
  return {
    id: requireString(value, "id"),
    text: requireString(value, "text"),
    evidenceIds: ids,
  };
}

function decodeInterpretation(
  value: unknown,
  cutoff: Date,
  knownStoryIds: Set<string>,
  displayableStoryIds: Set<string>,
): NewsInterpretationSection {
  if (!isRecord(value)) {
    throw new NewsValidationError("interpretation must be an object");
  }
  const status = requireString(value, "status");
  if (status !== "available" && status !== "unavailable") {
    throw new NewsValidationError(`interpretation status is unsupported: ${status}`);
  }
  if (!Array.isArray(value.claims)) {
    throw new NewsValidationError("interpretation claims must be an array");
  }
  if (status === "unavailable") {
    if (value.claims.length > 0) {
      throw new NewsValidationError(
        "an unavailable interpretation must not carry conclusions",
      );
    }
    const reason = value.reason;
    if (typeof reason !== "string" || reason.trim() === "") {
      throw new NewsValidationError(
        "an unavailable interpretation must state its reason",
      );
    }
    return { status: "unavailable", reason };
  }

  const generatedAt = parseTimestamp(
    requireString(value, "generatedAt"),
    "interpretation.generatedAt",
  );
  if (generatedAt.getTime() > cutoff.getTime()) {
    throw new NewsValidationError(
      "interpretation.generatedAt is after the snapshot cutoff",
    );
  }
  const evidenceValidUntil = parseTimestamp(
    requireString(value, "evidenceValidUntil"),
    "interpretation.evidenceValidUntil",
  );
  if (evidenceValidUntil.getTime() <= generatedAt.getTime()) {
    throw new NewsValidationError(
      "interpretation.evidenceValidUntil must follow generatedAt",
    );
  }
  const claims = value.claims.map((claim) => decodeClaim(claim, knownStoryIds));
  // A conclusion is shown only when every citation behind it can be opened;
  // one unreachable citation is enough to make the conclusion untraceable.
  const traceable = claims.filter((claim) =>
    claim.evidenceIds.every((id) => displayableStoryIds.has(id)),
  );
  return {
    status: "available",
    model: requireString(value, "model"),
    generatedAt: generatedAt.toISOString(),
    evidenceValidUntil: evidenceValidUntil.toISOString(),
    claims: traceable,
    withheldClaimCount: claims.length - traceable.length,
  };
}

export function decodeNewsBriefingEnvelope(
  value: unknown,
  { now = new Date() }: { now?: Date } = {},
): NewsBriefing {
  if (!isRecord(value)) {
    throw new NewsValidationError("news briefing must be an object");
  }
  if (value.schemaVersion !== "1") {
    throw new NewsValidationError("unsupported news schemaVersion");
  }
  const symbol = normalizeUsSymbol(requireString(value, "symbol"));
  const asOf = parseTimestamp(requireString(value, "asOf"), "asOf");
  if (asOf.getTime() > now.getTime()) {
    throw new NewsValidationError("asOf is in the future");
  }
  const { section: feed, knownStoryIds } = decodeFeed(value.feed, asOf);
  const displayableStoryIds = new Set(
    feed.status === "connected" ? feed.stories.map((story) => story.id) : [],
  );
  return {
    symbol,
    asOf: asOf.toISOString(),
    feed,
    interpretation: decodeInterpretation(
      value.interpretation,
      asOf,
      knownStoryIds,
      displayableStoryIds,
    ),
  };
}
