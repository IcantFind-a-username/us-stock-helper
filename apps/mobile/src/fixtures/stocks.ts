import type { Candle, Horizon, StockSnapshot } from "@/domain/models";

const closes = [
  132.1, 132.8, 131.9, 133.2, 134.1, 133.6, 135.0, 136.2,
  135.7, 136.8, 137.6, 137.1, 138.4, 139.0, 138.5, 139.7,
  140.2, 139.8, 141.1, 141.8, 141.2, 142.0, 141.6, 142.4,
  142.9, 142.2, 143.1, 143.8,
];

const buildCandles = (price: number): Candle[] => {
  const scale = price / 143.8;
  return closes.map((rawClose, index) => {
    const close = rawClose * scale;
    const open = (index === 0 ? 131.6 : (closes[index - 1] ?? rawClose)) * scale;
    return {
      timestamp: `2026-07-24T${String(9 + Math.floor(index / 12)).padStart(2, "0")}:${String((index * 5) % 60).padStart(2, "0")}:00-04:00`,
      open,
      high: Math.max(open, close) + 0.7 * scale,
      low: Math.min(open, close) - 0.6 * scale,
      close,
      volume: 420_000 + index * 31_000,
    };
  });
};

type StockProfile = {
  symbol: string;
  company: string;
  price: number;
  changePercent: number;
  forecastSlope: number;
  baseScore: number;
  adjustedScore: number;
  conclusion: string;
  counterCase: string;
  rsi: StockSnapshot["indicators"]["rsi"];
  macd: StockSnapshot["indicators"]["macd"];
  reportedOwnership: Omit<StockSnapshot["reportedOwnership"], "reportedAt" | "citationIds">;
  participation: Pick<
    StockSnapshot["participationProxy"],
    "institutionalPercent" | "retailPercent" | "confidence" | "sourceCoverage"
  >;
  fundamentals: Omit<StockSnapshot["fundamentals"], "citationIds">;
  marketContext: Omit<StockSnapshot["marketContext"], "citationIds">;
};

const stockProfiles: StockProfile[] = [
  {
    symbol: "NVDA",
    company: "NVIDIA",
    price: 143.8,
    changePercent: 2.46,
    forecastSlope: 0.7,
    baseScore: 70,
    adjustedScore: 72,
    conclusion: "谨慎偏多；等待量价确认，不追高。",
    counterCase: "若指数转弱或出口限制升级，当前形态可能失效。",
    rsi: { value: 63.8, period: 14, interval: "5分钟", state: "near-overbought", direction: "rising", divergence: "none" },
    macd: { dif: 1.42, dea: 1.08, interval: "5分钟", histogram: [0.08, 0.12, 0.18, 0.25, 0.31, 0.34], state: "bull-expanding", crossover: "golden-cross" },
    reportedOwnership: {
      institutionalPercent: 65,
      insiderPercent: 4,
      otherPercent: 31,
      changes: ["演示：Top 20 报告机构净增持 1.8%", "演示：内部人持仓无重大变化"],
    },
    participation: {
      institutionalPercent: 58,
      retailPercent: 42,
      confidence: "medium",
      sourceCoverage: "演示成交与盘口特征覆盖 82%",
    },
    fundamentals: {
      financialHealth: "演示：现金流健康，估值偏高",
      cash: "$31.4B",
      debt: "$11.0B",
      dilution: "低",
      runway: "充足",
      margins: "毛利率 74%（演示）",
      growth: "收入同比 +122%（演示）",
      valuation: "远期估值高于行业中位数（演示）",
      materialRisks: ["出口限制", "客户集中", "高估值回撤"],
      industryContext: "AI 加速器需求强，但竞争与周期性存在。",
      supplyChainContext: "先进制程与封装产能是关键约束。",
    },
    marketContext: {
      marketDirection: "纳指短线偏强，但广度一般",
      sectorState: "半导体板块相对强势",
      macroState: "利率与美元对高估值板块仍有压制",
      geopoliticalState: "出口限制消息构成双向事件风险",
      scoreAdjustment: -3,
      planChanges: ["杠杆上限从 1.75x 降至 1.5x", "要求大盘广度同步改善"],
    },
  },
  {
    symbol: "TSLA",
    company: "Tesla",
    price: 318.2,
    changePercent: -1.2,
    forecastSlope: -1.1,
    baseScore: 56,
    adjustedScore: 53,
    conclusion: "中性偏空；事件分歧高，等待反弹量能确认。",
    counterCase: "若交付或利润率超预期，空头假设可能迅速失效。",
    rsi: { value: 47.2, period: 14, interval: "5分钟", state: "neutral", direction: "falling", divergence: "none" },
    macd: { dif: -0.82, dea: -0.64, interval: "5分钟", histogram: [-0.06, -0.09, -0.14, -0.19, -0.16, -0.12], state: "bear-contracting", crossover: "death-cross" },
    reportedOwnership: {
      institutionalPercent: 49,
      insiderPercent: 13,
      otherPercent: 38,
      changes: ["演示：报告机构持仓小幅下降 0.6%", "演示：内部人持仓变化待下一报告期确认"],
    },
    participation: {
      institutionalPercent: 44,
      retailPercent: 56,
      confidence: "low",
      sourceCoverage: "演示成交与盘口特征覆盖 64%",
    },
    fundamentals: {
      financialHealth: "演示：现金充足，汽车利润率承压",
      cash: "$36.6B",
      debt: "$7.5B",
      dilution: "中低",
      runway: "充足",
      margins: "汽车毛利率承压（演示）",
      growth: "交付增速存在分歧（演示）",
      valuation: "估值依赖新业务兑现（演示）",
      materialRisks: ["价格竞争", "交付波动", "关键人风险"],
      industryContext: "电动车需求增长放缓，储能与自动驾驶预期仍高。",
      supplyChainContext: "电池成本与区域产能利用率影响利润率。",
    },
    marketContext: {
      marketDirection: "成长股风险偏好尚可，但高波动个股分化",
      sectorState: "汽车与可选消费相对强度偏弱",
      macroState: "利率高位对远期叙事估值不利",
      geopoliticalState: "关税与区域监管构成双向事件风险",
      scoreAdjustment: -3,
      planChanges: ["不追空，等待反弹失败", "做空方案要求借券与事件日历确认"],
    },
  },
  {
    symbol: "PLTR",
    company: "Palantir",
    price: 86.4,
    changePercent: 0.8,
    forecastSlope: 0.12,
    baseScore: 49,
    adjustedScore: 46,
    conclusion: "趋势仍强但估值拥挤；只观察，不追涨。",
    counterCase: "若订单与商业收入持续超预期，估值压力可能被盈利上修抵消。",
    rsi: { value: 71.6, period: 14, interval: "5分钟", state: "overbought", direction: "rising", divergence: "bearish" },
    macd: { dif: 0.74, dea: 0.68, interval: "5分钟", histogram: [0.18, 0.16, 0.13, 0.1, 0.07, 0.04], state: "bull-contracting", crossover: "none" },
    reportedOwnership: {
      institutionalPercent: 44,
      insiderPercent: 7,
      otherPercent: 49,
      changes: ["演示：报告机构持仓增加 0.9%", "演示：持仓集中度仍低于大型科技股"],
    },
    participation: {
      institutionalPercent: 46,
      retailPercent: 54,
      confidence: "low",
      sourceCoverage: "演示成交与盘口特征覆盖 59%",
    },
    fundamentals: {
      financialHealth: "演示：无净债务，估值缓冲有限",
      cash: "$5.4B",
      debt: "$0.2B",
      dilution: "中",
      runway: "充足",
      margins: "调整后利润率改善（演示）",
      growth: "商业收入保持较快增长（演示）",
      valuation: "收入倍数显著高于行业（演示）",
      materialRisks: ["估值拥挤", "政府订单节奏", "股权激励稀释"],
      industryContext: "企业 AI 软件需求增长，合同兑现节奏重要。",
      supplyChainContext: "主要约束来自人才、算力成本与客户部署周期。",
    },
    marketContext: {
      marketDirection: "软件成长股强势，但市场广度不足",
      sectorState: "应用软件相对强势且拥挤度上升",
      macroState: "实际利率上行会压缩高久期估值",
      geopoliticalState: "政府合同与数据监管带来事件风险",
      scoreAdjustment: -3,
      planChanges: ["不使用突破追涨", "等待估值与量价共同降温"],
    },
  },
];

const buildStock = (profile: StockProfile, horizon: Horizon): StockSnapshot => {
  const scale = profile.price / 143.8;
  const sourcePrefix = profile.symbol.toLowerCase();
  const candles = buildCandles(profile.price);
  const horizonLabel = {
    short: "未来 5 个交易日",
    swing: "未来 1–8 周",
    long: "未来 2–24 个月",
  }[horizon];
  const invalidationPrice = profile.price * (profile.forecastSlope >= 0 ? 0.9485 : 1.052);

  return {
  demoData: true,
  symbol: profile.symbol,
  company: profile.company,
  exchange: "NASDAQ",
  marketSession: "美股盘中",
  watchlisted: true,
  horizon,
  price: profile.price,
  changePercent: profile.changePercent,
  quoteLatencyMs: 850,
  candles,
  forecast: {
    horizon: horizonLabel,
    points: Array.from({ length: 8 }, (_, index) => {
      const median = profile.price + profile.forecastSlope * (index + 1);
      const width50 = (1.4 + index * 0.35) * scale;
      return {
        timestamp: `T+${index + 1}`,
        median,
        lower50: median - width50,
        upper50: median + width50,
        lower80: median - width50 * 2.1,
        upper80: median + width50 * 2.1,
      };
    }),
    probability:
      profile.forecastSlope > 0.2
        ? { up: 0.58, flat: 0.18, down: 0.24 }
        : profile.forecastSlope < 0
          ? { up: 0.29, flat: 0.21, down: 0.5 }
          : { up: 0.41, flat: 0.25, down: 0.34 },
    calibrationError: 0.084,
    predictedAt: "2026-07-24T10:30:00-04:00",
    modelVersion: "demo-calibrated-v1",
    invalidation: `${profile.forecastSlope >= 0 ? "收盘跌破" : "收盘站上"} ${invalidationPrice.toFixed(2)} 或大盘环境反向`,
  },
  magicNine: {
    count: profile.symbol === "PLTR" ? 9 : profile.symbol === "TSLA" ? 4 : 7,
    complete: false,
    invalidation: "序列中断则重新计数",
    horizon,
  },
  dragonTrend: {
    state: profile.adjustedScore >= 60 ? "bullish" : profile.adjustedScore < 50 ? "bearish" : "neutral",
    score: profile.adjustedScore,
    methodVersion: "original-demo-v1",
    invalidation: "趋势强度跌破 45",
  },
  patterns: [
    {
      name: "回踩五日线后企稳",
      status: "forming",
      complete: false,
      invalidation: `收盘跌破 ${invalidationPrice.toFixed(2)}`,
      horizon,
    },
    {
      name: "三日底分型",
      status: "confirmed",
      complete: true,
      invalidation: "跌破分型最低点",
      horizon,
    },
    {
      name: "W底",
      status: "forming",
      complete: false,
      invalidation: "右底跌破左底",
      horizon,
    },
    {
      name: "头肩顶",
      status: "invalidated",
      complete: false,
      invalidation: "价格重新站上右肩",
      horizon,
    },
    {
      name: "回眸一笑",
      status: "forming",
      complete: false,
      invalidation: "均线重新转弱",
      horizon,
    },
  ],
  indicators: {
    rsi: profile.rsi,
    macd: profile.macd,
  },
  reportedOwnership: {
    ...profile.reportedOwnership,
    reportedAt: "2026-06-30",
    citationIds: [`${sourcePrefix}-source-1`],
  },
  participationProxy: {
    label: "估算代理",
    ...profile.participation,
    estimatedAt: "2026-07-24T10:30:00-04:00",
    methodVersion: "demo-v1",
    citationIds: [`${sourcePrefix}-source-2`],
  },
  marketContext: {
    ...profile.marketContext,
    citationIds: [`${sourcePrefix}-source-2`],
  },
  fundamentals: {
    ...profile.fundamentals,
    citationIds: [`${sourcePrefix}-source-1`],
  },
  baseScore: profile.baseScore,
  adjustedScore: profile.adjustedScore,
  conclusion: profile.conclusion,
  counterCase: profile.counterCase,
  citations: [
    {
      id: `${sourcePrefix}-source-1`,
      title: `演示：${profile.symbol} 机构持仓与财报快照`,
      publisher: "SEC",
      url: "https://www.sec.gov/",
      publishedAt: "2026-07-20T14:00:00Z",
      firstSeenAt: "2026-07-20T14:01:00Z",
      kind: "fact",
    },
    {
      id: `${sourcePrefix}-source-2`,
      title: `演示：${profile.symbol} 市场与成交结构快照`,
      publisher: "Demo Market Feed",
      url: "https://example.com/demo-market-feed",
      publishedAt: "2026-07-24T14:30:00Z",
      firstSeenAt: "2026-07-24T14:30:01Z",
      kind: "inference",
    },
  ],
  };
};

const horizons: Horizon[] = ["short", "swing", "long"];

export const stockFixtures: Record<string, StockSnapshot> = Object.fromEntries(
  stockProfiles.flatMap((profile) =>
    horizons.map((horizon) => [
      `${profile.symbol}:${horizon}`,
      buildStock(profile, horizon),
    ]),
  ),
);
