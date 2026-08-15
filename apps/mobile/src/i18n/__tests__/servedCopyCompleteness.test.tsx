import { describe, expect, it, jest } from "@jest/globals";
import { render } from "@testing-library/react-native";

import {
  decodeDecisionEnvelope,
  decodeMarketBriefEnvelope,
} from "@/data/analysisGateway";
import { useColorScheme } from "@/hooks/use-color-scheme";

import { DecisionCard } from "@/components/stock/DecisionCard";
import { DecisionNewsSection } from "@/components/news/DecisionNewsSection";
import { MarketBriefCard } from "@/components/dashboard/MarketBriefCard";

jest.mock("@/hooks/use-color-scheme", () => ({
  useColorScheme: jest.fn(() => "light"),
}));
(useColorScheme as jest.MockedFunction<typeof useColorScheme>).mockReturnValue(
  "light",
);

/**
 * The served-copy Chinese sweep's completeness gate (2026-08-15).
 *
 * Real-mode screens leaked code-log-style English from server prose
 * channels: factor detail strings, the "adviser" factor identifier, and
 * notes like "geopolitics unavailable (no_qualified_source)." (Franz's
 * real-mode QA). Every fixture below is built from the server's *current*
 * vocabulary -- the exact strings services/analysis_core, services/
 * analysis_api and services/information_layer emit today, post-sweep -- run
 * through the real wire decoders and the real screen components, so a
 * regression (a new unmapped English sentence, or an old one drifting back
 * to English at the source) fails here rather than shipping.
 *
 * This is deliberately not a fuzz test: it does not invent server strings.
 * It pins the reachable states this sweep found and fixed.
 */

const NOW = new Date("2026-08-15T16:00:10.000Z");

/**
 * Technical tokens the reader does understand, or that the plan's own
 * allowlist names outright (tickers, company names, version ids, source
 * ids, URLs, "moomoo", "Claude", timestamps). Compared case-insensitively.
 */
const ALLOWED_TOKENS = new Set(
  [
    "NVDA",
    "RSI",
    "MACD",
    "SDK",
    "HTTP",
    "SEC",
    "UTC",
    "moomoo",
    "Claude",
    // Source ids named in a decision's or a brief's gap disclosures --
    // stable identifiers, not prose (information_layer/feeds/registry.py).
    "sec-current-8-k",
    "federal-reserve-press",
  ].map((token) => token.toLowerCase()),
);

/** True for a token this sweep's allowlist covers without an exact entry. */
function isAllowedByShape(token: string): boolean {
  // Version ids and technical identifiers carry a digit
  // ("explainable-horizon-score-v1", "claude-opus-4-8", "evt-1"); an ISO
  // timestamp fragment does too. Prose never does in this vocabulary.
  if (/\d/.test(token)) return true;
  // Full timestamps and URLs are checked as substrings below, not as single
  // tokens, since punctuation the word regex does not capture (":", "/",
  // ".") is part of what makes them recognizable as provenance.
  return false;
}

/**
 * Every run of Latin letters/digits/hyphens (3+ chars, starting with a
 * letter) that is neither an allowlisted technical token nor part of a URL
 * or ISO timestamp already stripped out. What remains is unmapped English
 * prose -- exactly the failure mode this sweep exists to catch.
 */
function unmappedEnglish(text: string): string[] {
  const withoutUrls = text.replace(/https?:\/\/\S+/g, " ");
  const withoutTimestamps = withoutUrls.replace(
    /\d{4}-\d{2}-\d{2}T[\d:.]+Z?/g,
    " ",
  );
  const tokens = withoutTimestamps.match(/[A-Za-z][A-Za-z0-9-]{2,}/g) ?? [];
  return tokens.filter(
    (token) =>
      !ALLOWED_TOKENS.has(token.toLowerCase()) && !isAllowedByShape(token),
  );
}

function collectText(node: unknown): string {
  if (node === null || node === undefined || typeof node === "boolean") {
    return "";
  }
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(collectText).join(" ");
  if (typeof node === "object" && "children" in (node as { children?: unknown })) {
    return collectText((node as { children?: unknown }).children);
  }
  return "";
}

function assertNoUnmappedEnglish(view: { toJSON(): unknown }) {
  const text = collectText(view.toJSON());
  const offenders = unmappedEnglish(text);
  expect(offenders).toEqual([]);
}

// ---------------------------------------------------------------------------
// Decision fixtures -- one JSON payload per reachable real-mode state,
// decoded through the real wire decoder exactly as the app receives it.
// ---------------------------------------------------------------------------

function measuredFactor(name: string, explanation: string) {
  return { name, rawValue: 0.4, weight: 0.2, points: 2.5, explanation };
}

function unavailableFactor(name: string, explanation: string) {
  return { name, rawValue: null, weight: 0, points: 0, explanation };
}

/** Every scoring.py explanation, current as of the 2026-08-15 sweep. */
const FACTOR_EXPLANATIONS: Record<string, string> = {
  technical_trend: "按周期对应的回看窗口，用已收盘K线计算涨跌幅。",
  momentum: "RSI 与 MACD 动量，只用已收盘K线计算。",
  pattern:
    "只计入收盘确认、且失效条件尚未触发的形态证据：确认后一旦收盘越过失效价位（如W底跌回颈线下方），该形态即停止计分；多个形态并存时取幅度最大者，幅度相同取最新。未确认的形态贡献为零。",
  market_sentiment: "按当时可见的市场情绪，结合引用的新闻证据。",
  macro: "按当时可见的宏观经济背景，作为软因子处理。",
  geopolitics: "按当时可见的地缘政治背景，作为软因子处理。",
  institutional_flow:
    "融合日内大单资金净流入占比的估算代理与机构持仓变动趋势（按披露日期计入），不声称掌握隐藏订单信息。",
  fundamentals: "按当时可见的公司财务状况。",
};

function availableDecisionPayload() {
  return {
    schemaVersion: "1",
    status: "live",
    symbol: "NVDA",
    horizon: "short",
    interval: "day",
    decisionCutoff: "2026-08-15T15:59:00.000Z",
    score: {
      value: 68.4,
      direction: "bullish",
      actionable: true,
      methodVersion: "explainable-horizon-score-v2",
      factorCoverage: 0.7,
      unavailableFactors: [
        "fundamentals",
        "geopolitics",
        "institutional_flow",
        "macro",
      ],
      blockedBy: [],
      contributions: [
        measuredFactor("technical_trend", FACTOR_EXPLANATIONS.technical_trend!),
        measuredFactor("momentum", FACTOR_EXPLANATIONS.momentum!),
        measuredFactor("pattern", FACTOR_EXPLANATIONS.pattern!),
        measuredFactor(
          "market_sentiment",
          FACTOR_EXPLANATIONS.market_sentiment!,
        ),
        unavailableFactor(
          "macro",
          `${FACTOR_EXPLANATIONS.macro}本次快照不可用。`,
        ),
        unavailableFactor(
          "geopolitics",
          `${FACTOR_EXPLANATIONS.geopolitics}本次快照不可用。`,
        ),
        unavailableFactor(
          "institutional_flow",
          `${FACTOR_EXPLANATIONS.institutional_flow}本次快照不可用。`,
        ),
        unavailableFactor(
          "fundamentals",
          `${FACTOR_EXPLANATIONS.fundamentals}本次快照不可用。`,
        ),
        // scoring.py's ninth contribution, outside the FeatureSet the other
        // eight names come from -- the bare "adviser" identifier Franz's
        // real-mode QA reported on the stock page's factor card title.
        measuredFactor(
          "adviser",
          "顾问软因子设有上限：最多影响 ±3 分，且不能绕过任何硬性拦截。",
        ),
      ],
    },
    baselineScore: null,
    adviserAdjustment: null,
    forecast: {
      currentPrice: 119.5,
      methodVersion: "bounded-scenario-forecast-v1",
      calibrationStatus: "uncalibrated",
      calibrationReference: null,
      invalidationConditions: ["引用的证据被撤回或被证伪。"],
      disclaimer: "Scenarios are uncertain analytical ranges, not promised prices.",
      cases: [
        {
          kind: "bear",
          probability: 0.2,
          priceLow: 112.0,
          priceHigh: 117.0,
          explanation: "按已实现波动率与当前证据评分推算的不利区间。",
        },
        {
          kind: "base",
          probability: 0.4,
          priceLow: 117.0,
          priceHigh: 122.0,
          explanation: "中性不确定区间；不是单一价格的预测。",
        },
        {
          kind: "bull",
          probability: 0.4,
          priceLow: 122.0,
          priceHigh: 128.0,
          explanation: "按已实现波动率与当前证据评分推算的有利区间。",
        },
      ],
    },
    riskPlan: {
      action: "long",
      direction: "bullish",
      entryRange: [118.3, 120.1],
      invalidationPrice: 114.7,
      targetRange: [122.0, 128.0],
      maxPositionPercent: 10,
      leverage: 1.1,
      warnings: [
        "Analysis only: this plan cannot submit, route, or execute an order.",
        "Hard gate active: stale_data, insufficient_evidence",
      ],
      blockedBy: [],
      methodVersion: "analysis-only-risk-plan-v1",
    },
    sentiment: {
      conclusion: "偏多",
      actionScore: 0.6,
      decisionSignal: "long_bias",
      uncertainty: ["独立来源不足"],
    },
    citations: [],
    newsInterpretation: null,
    adviserCouncil: null,
    adviserUsage: null,
    notes: [
      "Scored on 70% of the factor weight; the rest has no source yet.",
      // The exact strings Franz's 2026-08-15 real-mode QA reported.
      "geopolitics unavailable (no_qualified_source).",
      "institutional_flow unavailable (no_qualified_source).",
      "3 cited item(s) are older than the configured freshness window and are marked stale.",
      "本次没有召开顾问委员会，顾问调整为空，而非测得的零。",
    ],
  };
}

function unavailableDecisionPayload() {
  return {
    schemaVersion: "1",
    status: "unavailable",
    symbol: "NVDA",
    horizon: "short",
    interval: "day",
    decisionCutoff: "2026-08-15T15:59:00.000Z",
    score: null,
    baselineScore: null,
    adviserAdjustment: null,
    forecast: null,
    riskPlan: null,
    sentiment: null,
    citations: [],
    newsInterpretation: null,
    adviserCouncil: null,
    adviserUsage: null,
    notes: ["No completed candles were available at the decision cutoff."],
  };
}

function blockedDecisionPayload() {
  const base = availableDecisionPayload();
  return {
    ...base,
    score: {
      ...base.score,
      actionable: false,
      blockedBy: ["stale_data", "insufficient_evidence"],
    },
    forecast: null,
    riskPlan: null,
    notes: [
      "Realized volatility could not be measured, so no scenario range is offered.",
    ],
  };
}

describe("DecisionCard renders every reachable real-mode state in Chinese", () => {
  it("an available decision with mixed factor coverage, notes, forecast and risk plan", async () => {
    const decision = decodeDecisionEnvelope(availableDecisionPayload(), {
      now: NOW,
    });

    const view = await render(<DecisionCard decision={decision} />);

    assertNoUnmappedEnglish(view);
  });

  it("an unavailable decision", async () => {
    const decision = decodeDecisionEnvelope(unavailableDecisionPayload(), {
      now: NOW,
    });

    const view = await render(<DecisionCard decision={decision} />);

    assertNoUnmappedEnglish(view);
  });

  it("a blocked decision with no forecast or risk plan", async () => {
    const decision = decodeDecisionEnvelope(blockedDecisionPayload(), {
      now: NOW,
    });

    const view = await render(<DecisionCard decision={decision} />);

    assertNoUnmappedEnglish(view);
  });
});

// ---------------------------------------------------------------------------
// The model-interpretation card's reason states, current as of
// adviser_provider.py's 2026-08-15 sweep.
// ---------------------------------------------------------------------------

const ADVISER_REASONS = [
  "决策链没有得出结论，因此没有召开顾问委员会，也没有产生任何花费。",
  "本次部署没有安装顾问层（无法导入模型 SDK），因此没有产生解读。",
  "顾问层出现了本服务不会原样转述的失败，因为这类信息可能带有外发凭据。没有产生解读。",
  "本次没有召开顾问委员会，顾问调整为空，而非测得的零。",
];

describe("DecisionInterpretationCard renders every adviser reason in Chinese", () => {
  it.each(ADVISER_REASONS)("reason: %s", async (reason) => {
    const decision = decodeDecisionEnvelope(
      {
        ...availableDecisionPayload(),
        newsInterpretation: { status: "unavailable", reason, value: null },
      },
      { now: NOW },
    );

    const view = await render(
      <DecisionNewsSection decision={decision} errorCategory={null} symbol="NVDA" />,
    );

    assertNoUnmappedEnglish(view);
  });
});

// ---------------------------------------------------------------------------
// GET /market-brief -- available and fail-closed unavailable shapes, current
// as of market_brief.py and evidence_provider.py's Chinese gap reasons.
// ---------------------------------------------------------------------------

const ALL_DRIVER_CATEGORIES = [
  "news-sentiment",
  "breadth",
  "volatility-options",
  "sector",
  "rates-dollar",
  "macro-credit-energy",
  "liquidity-correlation",
  "broad-market-trend",
  "geopolitics",
] as const;

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

function availableBriefPayload() {
  return {
    schemaVersion: "1",
    status: "available",
    reason: null,
    decisionCutoff: "2026-08-15T15:59:00.000Z",
    marketSession: "regular",
    dataHealth: "fresh",
    sentiment: {
      conclusion: "偏多",
      actionScore: 0.42,
      uncertainty: ["独立来源不足"],
    },
    driverCoverage: ALL_DRIVER_CATEGORIES.map((category) =>
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
    ),
    citations: [],
    // collector.py's `_reason()` (2026-08-15 sweep): the gap's reason is
    // Chinese, only the source id itself stays a technical identifier.
    sourceGaps: ["federal-reserve-press（无法连接）"],
    notes: ["有 1 条证据在决策截点之后才可用，未纳入本次结论：evt-1"],
  };
}

function unavailableBriefPayload() {
  return {
    schemaVersion: "1",
    status: "unavailable",
    reason: "本次未能读取任何情报源：federal-reserve-press（无法连接）",
    decisionCutoff: "2026-08-15T15:59:00.000Z",
    marketSession: "regular",
    dataHealth: null,
    sentiment: null,
    driverCoverage: ALL_DRIVER_CATEGORIES.map((category) => ({
      category,
      available: false,
      conclusion: null,
      actionScore: null,
      missingReason: "本次没有可读取的情报源，无法给出该驱动的结论。",
    })),
    citations: [],
    sourceGaps: ["federal-reserve-press（无法连接）"],
    notes: [],
  };
}

describe("MarketBriefCard renders every reachable real-mode state in Chinese", () => {
  it("an available brief with an evidence-gap note and a source gap", async () => {
    const brief = decodeMarketBriefEnvelope(availableBriefPayload(), {
      now: NOW,
    });

    const view = await render(
      <MarketBriefCard
        brief={brief}
        error={null}
        onRetry={() => {}}
        status="live"
      />,
    );

    assertNoUnmappedEnglish(view);
  });

  it("the fail-closed unavailable brief", async () => {
    const brief = decodeMarketBriefEnvelope(unavailableBriefPayload(), {
      now: NOW,
    });

    const view = await render(
      <MarketBriefCard
        brief={brief}
        error={null}
        onRetry={() => {}}
        status="unavailable"
      />,
    );

    assertNoUnmappedEnglish(view);
  });
});

describe("the completeness check itself", () => {
  it("still catches unmapped English prose", () => {
    expect(unmappedEnglish("geopolitics unavailable")).toEqual([
      "geopolitics",
      "unavailable",
    ]);
  });

  it("does not flag allowlisted technical tokens", () => {
    expect(
      unmappedEnglish(
        "NVDA · moomoo · Claude · RSI MACD SDK HTTP explainable-horizon-score-v1 " +
          "sec-current-8-k federal-reserve-press https://reuters.example/a " +
          "2026-08-15T15:59:00.000Z",
      ),
    ).toEqual([]);
  });
});
