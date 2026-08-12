const cutoff = "2026-07-25T16:00:00.000Z";

export function decisionFixture() {
  return {
    schemaVersion: "1",
    status: "live" as "live" | "unavailable",
    symbol: "NVDA",
    horizon: "short",
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
    baselineScore: null,
    adviserAdjustment: 0,
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
    notes: ["Scored on 70% of the factor weight; the rest has no source yet."],
  };
}
