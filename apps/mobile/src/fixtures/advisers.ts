import type {
  AdviserOpinion,
  PlanSide,
  RiskPreference,
  TradePlan,
} from "@/domain/models";

const adviserProfiles = [
  ["damodaran", "Damodaran 风格", "估值叙事"],
  ["graham", "Graham 风格", "安全边际"],
  ["ackman", "Ackman 风格", "集中与催化"],
  ["wood", "Cathie Wood 风格", "创新成长"],
  ["munger", "Munger 风格", "企业质量"],
  ["burry", "Burry 风格", "逆向与泡沫"],
  ["pabrai", "Pabrai 风格", "低风险高不对称"],
  ["taleb", "Taleb 风格", "尾部风险"],
  ["lynch", "Peter Lynch 风格", "成长与可理解性"],
  ["fisher", "Phil Fisher 风格", "深度成长研究"],
  ["jhunjhunwala", "Jhunjhunwala 风格", "长期成长"],
  ["druckenmiller", "Druckenmiller 风格", "宏观动量"],
  ["buffett", "Buffett 风格", "质量与合理价格"],
] as const;

export const adviserOpinions: AdviserOpinion[] = adviserProfiles.map(([id, displayName, focus], index): AdviserOpinion => ({
  id,
  displayName,
  focus,
  direction: index === 5 || index === 7 ? "bearish" : "bullish",
  confidence: index < 4 ? 0.72 : 0.58,
  active: index < 4,
  abstained: index === 12,
  thesis: "基于演示证据包的风格化观点。",
  counterargument: "估值拥挤与事件不确定性可能削弱结论。",
  evidenceIds: ["nvda-source-1"],
}));

const preferences: RiskPreference[] = ["conservative", "balanced", "aggressive"];
const sides: PlanSide[] = ["long", "short"];

export const tradePlanFixtures: TradePlan[] = sides.flatMap((side) =>
  preferences.map((preference, index): TradePlan => ({
    id: `NVDA-${side}-${preference}`,
    symbol: "NVDA",
    side,
    preference,
    objectiveScore: 72,
    confidence: 0.68,
    entryMethod: preference === "aggressive" ? "突破限价" : "回踩分批限价",
    entryRange: side === "long" ? [139.8, 141.2] : [143.4, 144.6],
    quantity: [20, 35, 50][index] ?? 20,
    riskBudgetPercent: [0.5, 0.8, 1.0][index] ?? 0.5,
    leverage: [1, 1.25, 1.5][index] ?? 1,
    maximumLeverage: 1.5,
    invalidationPrice: side === "long" ? 136.4 : 148.2,
    stopLogic: "触及失效价后取消原假设；跳空时按首个可执行价格重新评估。",
    targetRange: side === "long" ? [148, 153] : [134, 137],
    estimatedRewardRisk: [1.6, 2.1, 2.6][index] ?? 1.6,
    holdingWindow: "盘中至 5 个交易日",
    cancelConditions: ["证据包过期", "大盘环境转为空头", "关键消息被证伪"],
    riskWarning:
      side === "short"
        ? "演示方案；需确认借券可用性，做空存在理论上的无限损失风险。"
        : "演示方案；跳空可能使实际亏损超过计划止损。",
    evidenceSnapshotId: "NVDA-short-2026-07-24T10:30:00Z",
    shortRisk: side === "short" ? {
      borrowAvailable: true,
      checkedAt: "2026-07-24T10:29:00-04:00",
      estimatedBorrowFeePercent: 0.35,
      shortInterestPercent: 1.2,
      crowding: "low",
      warnings: ["逼空与跳空风险", "停牌与召回风险", "理论上的无限损失风险"],
    } : null,
  })),
);
