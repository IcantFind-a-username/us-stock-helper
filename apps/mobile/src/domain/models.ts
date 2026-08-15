export type Horizon = "short" | "swing" | "long";
export type Direction = "bullish" | "neutral" | "bearish";
export type EvidenceKind = "fact" | "inference" | "scenario" | "rumor";
export type RiskPreference = "conservative" | "balanced" | "aggressive";
export type PlanSide = "long" | "short";
export type DataHealth = "fresh" | "stale" | "conflict" | "insufficient";
export type MarketDriverCategory =
  | "news-sentiment"
  | "breadth"
  | "volatility-options"
  | "sector"
  | "rates-dollar"
  | "macro-credit-energy"
  | "liquidity-correlation"
  | "broad-market-trend"
  | "geopolitics";

export type MarketDriverCoverage =
  | "news"
  | "social-sentiment"
  | "breadth"
  | "volatility"
  | "options"
  | "term-structure"
  | "sector-strength"
  | "rates"
  | "yield-curve"
  | "dollar"
  | "macro"
  | "credit"
  | "energy"
  | "commodities"
  | "liquidity"
  | "correlation-stress"
  | "broad-trend"
  | "geopolitics";

export interface Citation {
  id: string;
  title: string;
  publisher: string;
  url: string;
  publishedAt: string;
  firstSeenAt: string;
  kind: EvidenceKind;
}

export interface MarketDriver {
  id: string;
  category: MarketDriverCategory;
  coverage: MarketDriverCoverage[];
  label: string;
  score: number;
  conclusion: string;
  freshness: "fresh" | "stale" | "conflict";
  citationIds: string[];
}

export interface DashboardSnapshot {
  demoData: true;
  horizon: Horizon;
  updatedAt: string;
  marketSession: string;
  dataHealth: DataHealth;
  marketScore: number;
  marketConfidence: number;
  marketScoreChange: number;
  marketConclusion: string;
  marketRationale: string;
  marketAdvice: string;
  marketRiskPosture: string;
  marketInvalidation: string;
  contradictions: string[];
  marketDrivers: MarketDriver[];
  dataHealthCitationIds: string[];
  priorityAlert: AlertThread;
  watchlist: WatchlistQuote[];
  candidates: Candidate[];
}

export interface WatchlistQuote {
  symbol: string;
  price: number;
  changePercent: number;
  direction: Direction;
  summary: string;
}

export interface Candidate {
  symbol: string;
  company: string;
  horizon: Horizon;
  side: PlanSide;
  designation: "asymmetric-upside" | "standard";
  score: number;
  state: "observation" | "action-eligible" | "risk";
  catalyst: string;
  evidenceFreshness: "fresh" | "stale" | "conflict";
  institutionalProxy: string;
  technicalState: string;
  fundamentalState: string;
  volatilityState: string;
  liquidityRisk: "low" | "medium" | "high";
  reason: string;
  counterCase: string;
  invalidation: string;
  evidenceCount: number;
  counterEvidenceCount: number;
  citationIds: string[];
}

/**
 * How far the adviser panel may move an objective score. Mirrors
 * ADVISER_SCORE_CAP in services/analysis_core; the two must stay equal or the
 * app tells the user advisers carry weight the server will never grant them.
 */
export const ADVISER_SCORE_CAP = 3.0;

export type PriceAdjustment = "forward-adjusted" | "unadjusted";

export interface FactorContribution {
  name: string;
  /** null when no source supplied the factor, as opposed to a measured zero. */
  rawValue: number | null;
  weight: number;
  points: number;
  explanation: string;
}

export interface DecisionScore {
  value: number;
  direction: "bullish" | "bearish" | "neutral";
  actionable: boolean;
  methodVersion: string;
  /** Share of the factor weight that had a source. */
  factorCoverage: number;
  unavailableFactors: string[];
  blockedBy: string[];
  contributions: FactorContribution[];
}

export interface DecisionScenario {
  kind: string;
  probability: number;
  priceLow: number;
  priceHigh: number;
  explanation: string;
}

export interface DecisionForecast {
  currentPrice: number;
  methodVersion: string;
  calibrationStatus: string;
  invalidationConditions: string[];
  disclaimer: string;
  cases: DecisionScenario[];
}

export interface DecisionRiskPlan {
  action: "long" | "short" | "watch" | "avoid";
  direction: string;
  entryRange: [number, number] | null;
  invalidationPrice: number | null;
  targetRange: [number, number] | null;
  maxPositionPercent: number;
  leverage: number;
  warnings: string[];
  methodVersion: string;
}

export interface DecisionCitation {
  id: string;
  headline: string;
  publisher: string;
  url: string;
  availableAt: string;
}

/**
 * Why a block of adviser output is or is not on the screen.
 *
 * Three states, not two, and they are never collapsed. `not-requested` means
 * nobody paid for the call; `unavailable` means the model was asked and could
 * not answer. Showing the second as the first would quietly turn a broken
 * model into "no opinion", which is the reading this whole layer exists to
 * prevent.
 */
export type AdviserBlockStatus = "not-requested" | "available" | "unavailable";

export interface AdviserCitation {
  /** The frozen evidence entry this quote was resolved against. */
  evidenceId: string;
  /** Copied verbatim from the source; the server rejects anything it cannot find there. */
  quote: string;
  url: string;
  publisher: string;
  availableAt: string;
  isCounterEvidence: boolean;
}

export interface AdviserConclusion {
  statement: string;
  confidence: string;
  /** Never empty. A conclusion with no source is refused before it gets here. */
  citations: AdviserCitation[];
  counterEvidence: AdviserCitation[];
}

export interface DecisionNewsInterpretation {
  headlineSummary: string;
  crossSourceReading: string;
  investmentImpact: AdviserConclusion[];
  /** Questions the evidence cannot answer, stated rather than filled in. */
  unknowns: string[];
}

export interface CouncilFrameworkOpinion {
  frameworkId: string;
  displayName: string;
  stance: string;
  /** What this framework is known to be blind to on this call. */
  blindSpot: string;
  conclusions: AdviserConclusion[];
}

export interface DecisionAdviserCouncil {
  summary: string;
  opinions: CouncilFrameworkOpinion[];
  baselineScore: number;
  adjustedScore: number;
  /** Zero whenever a hard gate is up: the council never talks past a gate. */
  scoreAdjustment: number;
  objectiveDirection: string;
  actionable: boolean;
  blockedBy: string[];
  disclaimer: string;
}

export interface AdviserBlock<T> {
  status: AdviserBlockStatus;
  /** Set unless the block is available; that is the whole point of it. */
  reason: string | null;
  value: T | null;
}

/** What the call actually spent, read off the response rather than estimated. */
export interface AdviserUsage {
  model: string | null;
  inputTokens: number;
  outputTokens: number;
  cacheCreationInputTokens: number;
  cacheReadInputTokens: number;
  costUsd: number;
}

export interface Decision {
  status: "live" | "unavailable";
  symbol: string;
  horizon: string;
  /** Completed-candle interval used by every technical input in this decision. */
  interval: string;
  decisionCutoff: string;
  /** null when the chain had nothing to score. */
  score: DecisionScore | null;
  /**
   * The engine's own score before any adviser council touched it. Equal to
   * `score` whenever `adviserAdjustment` is null or 0; a reader wanting the
   * pre-adjustment number reads this rather than trying to undo the fold.
   */
  baselineScore: DecisionScore | null;
  /**
   * Null means no adviser council ran for this response -- not a measured
   * zero. A folded, ±ADVISER_SCORE_CAP-clamped number means the council ran:
   * `score.value == baselineScore.value + adviserAdjustment` (clamped to
   * [0,100]) when ungated, or 0.0 with `score.value == baselineScore.value`
   * unchanged when a hard gate voided what the council would have said.
   */
  adviserAdjustment: number | null;
  /** null when volatility could not be measured; notes say why. */
  forecast: DecisionForecast | null;
  riskPlan: DecisionRiskPlan | null;
  citations: DecisionCitation[];
  /** null when the server predates the adviser layer and said nothing at all. */
  newsInterpretation: AdviserBlock<DecisionNewsInterpretation> | null;
  adviserCouncil: AdviserBlock<DecisionAdviserCouncil> | null;
  /** null when no model call reported what it spent. */
  adviserUsage: AdviserUsage | null;
  notes: string[];
}

export type MarketSession = "premarket" | "regular" | "afterhours" | "closed";

export interface MarketBriefSentiment {
  conclusion: string;
  /** Always a measured float; 0.0 when unmeasured (see `dataHealth`/`uncertainty`). */
  actionScore: number;
  /** e.g. "情绪未测量", "来源冲突", "含未证实传闻", "独立来源不足". */
  uncertainty: string[];
}

export interface MarketBriefDriverCoverage {
  category: MarketDriverCategory;
  available: boolean;
  /** null unless `available`. */
  conclusion: string | null;
  /** null unless `available`. */
  actionScore: number | null;
  /** null only when `available`; named otherwise, never invented. */
  missingReason: string | null;
}

export interface MarketBriefCitation {
  id: string;
  headline: string;
  publisher: string;
  url: string;
  availableAt: string;
  /** null only when age was never measured -- not a real production path. */
  freshnessSeconds: number | null;
  stale: boolean | null;
}

/**
 * `GET /market-brief`'s decoded envelope -- the Dashboard's real-mode market
 * hero. Deliberately shaped nothing like `DashboardSnapshot`: no `demoData`,
 * no symbol, no market score, no candidates, no priority alert. That
 * structural distance is what keeps `demoData: true` demo-only by
 * construction -- a decoded brief cannot be mistaken for, or substituted
 * into, the fixture path the Dashboard already renders.
 */
export interface MarketBrief {
  status: "available" | "unavailable";
  /** Set only when `status` is "unavailable"; names every source that failed. */
  reason: string | null;
  decisionCutoff: string;
  marketSession: MarketSession;
  /** null only when `status` is "unavailable". */
  dataHealth: DataHealth | null;
  /** null only when `status` is "unavailable". */
  sentiment: MarketBriefSentiment | null;
  /** Always nine entries, one per designed `MarketDriverCategory`. */
  driverCoverage: MarketBriefDriverCoverage[];
  citations: MarketBriefCitation[];
  sourceGaps: string[];
  /** Point-in-time exclusion disclosures (e.g., events after the decision cutoff). */
  notes: string[];
}

export interface Candle {
  /** Bar-close time. Indicators and patterns may only consume completed bars. */
  timestamp: string;
  /** When the exchange published this close, the earliest a replay may act. */
  availableAt: string;
  /**
   * When the gateway actually held this row; never before availableAt. Absent
   * on demo candles, which never travelled through a provider. The snapshot
   * decoder requires it for live data, where it is the honest bound on what
   * could have been known.
   */
  receivedAt?: string;
  /** Forward-adjusted prices are rewritten by later corporate actions. */
  priceAdjustment?: PriceAdjustment;
  complete: boolean;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ForecastPoint {
  timestamp: string;
  median: number;
  lower50: number;
  upper50: number;
  lower80: number;
  upper80: number;
}

export interface ForecastSnapshot {
  horizon: string;
  points: ForecastPoint[];
  probability: { up: number; flat: number; down: number };
  calibrationError: number;
  predictedAt: string;
  modelVersion: string;
  invalidation: string;
}

export interface RsiSnapshot {
  asOf: string;
  value: number;
  period: number;
  interval: string;
  state: "oversold" | "neutral" | "near-overbought" | "overbought";
  direction: "rising" | "flat" | "falling";
  divergence: "bullish" | "none" | "bearish";
}

export interface MacdSnapshot {
  asOf: string;
  dif: number;
  dea: number;
  interval: string;
  histogram: number[];
  state: "bull-expanding" | "bull-contracting" | "bear-expanding" | "bear-contracting";
  crossover: "golden-cross" | "death-cross" | "none";
}

export interface ReportedOwnership {
  institutionalPercent: number;
  insiderPercent: number;
  otherPercent: number;
  reportedAt: string;
  availableAt: string;
  changes: string[];
  citationIds: string[];
}

export interface ParticipationProxy {
  label: "估算代理";
  institutionalPercent: number;
  retailPercent: number;
  confidence: "low" | "medium" | "high";
  estimatedAt: string;
  methodVersion: string;
  sourceCoverage: string;
  citationIds: string[];
}

export interface MarketContext {
  asOf: string;
  marketDirection: string;
  sectorState: string;
  macroState: string;
  geopoliticalState: string;
  scoreAdjustment: number;
  planChanges: string[];
  citationIds: string[];
}

export interface PatternSignal {
  name: string;
  status: "forming" | "confirmed" | "invalidated";
  complete: boolean;
  invalidation: string;
  horizon: Horizon;
}

export interface FundamentalSnapshot {
  financialHealth: string;
  cash: string;
  debt: string;
  dilution: string;
  runway: string;
  margins: string;
  growth: string;
  valuation: string;
  materialRisks: string[];
  industryContext: string;
  supplyChainContext: string;
  citationIds: string[];
}

export interface StockSnapshot {
  demoData: true;
  symbol: string;
  company: string;
  exchange: string;
  marketSession: string;
  watchlisted: boolean;
  horizon: Horizon;
  price: number;
  changePercent: number;
  quoteLatencyMs: number;
  candles: Candle[];
  forecast: ForecastSnapshot;
  magicNine: {
    count: number;
    complete: boolean;
    direction: "bullish" | "bearish";
    invalidation: string;
    horizon: Horizon;
    /** Explicit fixture points aligned one-for-one with completed candles. */
    series: (MagicNineSeriesPoint | null)[];
  };
  dragonTrend: { state: Direction; score: number; methodVersion: string; invalidation: string };
  patterns: PatternSignal[];
  indicators: { rsi: RsiSnapshot; macd: MacdSnapshot };
  reportedOwnership: ReportedOwnership;
  institutionalHoldings: DelayedInstitutionalHolding[];
  participationProxy: ParticipationProxy;
  marketContext: MarketContext;
  fundamentals: FundamentalSnapshot;
  baseScore: number;
  adjustedScore: number;
  conclusion: string;
  counterCase: string;
  citations: Citation[];
}

export type DataStatus =
  | "live"
  | "partial"
  | "delayed"
  | "stale"
  | "unavailable"
  | "demo";

export type SnapshotSource = {
  source: "moomoo" | "fixture";
  status: DataStatus;
  asOf: string;
  decisionCutoff: string;
};

export interface ParticipationBar {
  closedAt: string;
  mainShare: number | null;
  retailShare: number | null;
  mainActivity: number | null;
  retailActivity: number | null;
  netFlow: number | null;
  coverage: number | null;
  source: string;
  asOf: string;
  availableAt: string;
  methodVersion: "order-size-activity-share-v1";
  qualityStatus: "live" | "unavailable";
  missingReason: string | null;
}

export interface ChartQuote {
  price: number;
  changePercent: number;
  source: string;
  asOf: string;
  availableAt: string;
  methodVersion: string;
  qualityStatus: DataStatus;
}

export interface LiveQuote extends ChartQuote {
  source: "moomoo";
  methodVersion: "provider-quote-v1";
  qualityStatus: "live";
}

/**
 * A drawable indicator series, one value per completed candle in the same
 * order, published by the analysis service under its own method version.
 *
 * The app never derives one of these from candle closes: an indicator drawn
 * from client-side arithmetic would carry no version, no cutoff, and no way to
 * tell a warm-up gap from a real value. `null` marks a bar the method had no
 * value for, so the line breaks there instead of being invented across it.
 */
export interface ChartIndicatorSeries {
  values: (number | null)[];
  source: string;
  asOf: string;
  availableAt: string;
  methodVersion: string;
  qualityStatus: DataStatus;
}

export interface ChartMacdSeries {
  line: (number | null)[];
  signal: (number | null)[];
  histogram: (number | null)[];
  source: string;
  asOf: string;
  availableAt: string;
  methodVersion: string;
  qualityStatus: DataStatus;
}

export interface ChartIndicatorValue {
  value: number | null;
  /** null when the server published only the latest value and no series. */
  series: ChartIndicatorSeries | null;
  source: string;
  asOf: string;
  availableAt: string;
  methodVersion: string;
  qualityStatus: DataStatus;
}

export interface LiveIndicatorValue extends ChartIndicatorValue {
  source: "analysis-core";
  qualityStatus: "live" | "unavailable";
}

/** Realized volatility, or an explicit statement that it cannot be measured. */
export interface LiveVolatilityIndicator extends LiveIndicatorValue {
  sampleSize: number;
  missingReason: string | null;
}

/**
 * 顶分型/底分型/W底/双头/头肩顶/头肩底/回踩五日线企稳（回眸一笑）-- see
 * services/analysis_core/us_stock_helper_core/patterns_shapes.py, whose
 * module docstring is the versioned spec every rule here implements.
 */
export type PatternShapeKind =
  | "fractal_top"
  | "fractal_bottom"
  | "double_bottom"
  | "double_top"
  | "head_shoulders_top"
  | "head_shoulders_bottom"
  | "ma5_pullback";

export type PatternShapeStatus = "forming" | "confirmed" | "invalidated";

export interface PatternShapeBarRef {
  index: number;
  closedAt: string;
}

/** Three-layer reading: 一句话含义 / 展开解释 / honesty line, fixed server-side copy. */
export interface PatternShapeReading {
  summary: string;
  detail: string;
  /** Fixed until the phase-2 backtest attaches real hit rates: "历史胜率待回测". */
  honesty: string;
}

export interface PatternShapeSignal {
  kind: PatternShapeKind;
  name: string;
  status: PatternShapeStatus;
  direction: "bullish" | "bearish";
  /** Structural bars (pivots/shoulders/touch bar…) in chronological order. */
  bars: PatternShapeBarRef[];
  /** Index (into completedCandles) a chart marker should anchor to. */
  anchorIndex: number;
  /** Bar index this status became true at (confirmed/invalidated), or "as of" for forming. */
  eventIndex: number;
  invalidation: string;
  explanation: string;
  reading: PatternShapeReading;
  methodVersion: "patterns-shapes-v1";
}

export interface PatternShapeDetection {
  detector: "fractal" | "double_extreme" | "head_and_shoulders" | "ma5_pullback";
  minimumWindow: number;
  sampleSize: number;
  qualityStatus: "live" | "unavailable";
  missingReason: string | null;
  methodVersion: "patterns-shapes-v1";
  signals: PatternShapeSignal[];
}

/** All four shape detectors' results for one snapshot's completed bars. */
export interface LivePatternShapesIndicator {
  source: "analysis-core";
  asOf: string;
  availableAt: string;
  methodVersion: "patterns-shapes-v1";
  qualityStatus: "live" | "unavailable";
  detections: PatternShapeDetection[];
}

export interface ChartMacdIndicator {
  line: number | null;
  signal: number | null;
  histogram: number | number[] | null;
  /** null when the server published only the latest values and no series. */
  series: ChartMacdSeries | null;
  source: string;
  asOf: string;
  availableAt: string;
  methodVersion: string;
  qualityStatus: DataStatus;
}

export interface LiveMacdIndicator extends ChartMacdIndicator {
  histogram: number | null;
  source: "analysis-core";
  methodVersion: "macd-12-26-9-v1";
  qualityStatus: "live" | "unavailable";
}

export interface CompletedTdSetup {
  direction: "bullish" | "bearish";
  confirmedAtIndex: number;
  perfected: boolean;
  barsSince: number;
}

export interface MagicNineSeriesPoint {
  direction: "bullish" | "bearish";
  count: number;
}

export interface ChartMagicNineSnapshot {
  direction: string | null;
  count: number;
  /** One server-published TD count per completed candle; null outside a run. */
  series: (MagicNineSeriesPoint | null)[] | null;
  completed: boolean;
  /** null when the bar 8/9 comparison was not performed. */
  perfected: boolean | null;
  confirmedAtIndex: number | null;
  /** Counting restarts after a nine, so the finished run is carried here. */
  lastCompleted: CompletedTdSetup | null;
  source: string;
  asOf: string;
  availableAt: string;
  methodVersion: string;
  qualityStatus: DataStatus;
}

export interface MagicNineSnapshot extends ChartMagicNineSnapshot {
  source: "analysis-core";
  qualityStatus: "live" | "unavailable";
}

export interface DelayedInstitutionalHolding {
  period: string;
  reportedAt: string;
  reportedAtBasis: "reporting-period-end";
  availableAt: string;
  source: "moomoo-delayed-institutional-disclosure";
  institutionCount: number;
  institutionCountChange: number;
  sharesHeld: number;
  sharesHeldChange: number;
  holdingPercent: number;
  holdingPercentChange: number;
  asOf: string;
  methodVersion:
    | "reported-holdings-v1"
    | "reported-holdings-v2-anomaly-aware";
  qualityStatus: "delayed";
}

export interface SnapshotProvenance {
  source: string;
  asOf: string;
  availableAt: string;
  methodVersion: string;
  qualityStatus: DataStatus;
}

export type SnapshotAvailability =
  | "live"
  | "delayed"
  | "stale"
  | "unavailable";

export type SnapshotQuality =
  | "validated"
  | "partial"
  | "anomalous"
  | "invalid";

export type SnapshotCompatibility = "v3" | "v2-fallback";

export interface SnapshotSection<T> {
  availabilityStatus: SnapshotAvailability;
  qualityStatus: SnapshotQuality;
  source: string | null;
  asOf: string | null;
  availableAt: string | null;
  receivedAt: string | null;
  data: T | null;
  errorCode: string | null;
  reason: string | null;
  warnings: string[];
  anomalies: { code: string; reason: string; rowIndex?: number }[];
  methodVersion: string;
}

export type SnapshotSectionName =
  | "quote"
  | "candles"
  | "technical"
  | "currentSessionFlow"
  | "holdings"
  | "fundamentals"
  | "marketContext"
  | "news"
  | "forecastDecision";

export interface NormalizedCapitalFlowPoint {
  timestamp: string;
  availableAt: string;
  session: string;
  totalNetFlow: number;
  extraLargeOrderNetFlow: number;
  largeOrderNetFlow: number;
  mediumOrderNetFlow: number;
  smallOrderNetFlow: number;
  largeOrderProxyNetFlow: number;
  institutionalIdentity: false;
}

export interface LiveTechnicalIndicators {
  ma5: LiveIndicatorValue;
  rsi: LiveIndicatorValue;
  macd: LiveMacdIndicator;
  volatility: LiveVolatilityIndicator;
  patternShapes: LivePatternShapesIndicator;
}

export interface StockSnapshotSections {
  quote: SnapshotSection<LiveQuote>;
  candles: SnapshotSection<{
    candles: Candle[];
    priceAdjustment: PriceAdjustment;
  }>;
  technical: SnapshotSection<{
    indicators: LiveTechnicalIndicators;
    magicNine: MagicNineSnapshot;
  }>;
  currentSessionFlow: SnapshotSection<NormalizedCapitalFlowPoint[]>;
  holdings: SnapshotSection<DelayedInstitutionalHolding[]>;
  fundamentals: SnapshotSection<unknown>;
  marketContext: SnapshotSection<unknown>;
  news: SnapshotSection<unknown>;
  forecastDecision: SnapshotSection<unknown>;
}

export interface ChartSnapshot {
  demoData: boolean;
  source: SnapshotSource;
  symbol: string;
  interval: string;
  quote: ChartQuote | null;
  candles: Candle[];
  participationBars: ParticipationBar[];
  indicators: {
    ma5: ChartIndicatorValue;
    rsi: ChartIndicatorValue;
    macd: ChartMacdIndicator;
  };
  magicNine: ChartMagicNineSnapshot;
  forecast: ForecastSnapshot | null;
  institutionalHoldings?: DelayedInstitutionalHolding[];
}

export interface LiveStockSnapshot extends ChartSnapshot {
  demoData: false;
  source: SnapshotSource & {
    source: "moomoo";
    status: "live" | "partial";
  };
  snapshotStatus: "live" | "partial";
  compatibility: SnapshotCompatibility;
  requestedCount: number;
  requestedSections: SnapshotSectionName[];
  sections: StockSnapshotSections;
  decisionCutoff: string;
  priceAdjustment: PriceAdjustment | null;
  quote: LiveQuote | null;
  indicators: LiveTechnicalIndicators;
  magicNine: MagicNineSnapshot;
  institutionalHoldings: DelayedInstitutionalHolding[];
  provenance: SnapshotProvenance[];
  warnings: string[];
}

export interface DemoChartSnapshot extends ChartSnapshot {
  demoData: true;
  source: SnapshotSource & { source: "fixture"; status: "demo" };
  quote: ChartQuote;
  institutionalHoldings: DelayedInstitutionalHolding[];
}

/** Converts the existing, explicitly demo-only fixture model for chart consumers. */
export function toDemoChartSnapshot(stock: StockSnapshot): DemoChartSnapshot {
  const asOf = stock.indicators.rsi.asOf;
  const fixtureMetadata = {
    source: "fixture",
    asOf,
    availableAt: asOf,
    methodVersion: "demo-fixture-v1",
    qualityStatus: "demo" as const,
  };
  return {
    demoData: true,
    source: {
      source: "fixture",
      status: "demo",
      asOf,
      decisionCutoff: asOf,
    },
    symbol: stock.symbol,
    interval:
      stock.indicators.rsi.interval === "周线"
        ? "week"
        : stock.indicators.rsi.interval === "日线"
          ? "day"
          : "5m",
    quote: {
      ...fixtureMetadata,
      price: stock.price,
      changePercent: stock.changePercent,
    },
    candles: stock.candles,
    participationBars: [],
    indicators: {
      // The demo fixture carries latest values only. Synthesising a series here
      // would be the app drawing an indicator it computed itself, so the chart
      // says the series is missing instead.
      ma5: { ...fixtureMetadata, value: null, series: null },
      rsi: {
        ...fixtureMetadata,
        value: stock.indicators.rsi.value,
        series: null,
      },
      macd: {
        ...fixtureMetadata,
        line: stock.indicators.macd.dif,
        signal: stock.indicators.macd.dea,
        histogram: stock.indicators.macd.histogram,
        series: null,
      },
    },
    magicNine: {
      ...fixtureMetadata,
      direction: stock.magicNine.direction,
      count: stock.magicNine.count,
      // Demo data is fictional by definition, but it still carries a complete,
      // explicit series so the chart exercises the same rendering contract as
      // a live server response. The phone does not derive these from closes.
      series: stock.magicNine.series,
      completed: stock.magicNine.complete,
      perfected: false,
      confirmedAtIndex:
        stock.magicNine.count > 0 ? stock.candles.length - 1 : null,
      lastCompleted: stock.magicNine.complete
        ? {
            direction: stock.magicNine.direction,
            confirmedAtIndex: stock.candles.length - 1,
            perfected: false,
            barsSince: 0,
          }
        : null,
    },
    forecast: stock.forecast,
    institutionalHoldings: stock.institutionalHoldings,
  };
}

export interface AdviserOpinion {
  id: string;
  displayName: string;
  focus: string;
  direction: Direction;
  confidence: number;
  active: boolean;
  abstained: boolean;
  thesis: string;
  counterargument: string;
  evidenceIds: string[];
}

export interface TradePlan {
  id: string;
  symbol: string;
  horizon: Horizon;
  side: PlanSide;
  preference: RiskPreference;
  objectiveScore: number;
  confidence: number;
  entryMethod: string;
  entryRange: [number, number];
  quantity: number;
  riskBudgetPercent: number;
  leverage: number;
  maximumLeverage: number;
  invalidationPrice: number;
  stopLogic: string;
  targetRange: [number, number];
  estimatedRewardRisk: number;
  holdingWindow: string;
  cancelConditions: string[];
  riskWarning: string;
  evidenceSnapshotId: string;
  generatedAt: string;
  methodVersion: string;
  citationIds: string[];
  shortRisk: {
    borrowAvailable: boolean;
    checkedAt: string;
    estimatedBorrowFeePercent: number;
    shortInterestPercent: number;
    crowding: "low" | "medium" | "high";
    warnings: string[];
  } | null;
}

export interface AlertThread {
  id: string;
  symbol: string;
  horizon: Horizon;
  severity: "info" | "observation" | "action" | "risk";
  title: string;
  summary: string;
  triggeredAt: string;
  sourceFreshness: "fresh" | "stale" | "conflict";
  sourceCoverage: string;
  currentState: string;
  invalidation: string;
  baseScoreContribution: number;
  adviserAdjustment: number | null;
  evidenceCount: number;
  counterEvidenceCount: number;
  updatedAt: string;
  citations: Citation[];
}

export interface JournalEntry {
  id: string;
  symbol: string;
  side: PlanSide;
  quantity: number;
  executionPrice: number;
  executedAt: string;
  executionDelaySeconds: number;
  pnl: number;
  pnlState: "realized" | "unrealized";
  decision: "followed" | "overridden";
  slippage: number;
  notes: string;
}

export interface ConversationSection {
  title:
    | "客观结论"
    | "证据"
    | "最强反证"
    | "缺失信息与不确定性"
    | "个性化风险场景"
    | "引用";
  body: string;
}

export interface ConversationTurn {
  id: string;
  role: "user" | "assistant";
  text?: string;
  sections?: ConversationSection[];
  citationIds: string[];
}
