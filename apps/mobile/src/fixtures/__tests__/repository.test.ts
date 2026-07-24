import { describe, expect, it } from "@jest/globals";
import type { Horizon } from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";

type HorizonExpectation = {
  horizon: Horizon;
  score: number;
  confidence: number;
  scoreChange: number;
  rationale: string;
  advice: string;
  posture: string;
  alertTitle: string;
  citationTitle: string;
  candidateScore: number;
  candidateReason: string;
  driverConclusion: string;
};

const horizonExpectations: HorizonExpectation[] = [
  { horizon: "short", score: 61, confidence: 0.67, scoreChange: 4, rationale: "新闻与社交情绪改善", advice: "优先等回踩确认", posture: "轻仓，等待量价与广度确认", alertTitle: "NVDA 接近量价确认区", citationTitle: "演示：短线 NVDA 量价确认快照", candidateScore: 72, candidateReason: "催化、量价和短线", driverConclusion: "新闻改善，社交讨论升温但拥挤" },
  { horizon: "swing", score: 56, confidence: 0.62, scoreChange: -2, rationale: "板块相对强势", advice: "以相对强势板块为主", posture: "分批，优先顺势回撤", alertTitle: "NVDA 进入波段趋势验证区", citationTitle: "演示：波段 NVDA 趋势与广度快照", candidateScore: 64, candidateReason: "波段趋势仍需", driverConclusion: "新闻催化有限，社交热度回落" },
  { horizon: "long", score: 68, confidence: 0.73, scoreChange: 3, rationale: "盈利质量与资本开支", advice: "优先关注现金流质量", posture: "耐心，质量优先并容忍波动", alertTitle: "NVDA 长期盈利质量待估值确认", citationTitle: "演示：长期 NVDA 盈利质量快照", candidateScore: 81, candidateReason: "长期盈利质量", driverConclusion: "盈利叙事改善，社交噪音权重较低" },
];

describe("fixtureRepository", () => {
  it.each(["short", "swing", "long"] as const)(
    "returns a complete %s dashboard",
    (horizon) => {
      const dashboard = fixtureRepository.getDashboard(horizon);

      expect(dashboard.horizon).toBe(horizon);
      expect(dashboard.demoData).toBe(true);
      expect(dashboard.marketConclusion.length).toBeGreaterThan(0);
      expect(dashboard.marketDrivers.map((driver) => driver.category)).toEqual([
        "news-sentiment",
        "breadth",
        "volatility-options",
        "sector",
        "rates-dollar",
        "macro-credit-energy",
        "liquidity-correlation",
        "broad-market-trend",
        "geopolitics",
      ]);
      expect(dashboard.marketDrivers.map((driver) => driver.coverage)).toEqual([
        ["news", "social-sentiment"],
        ["breadth"],
        ["volatility", "options", "term-structure"],
        ["sector-strength"],
        ["rates", "yield-curve", "dollar"],
        ["macro", "credit", "energy", "commodities"],
        ["liquidity", "correlation-stress"],
        ["broad-trend"],
        ["geopolitics"],
      ]);
      expect(dashboard.marketDrivers.every((driver) => driver.freshness.length > 0)).toBe(true);
      expect(dashboard.marketDrivers.find((driver) => driver.category === "geopolitics")?.freshness).toBe("conflict");
      expect(dashboard.dataHealthCitationIds).toEqual([`${horizon}-data-health`]);
      expect(fixtureRepository.getCitations(dashboard.dataHealthCitationIds)[0]?.title).toBe(`演示：${horizon === "short" ? "短线" : horizon === "swing" ? "波段" : "长期"}数据健康与市场时段快照`);
      expect(dashboard.watchlist.length).toBeGreaterThanOrEqual(3);
      expect(dashboard.candidates.some((candidate) => candidate.side === "long" && candidate.designation === "asymmetric-upside")).toBe(true);
      expect(dashboard.candidates.some((candidate) => candidate.side === "short" && candidate.designation === "standard")).toBe(true);
      expect(dashboard.candidates.every((candidate) => candidate.counterCase.length > 0 && candidate.invalidation.length > 0 && candidate.citationIds.length > 0)).toBe(true);
    },
  );

  it.each(horizonExpectations)(
    "keeps $horizon objective fields, alert, candidates, drivers, and evidence independently fixture-backed",
    ({ horizon, score, confidence, scoreChange, rationale, advice, posture, alertTitle, citationTitle, candidateScore, candidateReason, driverConclusion }) => {
      const dashboard = fixtureRepository.getDashboard(horizon);
      const candidate = dashboard.candidates[0]!;

      expect(dashboard.marketScore).toBe(score);
      expect(dashboard.marketConfidence).toBe(confidence);
      expect(dashboard.marketScoreChange).toBe(scoreChange);
      expect(dashboard.marketRationale).toContain(rationale);
      expect(dashboard.marketAdvice).toContain(advice);
      expect(dashboard.marketRiskPosture).toBe(posture);
      expect(dashboard.priorityAlert.title).toBe(alertTitle);
      expect(dashboard.priorityAlert.sourceCoverage.length).toBeGreaterThan(0);
      expect(candidate.score).toBe(candidateScore);
      expect(candidate.reason).toContain(candidateReason);
      expect(fixtureRepository.getCitations(candidate.citationIds)[0]?.title).toBe(citationTitle);
      expect(fixtureRepository.getCitations(dashboard.marketDrivers[0]!.citationIds)[0]?.title).toContain(`${horizon === "short" ? "短线" : horizon === "swing" ? "波段" : "长期"}新闻与社交情绪`);
      expect(dashboard.marketDrivers[0]?.conclusion).toBe(driverConclusion);
    },
  );

  it.each(["short", "swing", "long"] as const)(
    "resolves every %s dashboard symbol into stock detail and six analysis plans",
    (horizon) => {
      const dashboard = fixtureRepository.getDashboard(horizon);
      const symbols = [
        ...new Set([
          ...dashboard.watchlist.map(({ symbol }) => symbol),
          ...dashboard.candidates.map(({ symbol }) => symbol),
          dashboard.priorityAlert.symbol,
        ]),
      ];

      expect(symbols).toEqual(["NVDA", "TSLA", "PLTR"]);

      for (const symbol of symbols) {
        const stock = fixtureRepository.getStock(symbol, horizon);
        const plans = fixtureRepository.getTradePlans(symbol);

        expect(stock).toMatchObject({ symbol, horizon, demoData: true });
        expect(plans).toHaveLength(6);
        expect(plans.every((plan) => plan.symbol === symbol)).toBe(true);
        expect(
          new Set(plans.map(({ side, preference }) => `${side}:${preference}`)),
        ).toEqual(
          new Set([
            "long:conservative",
            "long:balanced",
            "long:aggressive",
            "short:conservative",
            "short:balanced",
            "short:aggressive",
          ]),
        );
      }
    },
  );

  it("keeps RSI, MACD, reported ownership, and participation proxy", () => {
    const stock = fixtureRepository.getStock("NVDA", "short");

    expect(stock.indicators.rsi.value).toBeGreaterThan(0);
    expect(stock.indicators.macd.histogram.length).toBeGreaterThan(0);
    expect(stock.candles).toHaveLength(28);
    expect(stock.forecast.points).toHaveLength(8);
    expect(stock.dragonTrend.methodVersion).toBe("original-demo-short-v1");
    expect(stock.patterns[0]?.complete).toBe(false);
    expect(stock.fundamentals.materialRisks.length).toBeGreaterThan(0);
    expect(stock.reportedOwnership.reportedAt).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(stock.participationProxy.label).toBe("估算代理");
    expect(stock.participationProxy.sourceCoverage.length).toBeGreaterThan(0);
    expect(
      stock.participationProxy.institutionalPercent +
        stock.participationProxy.retailPercent,
    ).toBe(100);
  });

  it("keeps stock horizons genuinely independent and point-in-time safe", () => {
    const snapshots = (["short", "swing", "long"] as const).map((horizon) =>
      fixtureRepository.getStock("NVDA", horizon),
    );

    expect(new Set(snapshots.map(({ conclusion }) => conclusion)).size).toBe(3);
    expect(new Set(snapshots.map(({ adjustedScore }) => adjustedScore)).size).toBe(3);
    expect(new Set(snapshots.map(({ indicators }) => indicators.rsi.interval))).toEqual(
      new Set(["5分钟", "日线", "周线"]),
    );

    for (const stock of snapshots) {
      const predictedAt = Date.parse(stock.forecast.predictedAt);
      expect(Number.isFinite(predictedAt)).toBe(true);
      expect(
        stock.candles.every(
          (candle) =>
            candle.complete &&
            Number.isFinite(Date.parse(candle.availableAt)) &&
            Date.parse(candle.availableAt) <= predictedAt,
        ),
      ).toBe(true);
      expect(
        stock.forecast.points.every(
          (point) =>
            Number.isFinite(Date.parse(point.timestamp)) &&
            Date.parse(point.timestamp) > predictedAt,
        ),
      ).toBe(true);
      expect(Date.parse(stock.indicators.rsi.asOf)).toBeLessThanOrEqual(predictedAt);
      expect(Date.parse(stock.indicators.macd.asOf)).toBeLessThanOrEqual(predictedAt);
      expect(Date.parse(stock.marketContext.asOf)).toBeLessThanOrEqual(predictedAt);
      expect(Date.parse(stock.participationProxy.estimatedAt)).toBeLessThanOrEqual(
        predictedAt,
      );
      expect(Date.parse(stock.reportedOwnership.availableAt)).toBeLessThanOrEqual(
        predictedAt,
      );
      expect(
        stock.forecast.probability.up +
          stock.forecast.probability.flat +
          stock.forecast.probability.down,
      ).toBeCloseTo(1);
    }
  });

  it("keeps alert invalidation and objective conversation order", () => {
    const alerts = fixtureRepository.getAlerts();

    expect(alerts[0]).toMatchObject({
      currentState: "等待量价确认",
      invalidation: "收盘跌破 136.40",
      sourceCoverage: "盘中报价、期权与量价演示快照",
    });
    expect(alerts.map(({ severity }) => severity)).toEqual([
      "action",
      "risk",
      "observation",
      "info",
    ]);
    expect(alerts.every(({ citations }) => citations.length > 0)).toBe(true);
    expect(
      fixtureRepository
        .getConversation()[0]
        ?.sections?.map((section) => section.title),
    ).toEqual([
      "客观结论",
      "证据",
      "最强反证",
      "缺失信息与不确定性",
      "个性化风险场景",
      "引用",
    ]);
  });

  it.each(["NVDA", "TSLA", "PLTR"] as const)(
    "binds %s adviser opinions and plans only to resolvable same-symbol evidence",
    (symbol) => {
      const advisers = fixtureRepository.getAdvisers(symbol, "short");
      const plans = fixtureRepository.getTradePlans(symbol, "short");
      const expectedPrefix = `${symbol.toLowerCase()}-source-`;

      expect(advisers).toHaveLength(13);
      expect(
        advisers.every(
          (opinion) =>
            opinion.evidenceIds.every((id) => id.startsWith(expectedPrefix)) &&
            fixtureRepository.getCitations(opinion.evidenceIds).length ===
              opinion.evidenceIds.length,
        ),
      ).toBe(true);
      expect(plans).toHaveLength(6);
      expect(plans.every((plan) => plan.horizon === "short")).toBe(true);
      expect(
        plans.every(
          (plan) =>
            plan.citationIds.every((id) => id.startsWith(expectedPrefix)) &&
            fixtureRepository.getCitations(plan.citationIds).length ===
              plan.citationIds.length,
        ),
      ).toBe(true);
    },
  );

  it.each(["NVDA", "TSLA", "PLTR"] as const)(
    "freezes %s objective score and confidence across every risk preference",
    (symbol) => {
      for (const horizon of ["short", "swing", "long"] as const) {
        const stock = fixtureRepository.getStock(symbol, horizon);
        const plans = fixtureRepository.getTradePlans(symbol, horizon);
        expect(new Set(plans.map(({ objectiveScore }) => objectiveScore))).toEqual(
          new Set([stock.adjustedScore]),
        );
        expect(new Set(plans.map(({ confidence }) => confidence)).size).toBe(1);
      }
    },
  );
});
