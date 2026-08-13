/**
 * The one place where server vocabulary becomes Chinese.
 *
 * The services answer in English and in their own identifiers — `stale_data`,
 * `institutional_flow`, "Analysis only: …" — and that is theirs to keep: those
 * strings are the wire contract and the audit trail, and rewriting them at the
 * source would change what the service means. The screen is a different
 * matter. Its reader reads Chinese, so the turn happens here, on the way to
 * the screen and nowhere else.
 *
 * Two rules hold everywhere in this file:
 *
 * 1. A term this table has no entry for is returned untouched. Text the reader
 *    cannot parse is a worse outcome than nothing at all only if you never
 *    consider the third outcome — a line that quietly disappears, taking the
 *    service's own caveat with it. Absence is the one thing this app must
 *    never manufacture, so the identifier goes on screen as it arrived.
 * 2. Every table lives here. A second copy elsewhere drifts, and the same gate
 *    then reads two different ways on two screens.
 */

/** Scoring factors, as named by the analysis service's FeatureSet. */
const FACTOR_NAMES: Record<string, string> = {
  technical_trend: "技术趋势",
  momentum: "动量",
  pattern: "形态",
  market_sentiment: "市场情绪",
  macro: "宏观",
  geopolitics: "地缘政治",
  institutional_flow: "机构资金",
  fundamentals: "基本面",
};

/** Hard gates: the reasons the engine refuses to call a score actionable. */
const GATE_NAMES: Record<string, string> = {
  stale_data: "数据陈旧",
  insufficient_evidence: "证据不足",
  conflicting_evidence: "证据冲突",
  unverified_rumor: "未证实传闻",
  low_liquidity: "流动性不足",
  borrow_unavailable: "无券可借",
  borrow_data_stale: "融券数据陈旧",
};

const PLAN_ACTIONS: Record<string, string> = {
  long: "做多",
  short: "做空",
  watch: "观望",
  avoid: "回避",
};

const SCORE_DIRECTIONS: Record<string, string> = {
  bullish: "偏多",
  neutral: "中性",
  bearish: "偏空",
};

const SCENARIO_KINDS: Record<string, string> = {
  bear: "下行",
  base: "基准",
  bull: "上行",
};

// Transport failure categories are deliberately absent from this file. They
// are named in @/i18n/marketErrorCopy, which answers more than a label can:
// what was refused, by whom, and whether the reader can do anything about it.

const CANDLE_INTERVALS: Record<string, string> = {
  "1m": "1 分钟",
  "5m": "5 分钟",
  "15m": "15 分钟",
  "30m": "30 分钟",
  "60m": "60 分钟",
  day: "日线",
  week: "周线",
  // Demo snapshots carry the horizon in place of a real cadence. The screen
  // states the demo status separately, so the label carries only the horizon.
  "demo-short": "短线",
  "demo-swing": "波段",
  "demo-long": "长线",
};

const SNAPSHOT_SOURCES: Record<string, string> = {
  // moomoo is the provider's own name, not an identifier to translate.
  fixture: "演示数据",
  "analysis-core": "分析内核",
  "moomoo-delayed-institutional-disclosure": "moomoo 延迟机构披露",
};

const CHART_STATUSES: Record<string, string> = {
  demo: "演示数据",
  live: "实时只读",
  stale: "缓存数据",
};

/**
 * Sentences the services emit verbatim, from the risk planner, the forecaster,
 * the analysis API and the market gateway's participation and volatility
 * estimators.
 */
const SERVICE_SENTENCES: Record<string, string> = {
  "Analysis only: this plan cannot submit, route, or execute an order.":
    "仅供分析：本方案不会提交、路由或执行任何委托。",
  "Scenario ranges are uncertain and require independent confirmation before any decision.":
    "情景区间带有不确定性，做任何决定前都要独立核实。",
  "Forecast calibration status is uncalibrated.": "预测尚未经过校准。",
  "Scenarios are uncertain analytical ranges, not promised prices.":
    "情景是带不确定性的分析区间，不是承诺的价格。",
  "Realized volatility could not be measured, so no scenario range is offered.":
    "无法测得已实现波动率，因此不给出情景区间。",
  "No completed candles were available at the decision cutoff.":
    "决策截止时点上没有任何已完成 K 线。",
  "Capital-flow participation is unavailable for this snapshot.":
    "本次快照没有资金流参与结构数据。",
  "unsupported interval in v1": "v1 尚不支持该周期",
  "unsupported intraday cadence": "不支持的日内节奏",
  "mixed session flow points": "资金流数据跨越了不同交易时段",
  "incomplete minute coverage": "分钟级覆盖不完整",
  "capital flow unavailable": "本次快照没有资金流数据",
  "zero activity denominator": "活动量分母为零",
  "no price variation in the observed window": "观察窗口内价格没有任何变化",
};

/**
 * Sentences the services assemble at runtime, so the numbers and identifiers
 * inside them have to be carried across rather than looked up.
 */
const SERVICE_PATTERNS: {
  pattern: RegExp;
  translate(match: RegExpExecArray): string;
}[] = [
  {
    // The server joins raw gate values into this line, so the sentence and the
    // identifiers inside it are translated by the same table.
    pattern: /^Hard gate active: (.+)$/,
    translate: (match) =>
      `已触发硬性拦截：${match[1]!
        .split(",")
        .map((gate) => gateLabel(gate.trim()))
        .join("、")}`,
  },
  {
    pattern:
      /^Scored on (\d+)% of the factor weight; the rest has no source yet\.$/,
    translate: (match) => `评分只用到 ${match[1]}% 的因子权重，其余因子暂时没有数据源。`,
  },
  {
    pattern:
      /^(\d+) cited item\(s\) are older than the configured freshness window and are marked stale\.$/,
    translate: (match) => `有 ${match[1]} 条引用超出设定的新鲜度窗口，已标记为陈旧。`,
  },
  {
    pattern: /^insufficient sample: (\d+) of (\d+) returns$/,
    translate: (match) => `样本不足：需要 ${match[2]} 条收益率，只有 ${match[1]} 条。`,
  },
];

export function factorLabel(factor: string): string {
  return FACTOR_NAMES[factor] ?? factor;
}

export function gateLabel(gate: string): string {
  return GATE_NAMES[gate] ?? gate;
}

export function planActionLabel(action: string): string {
  return PLAN_ACTIONS[action] ?? action;
}

export function scoreDirectionLabel(direction: string): string {
  return SCORE_DIRECTIONS[direction] ?? direction;
}

export function scenarioLabel(kind: string): string {
  return SCENARIO_KINDS[kind] ?? kind;
}

export function intervalLabel(interval: string): string {
  return CANDLE_INTERVALS[interval] ?? interval;
}

export function snapshotSourceLabel(source: string): string {
  return SNAPSHOT_SOURCES[source] ?? source;
}

export function chartStatusLabel(status: string): string {
  return CHART_STATUSES[status] ?? status;
}

/**
 * Turns one free-text line from a service into Chinese, or hands it back.
 *
 * `notes` and `warnings` are prose the services write, and they add to that
 * prose whenever a new caveat is worth stating. A line this table has never
 * seen is therefore expected, not exceptional, and it reaches the screen
 * untouched: an English caveat the reader must puzzle over still tells them
 * something, and a dropped one tells them the opposite of the truth.
 */
export function serviceTextLabel(text: string): string {
  const trimmed = text.trim();
  const sentence = SERVICE_SENTENCES[trimmed];
  if (sentence !== undefined) return sentence;
  for (const { pattern, translate } of SERVICE_PATTERNS) {
    const match = pattern.exec(trimmed);
    if (match) return translate(match);
  }
  return text;
}
