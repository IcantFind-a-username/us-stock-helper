const cutoff = "2026-07-25T16:00:00.000Z";

export function decisionFixture() {
  return {
    schemaVersion: "1",
    status: "live" as "live" | "unavailable",
    symbol: "NVDA",
    horizon: "short",
    interval: "day",
    decisionCutoff: cutoff,
    score: {
      value: 72.5,
      direction: "bullish",
      actionable: true,
      methodVersion: "explainable-horizon-score-v1",
      factorCoverage: 0.7,
      unavailableFactors: [
        "fundamentals",
        "geopolitics",
        "institutional_flow",
        "macro",
      ],
      blockedBy: [] as string[],
      contributions: [
        {
          name: "technical_trend",
          rawValue: 0.57 as number | null,
          weight: 0.36,
          points: 10.1,
          explanation: "Closed-bar return over the horizon-specific lookback.",
        },
        {
          name: "macro",
          rawValue: null as number | null,
          weight: 0,
          points: 0,
          explanation: "As-of macroeconomic context. Unavailable for this snapshot.",
        },
      ],
    } as Record<string, unknown> | null,
    // Identical to `score` by default: nobody asked for the adviser council,
    // so nothing folded an adjustment in and the two describe the same
    // computation, exactly as the wire contract's "council off" example
    // shows (server: adviser-adjustment-contract.md).
    baselineScore: {
      value: 72.5,
      direction: "bullish",
      actionable: true,
      methodVersion: "explainable-horizon-score-v1",
      factorCoverage: 0.7,
      unavailableFactors: [
        "fundamentals",
        "geopolitics",
        "institutional_flow",
        "macro",
      ],
      blockedBy: [] as string[],
      contributions: [
        {
          name: "technical_trend",
          rawValue: 0.57 as number | null,
          weight: 0.36,
          points: 10.1,
          explanation: "Closed-bar return over the horizon-specific lookback.",
        },
        {
          name: "macro",
          rawValue: null as number | null,
          weight: 0,
          points: 0,
          explanation: "As-of macroeconomic context. Unavailable for this snapshot.",
        },
      ],
    } as Record<string, unknown> | null,
    // Null, not zero: no adviser council ran for this response by default.
    adviserAdjustment: null as number | null,
    forecast: {
      currentPrice: 119.5,
      methodVersion: "bounded-scenario-forecast-v1",
      calibrationStatus: "uncalibrated",
      calibrationReference: null,
      invalidationConditions: ["The cited evidence is withdrawn."],
      disclaimer: "Scenarios are uncertain analytical ranges, not promised prices.",
      cases: [
        {
          kind: "bear",
          probability: 0.2,
          priceLow: 112.0,
          priceHigh: 117.0,
          explanation: "Adverse range.",
        },
        {
          kind: "base",
          probability: 0.4,
          priceLow: 117.0,
          priceHigh: 122.0,
          explanation: "Central range.",
        },
        {
          kind: "bull",
          probability: 0.4,
          priceLow: 122.0,
          priceHigh: 128.0,
          explanation: "Favorable range.",
        },
      ],
    } as Record<string, unknown> | null,
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
      ],
      blockedBy: [] as string[],
      methodVersion: "analysis-only-risk-plan-v1",
    } as Record<string, unknown> | null,
    sentiment: {
      conclusion: "偏多",
      actionScore: 0.6,
      decisionSignal: "long_bias",
      uncertainty: ["独立来源不足"],
    },
    citations: [
      {
        id: "c1",
        headline: "NVIDIA raises full-year revenue guidance",
        publisher: "Reuters",
        url: "https://reuters.example/a",
        availableAt: "2026-07-25T15:41:00.000Z",
      },
    ],
    // The adviser layer costs money, so the deployed default is a request that
    // never called it. The block still states which of the three states it is
    // in, because a bare null cannot tell "nobody asked" from "the model was
    // unreachable".
    newsInterpretation: {
      status: "not-requested",
      reason:
        "This request did not ask for the adviser layer; add adviser=1 to call the model.",
      value: null,
    } as Record<string, unknown> | null,
    adviserCouncil: {
      status: "not-requested",
      reason:
        "This request did not ask for the adviser layer; add adviser=1 to call the model.",
      value: null,
    } as Record<string, unknown> | null,
    adviserUsage: null as Record<string, unknown> | null,
    notes: ["Scored on 70% of the factor weight; the rest has no source yet."],
  };
}

/** One conclusion, sourced, exactly as the traceability layer emits it. */
export function adviserConclusionFixture() {
  return {
    statement: "指引上调支持偏多的解读。",
    confidence: "medium",
    citations: [
      {
        evidenceId: "a",
        quote: "raises full-year revenue guidance",
        url: "https://reuters.example/a",
        publisher: "reuters",
        availableAt: "2026-07-25T15:41:00Z",
        isCounterEvidence: false,
      },
    ],
    counterEvidence: [],
  };
}

export function newsInterpretationFixture() {
  return {
    status: "available",
    reason: null,
    value: {
      headlineSummary: "两家通讯社都报道了指引上调。",
      crossSourceReading: "两条报道指向同一件事，来源相互独立。",
      investmentImpact: [adviserConclusionFixture()],
      unknowns: ["证据没有说明毛利率如何变化。"],
    },
  };
}

export function adviserCouncilFixture() {
  return {
    status: "available",
    reason: null,
    value: {
      summary: "各框架都读到同一条指引上调。",
      opinions: [
        {
          frameworkId: "technical",
          displayName: "技术结构框架",
          stance: "bullish",
          blindSpot: "对基本面突变无感。",
          conclusions: [adviserConclusionFixture()],
        },
      ],
      baselineScore: 72.5,
      adjustedScore: 75.5,
      scoreAdjustment: 3,
      objectiveDirection: "bullish",
      actionable: true,
      blockedBy: [] as string[],
      disclaimer:
        "顾问观点是分析建议，不是操作指令；其影响有上限，且任一硬门未通过时一律作废。",
    },
  };
}

export function adviserUsageFixture() {
  return {
    model: "claude-opus-4-8",
    inputTokens: 13000,
    outputTokens: 3900,
    cacheCreationInputTokens: 0,
    cacheReadInputTokens: 2000,
    costUsd: 0.163,
  };
}
