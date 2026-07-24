import type { DashboardSnapshot, Horizon, MarketDriver, MarketDriverCategory } from "@/domain/models";

import { alertThreads } from "./alerts";

const horizonData: Record<
  Horizon,
  Pick<
    DashboardSnapshot,
    | "marketScore"
    | "marketConfidence"
    | "marketScoreChange"
    | "marketConclusion"
    | "marketAdvice"
    | "marketInvalidation"
    | "contradictions"
  >
> = {
  short: {
    marketScore: 61,
    marketConfidence: 0.67,
    marketScoreChange: 4,
    marketConclusion: "谨慎偏多",
    marketAdvice: "优先等回踩确认；单一方案风险预算不超过演示账户的 1%。",
    marketInvalidation: "广度继续走弱且波动率期限结构转为明显倒挂。",
    contradictions: ["指数上涨但市场广度扩散有限", "板块强势但利率端仍有压制"],
  },
  swing: {
    marketScore: 56,
    marketConfidence: 0.62,
    marketScoreChange: -2,
    marketConclusion: "波段环境",
    marketAdvice: "以相对强势板块为主，等待回撤后再验证趋势延续。",
    marketInvalidation: "趋势跌破中期均线且信用利差同步扩大。",
    contradictions: ["趋势仍在但高估值板块轮动加快", "信用与流动性信号尚未完全一致"],
  },
  long: {
    marketScore: 68,
    marketConfidence: 0.73,
    marketScoreChange: 3,
    marketConclusion: "中长期质量优先",
    marketAdvice: "优先关注现金流质量与估值缓冲，接受短期价格波动。",
    marketInvalidation: "收益预期下修与美元走强同时持续，削弱长期盈利假设。",
    contradictions: ["增长预期改善但估值分化扩大", "地缘政治成本仍可能扰动供应链"],
  },
};

const driverDefinitions: [MarketDriverCategory, string, number, string][] = [
  ["news-sentiment", "新闻与整体情绪", 22, "情绪偏多但拥挤"],
  ["breadth", "市场广度", 6, "上涨扩散有限"],
  ["volatility-options", "波动率与期权", -8, "尾部保护需求上升"],
  ["sector", "板块强弱", 31, "半导体相对强势"],
  ["rates-dollar", "利率与美元", -18, "估值端仍受压制"],
  ["macro-credit-energy", "宏观、信用与能源", -4, "信用平稳，能源波动待观察"],
  ["liquidity-correlation", "流动性与相关性压力", -11, "相关性抬升，分散效果下降"],
  ["broad-market-trend", "大盘趋势", 18, "趋势向上但回踩仍需确认"],
  ["geopolitics", "地缘政治", -12, "出口限制风险待确认"],
];

const horizonDriverAdjustment: Record<Horizon, number> = { short: 0, swing: -3, long: 4 };

function marketDrivers(horizon: Horizon) {
  return driverDefinitions.map(([category, label, score, conclusion], index) => {
    const freshness: MarketDriver["freshness"] = index === 8 ? "conflict" : index === 6 ? "stale" : "fresh";

    return {
      id: `driver-${category}`,
      category,
      label,
      score: score + horizonDriverAdjustment[horizon],
      conclusion,
      freshness,
      citationIds: ["nvda-source-2"],
    };
  });
}

function candidates(horizon: Horizon): DashboardSnapshot["candidates"] {
  return [
    {
      symbol: "NVDA",
      company: "NVIDIA",
      horizon,
      side: "long",
      designation: "asymmetric-upside",
      score: 72,
      state: "action-eligible",
      catalyst: "板块动量与事件窗口",
      evidenceFreshness: "fresh",
      institutionalProxy: "估算机构参与 58% · 中置信",
      technicalState: "九转 7；MACD 多头扩张",
      fundamentalState: "增长强，估值偏高",
      volatilityState: "中等偏高",
      liquidityRisk: "low",
      reason: "催化、量价和市场环境同向，但尚未排除事件风险。",
      counterCase: "估值拥挤，若成交量未确认则动量可能快速反转。",
      invalidation: "收盘跌破 136.40 且大盘趋势同步转弱。",
      evidenceCount: 5,
      counterEvidenceCount: 2,
      citationIds: ["nvda-source-2"],
    },
    {
      symbol: "TSLA",
      company: "Tesla",
      horizon,
      side: "short",
      designation: "standard",
      score: 58,
      state: "observation",
      catalyst: "交付预期变化",
      evidenceFreshness: "conflict",
      institutionalProxy: "覆盖不足",
      technicalState: "反弹遇阻，等待确认",
      fundamentalState: "利润率与现金流待验证",
      volatilityState: "高",
      liquidityRisk: "medium",
      reason: "仅进入观察池，证据尚不足以触发行动研究。",
      counterCase: "若交付或利润率超预期，空头假设会迅速失效。",
      invalidation: "放量突破近期反弹高点并维持两日。",
      evidenceCount: 3,
      counterEvidenceCount: 3,
      citationIds: ["nvda-source-2"],
    },
    {
      symbol: "PLTR",
      company: "Palantir",
      horizon,
      side: "long",
      designation: "standard",
      score: 49,
      state: "risk",
      catalyst: "订单消息",
      evidenceFreshness: "stale",
      institutionalProxy: "估算机构参与 46% · 低置信",
      technicalState: "RSI 接近超买",
      fundamentalState: "增长较快，估值拥挤",
      volatilityState: "高",
      liquidityRisk: "high",
      reason: "估值、拥挤度和消息确认度带来较高回撤风险。",
      counterCase: "若订单持续超预期，估值压力可能被盈利上修抵消。",
      invalidation: "连续两次订单确认且估值溢价收敛。",
      evidenceCount: 2,
      counterEvidenceCount: 5,
      citationIds: ["nvda-source-2"],
    },
  ];
}

const buildDashboard = (horizon: Horizon): DashboardSnapshot => ({
  demoData: true,
  horizon,
  updatedAt: "2026-07-24T10:30:00-04:00",
  marketSession: "美股盘中 · 演示状态",
  dataHealth: "fresh",
  ...horizonData[horizon],
  marketDrivers: marketDrivers(horizon),
  priorityAlert: { ...alertThreads[0]!, horizon },
  watchlist: [
    { symbol: "NVDA", price: 143.8, changePercent: 2.46, direction: "bullish", summary: "量价待确认" },
    { symbol: "TSLA", price: 318.2, changePercent: -1.2, direction: "bearish", summary: "事件波动高" },
    { symbol: "PLTR", price: 86.4, changePercent: 0.8, direction: "neutral", summary: "高估值观察" },
  ],
  candidates: candidates(horizon),
});

export const dashboardFixtures: Record<Horizon, DashboardSnapshot> = {
  short: buildDashboard("short"),
  swing: buildDashboard("swing"),
  long: buildDashboard("long"),
};
