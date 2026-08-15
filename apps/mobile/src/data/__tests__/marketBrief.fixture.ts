import type { MarketBrief, MarketBriefDriverCoverage, MarketDriverCategory } from "@/domain/models";

/**
 * The nine designed driver categories, in the fixed order the server always
 * emits them -- kept here as plain data rather than imported from the
 * decoder, so this fixture stays a description of the wire contract instead
 * of a dependency on the module that reads it.
 */
const ALL_DRIVER_CATEGORIES: MarketDriverCategory[] = [
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

/** Copied verbatim from `market_brief.py`'s `_UNSOURCED_REASON` table. */
const UNSOURCED_DRIVER_REASON: Record<string, string> = {
  breadth: "大盘涨跌家数、新高新低等广度数据源尚未接入。",
  "volatility-options": "波动率与期权持仓数据源尚未接入。",
  sector: "板块轮动强弱数据源尚未接入。",
  "rates-dollar": "利率与美元指数数据源尚未接入。",
  "macro-credit-energy": "信用利差与能源价格数据源尚未接入。",
  "liquidity-correlation": "流动性与相关性压力数据源尚未接入。",
  "broad-market-trend": "大盘趋势判定数据源尚未接入。",
  geopolitics: "地缘政治的独立驱动判定尚未接入，相关报道已计入整体新闻情绪。",
};

export const marketBriefCutoff = "2026-08-15T14:03:00.000Z";

/** `status: "available"`, one sourced category, eight named gaps -- the shape `market-brief-contract.md`'s clean example describes. */
export function marketBriefFixture(
  overrides: Partial<MarketBrief> = {},
): MarketBrief {
  const driverCoverage: MarketBriefDriverCoverage[] = ALL_DRIVER_CATEGORIES.map(
    (category) =>
      category === "news-sentiment"
        ? {
            category,
            available: true,
            conclusion: "偏多",
            actionScore: 0.42,
            missingReason: null,
          }
        : {
            category,
            available: false,
            conclusion: null,
            actionScore: null,
            missingReason: UNSOURCED_DRIVER_REASON[category]!,
          },
  );
  return {
    status: "available",
    reason: null,
    decisionCutoff: marketBriefCutoff,
    marketSession: "regular",
    dataHealth: "fresh",
    sentiment: {
      conclusion: "偏多",
      actionScore: 0.42,
      uncertainty: ["独立来源不足"],
    },
    driverCoverage,
    citations: [
      {
        id: "C1",
        headline: "NVIDIA raises full-year revenue guidance",
        publisher: "reuters",
        url: "https://reuters.example/a",
        availableAt: "2026-08-15T13:44:00.000Z",
        freshnessSeconds: 1140,
        stale: false,
      },
    ],
    sourceGaps: [],
    notes: [],
    ...overrides,
  };
}

/** `status: "unavailable"`, the fail-closed shape: every source failed, nothing invented. */
export function marketBriefUnavailableFixture(
  overrides: Partial<MarketBrief> = {},
): MarketBrief {
  const reason =
    "本次未能读取任何情报源：sec-current-8-k（HTTP 503）、fred-releases（unreachable）";
  const driverCoverage: MarketBriefDriverCoverage[] = ALL_DRIVER_CATEGORIES.map(
    (category) => ({
      category,
      available: false,
      conclusion: null,
      actionScore: null,
      missingReason: "本次没有可读取的情报源，无法给出该驱动的结论。",
    }),
  );
  return {
    status: "unavailable",
    reason,
    decisionCutoff: marketBriefCutoff,
    marketSession: "regular",
    dataHealth: null,
    sentiment: null,
    driverCoverage,
    citations: [],
    sourceGaps: ["sec-current-8-k（HTTP 503）", "fred-releases（unreachable）"],
    notes: [],
    ...overrides,
  };
}
