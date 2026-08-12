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
  magicNine: { count: number; complete: boolean; invalidation: string; horizon: Horizon };
  dragonTrend: { state: Direction; score: number; methodVersion: string; invalidation: string };
  patterns: PatternSignal[];
  indicators: { rsi: RsiSnapshot; macd: MacdSnapshot };
  reportedOwnership: ReportedOwnership;
  participationProxy: ParticipationProxy;
  marketContext: MarketContext;
  fundamentals: FundamentalSnapshot;
  baseScore: number;
  adjustedScore: number;
  conclusion: string;
  counterCase: string;
  citations: Citation[];
}

export type DataStatus = "live" | "delayed" | "stale" | "unavailable" | "demo";

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
  coverage: number;
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

export interface ChartIndicatorValue {
  value: number | null;
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

export interface ChartMacdIndicator {
  line: number | null;
  signal: number | null;
  histogram: number | number[] | null;
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

export interface ChartMagicNineSnapshot {
  direction: string | null;
  count: number;
  completed: boolean;
  perfected: boolean;
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
  methodVersion: "reported-holdings-v1";
  qualityStatus: "delayed";
}

export interface SnapshotProvenance {
  source: string;
  asOf: string;
  availableAt: string;
  methodVersion: string;
  qualityStatus: DataStatus;
}

export interface ChartSnapshot {
  demoData: boolean;
  source: SnapshotSource;
  symbol: string;
  interval: string;
  quote: ChartQuote;
  candles: Candle[];
  participationBars: ParticipationBar[];
  indicators: {
    ma5: ChartIndicatorValue;
    rsi: ChartIndicatorValue;
    macd: ChartMacdIndicator;
  };
  magicNine: ChartMagicNineSnapshot;
  forecast: ForecastSnapshot | null;
}

export interface LiveStockSnapshot extends ChartSnapshot {
  demoData: false;
  source: SnapshotSource & { source: "moomoo"; status: "live" };
  decisionCutoff: string;
  priceAdjustment: PriceAdjustment;
  quote: LiveQuote;
  indicators: {
    ma5: LiveIndicatorValue;
    rsi: LiveIndicatorValue;
    macd: LiveMacdIndicator;
    volatility: LiveVolatilityIndicator;
  };
  magicNine: MagicNineSnapshot;
  institutionalHoldings: DelayedInstitutionalHolding[];
  provenance: SnapshotProvenance[];
  warnings: string[];
}

export interface DemoChartSnapshot extends ChartSnapshot {
  demoData: true;
  source: SnapshotSource & { source: "fixture"; status: "demo" };
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
    interval: `demo-${stock.horizon}`,
    quote: {
      ...fixtureMetadata,
      price: stock.price,
      changePercent: stock.changePercent,
    },
    candles: stock.candles,
    participationBars: [],
    indicators: {
      ma5: { ...fixtureMetadata, value: null },
      rsi: { ...fixtureMetadata, value: stock.indicators.rsi.value },
      macd: {
        ...fixtureMetadata,
        line: stock.indicators.macd.dif,
        signal: stock.indicators.macd.dea,
        histogram: stock.indicators.macd.histogram,
      },
    },
    magicNine: {
      ...fixtureMetadata,
      direction: null,
      count: stock.magicNine.count,
      completed: stock.magicNine.complete,
      perfected: false,
      confirmedAtIndex: null,
      lastCompleted: null,
    },
    forecast: stock.forecast,
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
