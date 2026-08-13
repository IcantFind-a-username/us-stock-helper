/**
 * The news surface's model.
 *
 * Two rules shape every type here. A report the reader cannot open is not
 * evidence, so `NewsSource.url` is non-nullable and the decoder is what
 * enforces it. And a moment in time is never approximate: publication and
 * receipt travel separately, because "when it happened" and "when we could
 * have known" are different facts and a reader deciding on freshness needs
 * both.
 */

export type NewsClaimStatus = "verified" | "reported" | "rumor";

export interface NewsSource {
  publisherId: string;
  publisher: string;
  /** A source without an openable link never reaches this type. */
  url: string;
  reliability: number;
  availableAt: string;
  receivedAt: string;
}

export interface NewsStory {
  id: string;
  headline: string;
  claimStatus: NewsClaimStatus;
  /** Publication moment of the earliest copy the reader can open. */
  availableAt: string;
  /** When the app held that copy. */
  receivedAt: string;
  sources: NewsSource[];
  /** Distinct publishers the reader can open, so it can never exceed them. */
  sourceCount: number;
  /** Reports left out because they carried no link. */
  omittedSourceCount: number;
}

export interface NewsClaim {
  id: string;
  text: string;
  /** Every conclusion points at the evidence it stands on; never empty. */
  evidenceIds: string[];
}

export type NewsFeedSection =
  | { status: "connected"; stories: NewsStory[]; hiddenStoryCount: number }
  | { status: "not-connected"; reason: string };

export type NewsInterpretationSection =
  | {
      status: "available";
      model: string;
      generatedAt: string;
      /** After this moment the cited evidence no longer supports the claims. */
      evidenceValidUntil: string;
      claims: NewsClaim[];
      /** Conclusions held back because their evidence was not openable. */
      withheldClaimCount: number;
    }
  | { status: "unavailable"; reason: string };

export interface NewsBriefing {
  symbol: string;
  asOf: string;
  feed: NewsFeedSection;
  interpretation: NewsInterpretationSection;
}

const minute = 60_000;
const hour = 60 * minute;
const day = 24 * hour;

/**
 * What any list of reports needs before it can be ordered.
 *
 * `receivedAt` is optional because not every producer reports it: the decision
 * service cites a report by publication time only. An absent receipt is left
 * absent rather than defaulted to the publication time, which would be a claim
 * about when the app held the report that nobody actually made.
 */
export type RecencyKey = {
  id: string;
  availableAt: string;
  receivedAt?: string;
};

/**
 * The one recency rule both news surfaces obey.
 *
 * Evidence markers are positional, so an unstable order silently renumbers the
 * reports a conclusion points at. Equal timestamps therefore still have to
 * produce one fixed order, which is what the id fallback is for.
 */
export function compareByRecency(left: RecencyKey, right: RecencyKey): number {
  const published =
    Date.parse(right.availableAt) - Date.parse(left.availableAt);
  if (published !== 0) return published;
  // A row that never reported its receipt must not outrank one that did, so an
  // absent receipt sorts as the oldest possible arrival rather than as "now".
  const leftReceived = left.receivedAt ? Date.parse(left.receivedAt) : -Infinity;
  const rightReceived = right.receivedAt
    ? Date.parse(right.receivedAt)
    : -Infinity;
  if (leftReceived !== rightReceived) {
    return rightReceived > leftReceived ? 1 : -1;
  }
  return left.id < right.id ? -1 : left.id > right.id ? 1 : 0;
}

export function orderStoriesByRecency(stories: NewsStory[]): NewsStory[] {
  return [...stories].sort(compareByRecency);
}

/**
 * Returns null rather than a comforting "刚刚" when the elapsed time cannot be
 * computed: an unparseable timestamp or one ahead of the reader's clock is a
 * fault to show, not to smooth over.
 */
export function formatRelativeTime(value: string, now: Date): string | null {
  const published = Date.parse(value);
  if (!Number.isFinite(published)) return null;
  const elapsed = now.getTime() - published;
  if (elapsed < 0) return null;
  if (elapsed < minute) return "刚刚";
  if (elapsed < hour) return `${Math.floor(elapsed / minute)} 分钟前`;
  if (elapsed < day) return `${Math.floor(elapsed / hour)} 小时前`;
  return `${Math.floor(elapsed / day)} 天前`;
}

const pad = (value: number) => String(value).padStart(2, "0");

export function formatAbsoluteUtc(value: string): string | null {
  const parsed = new Date(value);
  const time = parsed.getTime();
  if (!Number.isFinite(time)) return null;
  return (
    `${parsed.getUTCFullYear()}-${pad(parsed.getUTCMonth() + 1)}-` +
    `${pad(parsed.getUTCDate())} ${pad(parsed.getUTCHours())}:` +
    `${pad(parsed.getUTCMinutes())}:${pad(parsed.getUTCSeconds())} UTC`
  );
}

/**
 * Whether the evidence behind an interpretation has outlived its window.
 *
 * An unreadable window counts as expired: the alternative is vouching for a
 * conclusion whose shelf life nobody can establish.
 */
export function isEvidenceExpired(
  interpretation: NewsInterpretationSection,
  now: Date,
): boolean {
  if (interpretation.status !== "available") return false;
  const validUntil = Date.parse(interpretation.evidenceValidUntil);
  if (!Number.isFinite(validUntil)) return true;
  return now.getTime() > validUntil;
}

const firstCircledDigit = 0x2460;
const circledDigitCount = 20;

/** The shared label that ties a conclusion to the story row it came from. */
export function evidenceMarker(index: number): string {
  if (index < 0 || !Number.isInteger(index)) return `[${index + 1}]`;
  return index < circledDigitCount
    ? String.fromCharCode(firstCircledDigit + index)
    : `[${index + 1}]`;
}
