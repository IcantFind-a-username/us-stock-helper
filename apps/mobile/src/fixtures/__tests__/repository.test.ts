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
      expect(dashboard.marketDrivers.length).toBeGreaterThanOrEqual(4);
      expect(dashboard.watchlist.length).toBeGreaterThanOrEqual(3);
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
