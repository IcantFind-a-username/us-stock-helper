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

export interface Candle {
  timestamp: string;
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
  value: number;
  period: number;
  interval: string;
  state: "oversold" | "neutral" | "near-overbought" | "overbought";
  direction: "rising" | "flat" | "falling";
  divergence: "bullish" | "none" | "bearish";
}

export interface MacdSnapshot {
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
