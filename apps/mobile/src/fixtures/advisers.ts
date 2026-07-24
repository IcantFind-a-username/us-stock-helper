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
const horizons = ["short", "swing", "long"] as const;

type PlanProfile = {
  symbol: string;
  objectiveScore: number;
  confidence: number;
  longEntry: [number, number];
  shortEntry: [number, number];
  longInvalidation: number;
  shortInvalidation: number;
  longTarget: [number, number];
  shortTarget: [number, number];
  quantityScale: number;
  borrowFee: number;
  shortInterest: number;
  crowding: NonNullable<TradePlan["shortRisk"]>["crowding"];
};

const planProfiles: PlanProfile[] = [
  {
    symbol: "NVDA",
    objectiveScore: 72,
    confidence: 0.68,
    longEntry: [139.8, 141.2],
    shortEntry: [143.4, 144.6],
    longInvalidation: 136.4,
    shortInvalidation: 148.2,
    longTarget: [148, 153],
    shortTarget: [134, 137],
    quantityScale: 1,
    borrowFee: 0.35,
    shortInterest: 1.2,
    crowding: "low",
  },
  {
    symbol: "TSLA",
    objectiveScore: 53,
    confidence: 0.56,
    longEntry: [309.5, 314],
    shortEntry: [320, 324],
    longInvalidation: 299.8,
    shortInvalidation: 334,
    longTarget: [331, 342],
    shortTarget: [290, 302],
    quantityScale: 0.45,
    borrowFee: 0.48,
    shortInterest: 2.7,
    crowding: "medium",
  },
  {
    symbol: "PLTR",
    objectiveScore: 46,
    confidence: 0.51,
    longEntry: [82.2, 84.1],
    shortEntry: [86.8, 88.2],
    longInvalidation: 78.6,
    shortInvalidation: 92.4,
    longTarget: [90, 94],
    shortTarget: [76, 80],
    quantityScale: 1.4,
    borrowFee: 0.62,
    shortInterest: 3.1,
    crowding: "medium",
  },
];

export const tradePlanFixtures: TradePlan[] = planProfiles.flatMap((profile) =>
  horizons.flatMap((horizon) =>
    sides.flatMap((side) =>
      preferences.map((preference, index): TradePlan => ({
      id:
        horizon === "short"
          ? `${profile.symbol}-${side}-${preference}`
          : `${profile.symbol}-${horizon}-${side}-${preference}`,
      symbol: profile.symbol,
      horizon,
      side,
      preference,
      objectiveScore:
        profile.objectiveScore + (horizon === "swing" ? -3 : horizon === "long" ? 4 : 0),
      confidence:
        profile.confidence + (horizon === "swing" ? -0.04 : horizon === "long" ? 0.04 : 0),
      entryMethod: preference === "aggressive" ? "突破限价" : "回踩分批限价",
      entryRange: side === "long" ? profile.longEntry : profile.shortEntry,
      quantity: Math.max(1, Math.round(([20, 35, 50][index] ?? 20) * profile.quantityScale)),
      riskBudgetPercent: [0.5, 0.8, 1.0][index] ?? 0.5,
      leverage: [1, 1.25, 1.5][index] ?? 1,
      maximumLeverage: 1.5,
      invalidationPrice:
        side === "long" ? profile.longInvalidation : profile.shortInvalidation,
      stopLogic: "触及失效价后取消原假设；跳空时按首个可执行价格重新评估。",
      targetRange: side === "long" ? profile.longTarget : profile.shortTarget,
      estimatedRewardRisk: [1.6, 2.1, 2.6][index] ?? 1.6,
      holdingWindow:
        horizon === "short"
          ? "盘中至 5 个交易日"
          : horizon === "swing"
            ? "1–8 周"
            : "2–24 个月",
      cancelConditions: ["证据包过期", "大盘环境转为空头", "关键消息被证伪"],
      riskWarning:
        side === "short"
          ? "演示方案；需确认借券可用性，做空存在理论上的无限损失风险。"
          : "演示方案；跳空可能使实际亏损超过计划止损。",
      evidenceSnapshotId: `${profile.symbol}-${horizon}-2026-07-24`,
      generatedAt: "2026-07-24T15:50:02Z",
      methodVersion: `demo-risk-${horizon}-v1`,
      citationIds: [
        `${profile.symbol.toLowerCase()}-source-1`,
        `${profile.symbol.toLowerCase()}-source-2`,
      ],
      shortRisk:
        side === "short"
          ? {
              borrowAvailable: true,
              checkedAt: "2026-07-24T11:49:00-04:00",
              estimatedBorrowFeePercent: profile.borrowFee,
              shortInterestPercent: profile.shortInterest,
              crowding: profile.crowding,
              warnings: ["逼空与跳空风险", "停牌与召回风险", "理论上的无限损失风险"],
            }
          : null,
      })),
    ),
  ),
);
