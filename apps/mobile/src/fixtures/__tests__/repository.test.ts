import { describe, expect, it } from "@jest/globals";
import { fixtureRepository } from "@/fixtures/repository";

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
      expect(dashboard.marketDrivers.every((driver) => driver.freshness.length > 0)).toBe(true);
      expect(dashboard.watchlist.length).toBeGreaterThanOrEqual(3);
      expect(dashboard.candidates.some((candidate) => candidate.side === "long" && candidate.designation === "asymmetric-upside")).toBe(true);
      expect(dashboard.candidates.some((candidate) => candidate.side === "short" && candidate.designation === "standard")).toBe(true);
      expect(dashboard.candidates.every((candidate) => candidate.counterCase.length > 0 && candidate.invalidation.length > 0 && candidate.citationIds.length > 0)).toBe(true);
    },
  );

  it("keeps RSI, MACD, reported ownership, and participation proxy", () => {
    const stock = fixtureRepository.getStock("NVDA", "short");

    expect(stock.indicators.rsi.value).toBeGreaterThan(0);
    expect(stock.indicators.macd.histogram.length).toBeGreaterThan(0);
    expect(stock.candles).toHaveLength(28);
    expect(stock.forecast.points).toHaveLength(8);
    expect(stock.dragonTrend.methodVersion).toBe("original-demo-v1");
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

  it("keeps alert invalidation and objective conversation order", () => {
    expect(fixtureRepository.getAlerts()[0]).toMatchObject({
      currentState: "等待量价确认",
      invalidation: "收盘跌破 136.40",
    });
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
});
