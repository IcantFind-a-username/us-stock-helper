import type { AlertThread, Candidate, Citation, DashboardSnapshot, Horizon, MarketDriver, MarketDriverCategory, MarketDriverCoverage } from "@/domain/models";

const horizons: Horizon[] = ["short", "swing", "long"];
const horizonNames: Record<Horizon, string> = { short: "短线", swing: "波段", long: "长期" };

type HorizonMarket = Pick<DashboardSnapshot, "marketScore" | "marketConfidence" | "marketScoreChange" | "marketConclusion" | "marketRationale" | "marketAdvice" | "marketRiskPosture" | "marketInvalidation" | "contradictions">;

const horizonData: Record<Horizon, HorizonMarket> = {
  short: {
    marketScore: 61,
    marketConfidence: 0.67,
    marketScoreChange: 4,
    marketConclusion: "谨慎偏多",
    marketRationale: "新闻与社交情绪改善，但市场广度和期限结构仍要求确认。",
    marketAdvice: "优先等回踩确认；单一方案风险预算不超过演示账户的 1%。",
    marketRiskPosture: "轻仓，等待量价与广度确认",
    marketInvalidation: "广度继续走弱且波动率期限结构转为明显倒挂。",
    contradictions: ["指数上涨但市场广度扩散有限", "板块强势但利率端仍有压制"],
  },
  swing: {
    marketScore: 56,
    marketConfidence: 0.62,
    marketScoreChange: -2,
    marketConclusion: "波段环境",
    marketRationale: "板块相对强势仍在，但信用与趋势确认尚未同步。",
    marketAdvice: "以相对强势板块为主，等待回撤后再验证趋势延续。",
    marketRiskPosture: "分批，优先顺势回撤",
    marketInvalidation: "趋势跌破中期均线且信用利差同步扩大。",
    contradictions: ["趋势仍在但高估值板块轮动加快", "信用与流动性信号尚未完全一致"],
  },
  long: {
    marketScore: 68,
    marketConfidence: 0.73,
    marketScoreChange: 3,
    marketConclusion: "中长期质量优先",
    marketRationale: "盈利质量与资本开支持续改善，但估值与地缘成本仍需折价。",
    marketAdvice: "优先关注现金流质量与估值缓冲，接受短期价格波动。",
    marketRiskPosture: "耐心，质量优先并容忍波动",
    marketInvalidation: "收益预期下修与美元走强同时持续，削弱长期盈利假设。",
    contradictions: ["增长预期改善但估值分化扩大", "地缘政治成本仍可能扰动供应链"],
  },
};

type DriverDefinition = {
  category: MarketDriverCategory;
  coverage: MarketDriverCoverage[];
  label: string;
  score: number;
  conclusion: Record<Horizon, string>;
};

const driverDefinitions: DriverDefinition[] = [
  { category: "news-sentiment", coverage: ["news", "social-sentiment"], label: "新闻与社交情绪", score: 22, conclusion: { short: "新闻改善，社交讨论升温但拥挤", swing: "新闻催化有限，社交热度回落", long: "盈利叙事改善，社交噪音权重较低" } },
  { category: "breadth", coverage: ["breadth"], label: "市场广度", score: 6, conclusion: { short: "上涨扩散有限", swing: "广度尚未确认轮动", long: "长期参与度温和修复" } },
  { category: "volatility-options", coverage: ["volatility", "options", "term-structure"], label: "波动率、期权与期限结构", score: -8, conclusion: { short: "近端保护需求上升，期限结构偏脆弱", swing: "期权保护缓和但期限结构仍平坦", long: "长期波动定价可控，短端保护仍需关注" } },
  { category: "sector", coverage: ["sector-strength"], label: "板块强弱", score: 31, conclusion: { short: "半导体相对强势", swing: "科技相对强势但轮动加快", long: "高质量资本开支链条占优" } },
  { category: "rates-dollar", coverage: ["rates", "yield-curve", "dollar"], label: "利率、收益率曲线与美元", score: -18, conclusion: { short: "收益率与美元压制估值", swing: "曲线趋稳但美元尚未转弱", long: "长期利率压力缓解，美元仍是反证" } },
  { category: "macro-credit-energy", coverage: ["macro", "credit", "energy", "commodities"], label: "宏观、信用、能源与商品", score: -4, conclusion: { short: "信用平稳，能源与商品波动待观察", swing: "宏观放缓但信用未恶化", long: "资本开支与商品成本的长期平衡改善" } },
  { category: "liquidity-correlation", coverage: ["liquidity", "correlation-stress"], label: "流动性与相关性压力", score: -11, conclusion: { short: "相关性抬升，分散效果下降", swing: "流动性正常但相关性压力未消", long: "长期流动性充足，短期相关性仍偏高" } },
  { category: "broad-market-trend", coverage: ["broad-trend"], label: "大盘趋势", score: 18, conclusion: { short: "趋势向上但回踩仍需确认", swing: "中期趋势横向整理", long: "长期上升趋势保持" } },
  { category: "geopolitics", coverage: ["geopolitics"], label: "地缘政治", score: -12, conclusion: { short: "出口限制风险待确认", swing: "政策风险影响轮动", long: "供应链重构成本仍在" } },
];

const driverAdjustment: Record<Horizon, number> = { short: 0, swing: -3, long: 4 };

const candidateSpecs: Record<Horizon, (Omit<Candidate, "horizon" | "citationIds"> & { citationId: string })[]> = {
  short: [
    { symbol: "NVDA", company: "NVIDIA", side: "long", designation: "asymmetric-upside", score: 72, state: "action-eligible", catalyst: "盘中量价确认", evidenceFreshness: "fresh", institutionalProxy: "估算机构参与 58% · 中置信", technicalState: "九转 7；MACD 多头扩张", fundamentalState: "增长强，估值偏高", volatilityState: "中等偏高", liquidityRisk: "low", reason: "催化、量价和短线市场环境同向。", counterCase: "估值拥挤，若成交量未确认则动量可能快速反转。", invalidation: "收盘跌破 136.40 且大盘趋势同步转弱。", evidenceCount: 5, counterEvidenceCount: 2, citationId: "short-nvda" },
    { symbol: "TSLA", company: "Tesla", side: "short", designation: "standard", score: 58, state: "observation", catalyst: "交付预期变化", evidenceFreshness: "conflict", institutionalProxy: "覆盖不足", technicalState: "反弹遇阻，等待确认", fundamentalState: "利润率与现金流待验证", volatilityState: "高", liquidityRisk: "medium", reason: "短线交付预期分歧大，仅进入观察池。", counterCase: "若交付或利润率超预期，空头假设会迅速失效。", invalidation: "放量突破近期反弹高点并维持两日。", evidenceCount: 3, counterEvidenceCount: 3, citationId: "short-tsla" },
    { symbol: "PLTR", company: "Palantir", side: "long", designation: "standard", score: 49, state: "risk", catalyst: "订单消息", evidenceFreshness: "stale", institutionalProxy: "估算机构参与 46% · 低置信", technicalState: "RSI 接近超买", fundamentalState: "增长较快，估值拥挤", volatilityState: "高", liquidityRisk: "high", reason: "短线估值与拥挤度风险高。", counterCase: "若订单持续超预期，估值压力可能被盈利上修抵消。", invalidation: "连续两次订单确认且估值溢价收敛。", evidenceCount: 2, counterEvidenceCount: 5, citationId: "short-pltr" },
  ],
  swing: [
    { symbol: "NVDA", company: "NVIDIA", side: "long", designation: "standard", score: 64, state: "observation", catalyst: "趋势与广度验证", evidenceFreshness: "fresh", institutionalProxy: "估算机构参与 57% · 中置信", technicalState: "周线动量放缓，等待回撤", fundamentalState: "盈利上修与估值扩张分化", volatilityState: "中等", liquidityRisk: "low", reason: "波段趋势仍需广度与回撤承接确认。", counterCase: "若板块轮动扩大，单一龙头相对强势会减弱。", invalidation: "周线跌破中期趋势位且广度未修复。", evidenceCount: 4, counterEvidenceCount: 3, citationId: "swing-nvda" },
    { symbol: "TSLA", company: "Tesla", side: "short", designation: "standard", score: 62, state: "action-eligible", catalyst: "利润率修复验证", evidenceFreshness: "fresh", institutionalProxy: "覆盖不足", technicalState: "周线反弹量能不足", fundamentalState: "利润率修复低于预期", volatilityState: "中等偏高", liquidityRisk: "medium", reason: "波段反弹缺乏基本面与量能共同确认。", counterCase: "若利润率持续修复，估值重估会压缩空头空间。", invalidation: "周线放量站稳前高并出现利润率上修。", evidenceCount: 4, counterEvidenceCount: 2, citationId: "swing-tsla" },
    { symbol: "PLTR", company: "Palantir", side: "long", designation: "asymmetric-upside", score: 67, state: "observation", catalyst: "企业订单兑现", evidenceFreshness: "conflict", institutionalProxy: "估算机构参与 47% · 中置信", technicalState: "周线高位整理", fundamentalState: "订单增速改善但估值仍高", volatilityState: "中等偏高", liquidityRisk: "medium", reason: "波段订单催化存在，但需要确认增长兑现。", counterCase: "若订单节奏放缓，高估值会放大回撤。", invalidation: "订单增速下修且周线跌破整理区。", evidenceCount: 4, counterEvidenceCount: 3, citationId: "swing-pltr" },
  ],
  long: [
    { symbol: "NVDA", company: "NVIDIA", side: "long", designation: "asymmetric-upside", score: 81, state: "action-eligible", catalyst: "盈利质量与资本开支", evidenceFreshness: "fresh", institutionalProxy: "估算机构参与 61% · 高置信", technicalState: "长期趋势完整", fundamentalState: "现金流与盈利质量强，估值需折价", volatilityState: "中等", liquidityRisk: "low", reason: "长期盈利质量、现金流与资本开支趋势形成更优赔率。", counterCase: "若客户资本开支下修，长期盈利预期可能回撤。", invalidation: "连续两季盈利质量下修且资本开支预期转弱。", evidenceCount: 7, counterEvidenceCount: 2, citationId: "long-nvda" },
    { symbol: "TSLA", company: "Tesla", side: "short", designation: "standard", score: 54, state: "risk", catalyst: "竞争与资本开支", evidenceFreshness: "stale", institutionalProxy: "覆盖不足", technicalState: "长期均线仍有支撑", fundamentalState: "竞争加剧，现金流转折待验证", volatilityState: "高", liquidityRisk: "medium", reason: "长期竞争与资本开支假设尚缺少新证据支持。", counterCase: "若新业务兑现现金流，长期估值框架会改变。", invalidation: "自由现金流连续改善并超过长期预期。", evidenceCount: 3, counterEvidenceCount: 4, citationId: "long-tsla" },
    { symbol: "PLTR", company: "Palantir", side: "long", designation: "standard", score: 60, state: "observation", catalyst: "长期客户留存", evidenceFreshness: "fresh", institutionalProxy: "估算机构参与 49% · 中置信", technicalState: "长期趋势未破", fundamentalState: "留存改善，估值缓冲有限", volatilityState: "中等", liquidityRisk: "medium", reason: "长期客户留存改善提供观察价值，仍需估值缓冲。", counterCase: "若客户集中度升高，增长质量会受损。", invalidation: "客户留存下滑且估值溢价继续扩大。", evidenceCount: 5, counterEvidenceCount: 3, citationId: "long-pltr" },
  ],
};

const citationTitles: Record<string, string> = {
  "short-nvda": "演示：短线 NVDA 量价确认快照",
  "short-tsla": "演示：TSLA 短线交付预期快照",
  "short-pltr": "演示：PLTR 短线订单风险快照",
  "swing-nvda": "演示：波段 NVDA 趋势与广度快照",
  "swing-tsla": "演示：TSLA 波段利润率快照",
  "swing-pltr": "演示：PLTR 波段订单兑现快照",
  "long-nvda": "演示：长期 NVDA 盈利质量快照",
  "long-tsla": "演示：TSLA 长期竞争与现金流快照",
  "long-pltr": "演示：PLTR 长期客户留存快照",
};

function citation(id: string, title: string): Citation {
  return { id, title, publisher: "Demo Evidence Desk", url: `https://example.com/${id}`, publishedAt: "2026-07-24T14:30:00Z", firstSeenAt: "2026-07-24T14:30:01Z", kind: "inference" };
}

export const dashboardCitations: Citation[] = [
  ...horizons.flatMap((horizon) => driverDefinitions.map((driver) => citation(`${horizon}-${driver.category}`, `演示：${horizonNames[horizon]}${driver.label}快照`))),
  ...Object.entries(citationTitles).map(([id, title]) => citation(id, title)),
];

function citationById(id: string) {
  const match = dashboardCitations.find((item) => item.id === id);
  if (!match) throw new Error(`Missing dashboard citation: ${id}`);
  return match;
}

function marketDrivers(horizon: Horizon): MarketDriver[] {
  return driverDefinitions.map((driver, index) => ({
    id: `driver-${driver.category}`,
    category: driver.category,
    coverage: driver.coverage,
    label: driver.label,
    score: driver.score + driverAdjustment[horizon],
    conclusion: driver.conclusion[horizon],
    freshness: index === 8 ? "conflict" : (horizon === "short" && index === 6) || (horizon === "long" && index === 4) ? "stale" : "fresh",
    citationIds: [`${horizon}-${driver.category}`],
  }));
}

function candidates(horizon: Horizon): Candidate[] {
  return candidateSpecs[horizon].map(({ citationId, ...candidate }) => ({ ...candidate, horizon, citationIds: [citationId] }));
}

function priorityAlert(horizon: Horizon): AlertThread {
  const candidate = candidates(horizon)[0]!;
  const alertCopy: Record<Horizon, Pick<AlertThread, "title" | "summary" | "triggeredAt" | "sourceFreshness" | "currentState" | "invalidation" | "baseScoreContribution" | "adviserAdjustment" | "evidenceCount" | "counterEvidenceCount" | "updatedAt">> = {
    short: { title: "NVDA 接近量价确认区", summary: "价格走强，但仍需成交量与指数环境共同确认。", triggeredAt: "2026-07-24T10:26:00-04:00", sourceFreshness: "fresh", currentState: "等待量价确认", invalidation: "收盘跌破 136.40", baseScoreContribution: 7, adviserAdjustment: 2, evidenceCount: 5, counterEvidenceCount: 2, updatedAt: "2026-07-24T10:30:00-04:00" },
    swing: { title: "NVDA 进入波段趋势验证区", summary: "相对强势尚在，需由广度与回撤承接共同确认。", triggeredAt: "2026-07-24T10:12:00-04:00", sourceFreshness: "fresh", currentState: "等待周线趋势确认", invalidation: "周线跌破中期趋势位", baseScoreContribution: 4, adviserAdjustment: -1, evidenceCount: 4, counterEvidenceCount: 3, updatedAt: "2026-07-24T10:28:00-04:00" },
    long: { title: "NVDA 长期盈利质量待估值确认", summary: "盈利质量强，但估值与资本开支假设需要持续验证。", triggeredAt: "2026-07-24T09:45:00-04:00", sourceFreshness: "stale", currentState: "等待盈利质量复核", invalidation: "连续两季盈利质量下修", baseScoreContribution: 9, adviserAdjustment: 3, evidenceCount: 7, counterEvidenceCount: 2, updatedAt: "2026-07-24T10:20:00-04:00" },
  };
  const copy = alertCopy[horizon];

  return { id: `${horizon}-nvda-priority`, symbol: candidate.symbol, horizon, severity: horizon === "long" ? "observation" : "action", ...copy, citations: [citationById(candidate.citationIds[0]!)] };
}

const buildDashboard = (horizon: Horizon): DashboardSnapshot => ({
  demoData: true,
  horizon,
  updatedAt: "2026-07-24T10:30:00-04:00",
  marketSession: "美股盘中 · 演示状态",
  dataHealth: "fresh",
  ...horizonData[horizon],
  marketDrivers: marketDrivers(horizon),
  priorityAlert: priorityAlert(horizon),
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
