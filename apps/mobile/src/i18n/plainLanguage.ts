import type {
  CompletedTdSetup,
  MarketBriefDriverCoverage,
} from "@/domain/models";

/**
 * Fixed, versioned plain-language readings -- the mobile mirror of
 * `services/analysis_core/us_stock_helper_core/plain_language.py`.
 *
 * That module is the reviewed source of truth (versioned, methodology-
 * documented, exhaustively tested for completeness and banned verbs); this
 * file independently classifies the same finite states from the *already
 * wire-decoded, typed* fields the app has in hand (a market-brief driver's
 * `actionScore`, a decoded `magicNine` snapshot's `direction`/`count`/
 * `completed`/`perfected`) and carries the same Chinese copy. It does not
 * fetch the server's copy over the wire: Task 6/7 wire only breadth and
 * sector into `GET /market-brief`, and Magic Nine into the snapshot's
 * `magicNine` section -- both already typed and validated by
 * `@/data/marketGateway`'s decoders -- so classifying here is bucketing an
 * already-honest number, the same discipline `MagicNineMeter` and
 * `DataHealthBanner` already apply to other typed enums, not a client-side
 * re-derivation of a new metric from raw candles.
 *
 * 白话不喊单: `reading()` throws if a banned verb (买入/卖出/加仓/抄底/梭哈)
 * appears in either layer, at construction time -- so a violation breaks
 * every screen that imports this module, not just a test.
 */

export const PLAIN_LANGUAGE_VERSION = "plain-language-v1";

export const BANNED_VERBS = ["买入", "卖出", "加仓", "抄底", "梭哈"] as const;

export interface PlainReading {
  headline: string;
  explanation: string;
}

export interface PlainReadingNumbers {
  value: string;
  sampleSize: string;
  invalidation: string;
  /** An optional extra fact this indicator's numbers layer wants to carry
   * (e.g. Magic Nine's most recently completed run) -- shown after
   * `invalidation` when present. */
  note?: string;
}

export interface FullPlainReading extends PlainReading {
  numbers: PlainReadingNumbers;
}

/** Constructs a `PlainReading`, throwing if either layer carries a banned verb. */
export function reading(headline: string, explanation: string): PlainReading {
  if (!headline.trim()) throw new Error("a plain-language reading requires a headline");
  if (!explanation.trim()) {
    throw new Error("a plain-language reading requires an explanation");
  }
  for (const verb of BANNED_VERBS) {
    if (headline.includes(verb)) {
      throw new Error(`plain-language headline must never contain ${verb}: ${headline}`);
    }
    if (explanation.includes(verb)) {
      throw new Error(
        `plain-language explanation must never contain ${verb}: ${explanation}`,
      );
    }
  }
  return { headline, explanation };
}

// ---------------------------------------------------------------------------
// Breadth driver (GET /market-brief's "breadth" category, breadth-v1).
// Mirrors market_brief.py's own _breadth_label thresholds: actionScore is
// round(clamp((percent_above - 50) / 50), 6), so percent_above >= 55 is
// actionScore >= 0.1 and percent_above <= 45 is actionScore <= -0.1.
// ---------------------------------------------------------------------------

export type BreadthDriverState =
  | "breadth-strong"
  | "breadth-weak"
  | "breadth-mixed"
  | "breadth-unavailable";

const BREADTH_EXPLANATION =
  "广度看的不是大盘指数涨了多少，而是「有多少只股票真的在跟着涨」——就像班里" +
  "平均分不错，但可能只是几个学霸把分数拉高，其余同学没有进步。这里统计的是" +
  "自选列表里，收盘价站在自己50日均线上方的比例：值越高，说明参与上涨的股票" +
  "越多，而不是只有少数龙头在涨。这只统计自选列表，不是全市场，样本小时结论" +
  "也更容易受个别股票影响。";

const BREADTH_READINGS: Record<BreadthDriverState, PlainReading> = {
  "breadth-strong": reading(
    "自选列表里大多数股票都站上了自己的50日均线，参与上涨的股票较多。",
    BREADTH_EXPLANATION,
  ),
  "breadth-weak": reading(
    "自选列表里大多数股票都跌破了自己的50日均线，参与下跌的股票较多。",
    BREADTH_EXPLANATION,
  ),
  "breadth-mixed": reading(
    "自选列表里站上和跌破50日均线的股票数量差不多，涨跌互现，没有明显的一致方向。",
    BREADTH_EXPLANATION,
  ),
  "breadth-unavailable": reading(
    "自选广度暂不可用：历史K线不够计算50日均线。",
    BREADTH_EXPLANATION,
  ),
};

export function classifyBreadthDriver(
  entry: MarketBriefDriverCoverage,
): BreadthDriverState {
  if (!entry.available) return "breadth-unavailable";
  if (entry.actionScore === null) {
    throw new Error("breadth: an available entry must carry an actionScore");
  }
  if (entry.actionScore >= 0.1) return "breadth-strong";
  if (entry.actionScore <= -0.1) return "breadth-weak";
  return "breadth-mixed";
}

export function readBreadthDriver(
  entry: MarketBriefDriverCoverage,
): FullPlainReading {
  const state = classifyBreadthDriver(entry);
  return {
    ...BREADTH_READINGS[state],
    numbers: {
      value: entry.actionScore === null ? "暂无" : formatActionScore(entry.actionScore),
      sampleSize: "样本为当前自选列表（具体只数见上方结论文本）。",
      invalidation:
        "当自选列表为空、或历史K线不足以计算50日均线时，这个结论会变为不可用。",
    },
  };
}

// ---------------------------------------------------------------------------
// Sector driver (GET /market-brief's "sector" category, sector-rs-v1).
// ---------------------------------------------------------------------------

export type SectorDriverState =
  | "sector-rs-leading"
  | "sector-rs-lagging"
  | "sector-rs-unavailable";

const SECTOR_RS_EXPLANATION =
  "相对强弱比较的不是板块本身涨跌多少，而是它比基准（例如大盘ETF）跑赢还是" +
  "跑输——就像比较两个人跑步，不看谁跑得快，看谁比自己的平时水平进步更多、" +
  "又比对方多跑了几步。这里用的是板块最新收盘价相对自己均线的偏离幅度，减去" +
  "基准同样的偏离幅度：差值为正说明这段时间跑赢了基准，为负说明跑输了。";

const SECTOR_RS_READINGS: Record<SectorDriverState, PlainReading> = {
  "sector-rs-leading": reading(
    "当前领先的板块跑赢了基准，相对走势偏强。",
    SECTOR_RS_EXPLANATION,
  ),
  "sector-rs-lagging": reading(
    "当前排名靠前的板块也没有跑赢基准，板块轮动整体偏弱。",
    SECTOR_RS_EXPLANATION,
  ),
  "sector-rs-unavailable": reading(
    "板块强弱暂不可用：样本不足或历史数据不够计算相对强弱。",
    SECTOR_RS_EXPLANATION,
  ),
};

export function classifySectorDriver(
  entry: MarketBriefDriverCoverage,
): SectorDriverState {
  if (!entry.available) return "sector-rs-unavailable";
  if (entry.actionScore === null) {
    throw new Error("sector: an available entry must carry an actionScore");
  }
  return entry.actionScore > 0 ? "sector-rs-leading" : "sector-rs-lagging";
}

export function readSectorDriver(entry: MarketBriefDriverCoverage): FullPlainReading {
  const state = classifySectorDriver(entry);
  return {
    ...SECTOR_RS_READINGS[state],
    numbers: {
      value: entry.actionScore === null ? "暂无" : formatActionScore(entry.actionScore),
      sampleSize: "样本为已配置的板块 ETF 与基准（具体名单见上方结论文本）。",
      invalidation:
        "当板块 ETF 或基准未配置、或历史数据不足以计算相对强弱时，这个结论会变为不可用。",
    },
  };
}

function formatActionScore(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

// ---------------------------------------------------------------------------
// Magic Nine (chart badge + stock-page fact summary, td-setup-close-4-v2).
// Task 7. Mirrors plain_language.py's classify_magic_nine_progress /
// classify_magic_nine_last_completed against the wire-decoded snapshot
// shape (`ChartMagicNineSnapshot` / `MagicNineSnapshot`).
// ---------------------------------------------------------------------------

export type MagicNineProgressInput = {
  qualityStatus: string;
  direction: string | null;
  count: number;
  completed: boolean;
  perfected: boolean | null;
};

const MAGIC_NINE_EXPLANATION =
  "神奇九转（TD Setup）数的是：收盘价连续比「4根K线之前」的收盘价更低（看跌" +
  "方向）或更高（看涨方向）的次数，序列一旦中断（不再满足这个比较）就从头" +
  "开始数——就像数一串连续绿灯，闯一次红灯就得重新数。数到 9 本身不是买卖" +
  "信号，而是提醒这段单边走势已经持续很久，进入历史上更容易出现停顿或反转的" +
  "『警惕区』，仅此而已，不代表现在这一刻一定会反转。「完美」是在数到 9 之后" +
  "多看一眼第8、9根K线的最高/最低价有没有超过第6、7根——超过了才叫完美，是对" +
  "这次计数的一次额外确认；不完美不代表这次计数无效，只是确认强度弱一些。";

function directionKey(direction: string): "bullish" | "bearish" {
  if (direction === "bullish") return "bullish";
  if (direction === "bearish") return "bearish";
  throw new Error(`magic nine: unsupported direction: ${direction}`);
}

function countBucket(count: number): "early" | "mid" | "late" {
  if (count >= 1 && count <= 3) return "early";
  if (count >= 4 && count <= 6) return "mid";
  if (count >= 7 && count <= 8) return "late";
  throw new Error(`magic nine: unexpected in-progress count: ${count}`);
}

export function classifyMagicNineProgress(magicNine: MagicNineProgressInput): string {
  if (magicNine.qualityStatus === "unavailable") return "magic-nine-unavailable";
  if (magicNine.direction === null || magicNine.count === 0) {
    return "magic-nine-no-active-run";
  }
  const direction = directionKey(magicNine.direction);
  if (!magicNine.completed) {
    return `magic-nine-${direction}-${countBucket(magicNine.count)}`;
  }
  if (magicNine.perfected === true) return `magic-nine-${direction}-complete-perfected`;
  if (magicNine.perfected === false) return `magic-nine-${direction}-complete-unperfected`;
  return `magic-nine-${direction}-complete-unknown`;
}

const MAGIC_NINE_PROGRESS_HEADLINE_TEMPLATES: Record<string, string> = {
  "magic-nine-unavailable": "神奇九转暂不可用：这次没有足够的K线数据来计数。",
  "magic-nine-no-active-run":
    "当前没有正在进行中的九转计数：最近一次的连续比较被打断了，计数已经清零" +
    "重新开始。",
  "magic-nine-bullish-early":
    "上涨方向的九转刚数到 {count}——离『警惕反转』的 9 还早，当前只是记录" +
    "趋势的持续性。",
  "magic-nine-bearish-early":
    "下跌方向的九转刚数到 {count}——离『警惕反转』的 9 还早，当前只是记录" +
    "趋势的持续性。",
  "magic-nine-bullish-mid":
    "上涨方向的九转已经数到 {count}，过了一半但还没到 9，继续观察即可，" +
    "不是操作提示。",
  "magic-nine-bearish-mid":
    "下跌方向的九转已经数到 {count}，过了一半但还没到 9，继续观察即可，" +
    "不是操作提示。",
  "magic-nine-bullish-late":
    "上涨方向的九转数到 {count}，非常接近 9，进入需要多留意的『警惕反转』" +
    "临界阶段，但仍然不是操作提示。",
  "magic-nine-bearish-late":
    "下跌方向的九转数到 {count}，非常接近 9，进入需要多留意的『警惕反转』" +
    "临界阶段，但仍然不是操作提示。",
  "magic-nine-bullish-complete-perfected":
    "上涨方向的九转刚好数满 9，并且通过了『完美』的额外确认——是这轮单边" +
    "走势持续最久、最值得留意反转风险的时刻，但依然只是提醒，不是操作提示。",
  "magic-nine-bearish-complete-perfected":
    "下跌方向的九转刚好数满 9，并且通过了『完美』的额外确认——是这轮单边" +
    "走势持续最久、最值得留意反转风险的时刻，但依然只是提醒，不是操作提示。",
  "magic-nine-bullish-complete-unperfected":
    "上涨方向的九转刚好数满 9，但没有通过『完美』的额外确认——提醒依然成立，" +
    "只是确认强度弱一些。",
  "magic-nine-bearish-complete-unperfected":
    "下跌方向的九转刚好数满 9，但没有通过『完美』的额外确认——提醒依然成立，" +
    "只是确认强度弱一些。",
  "magic-nine-bullish-complete-unknown":
    "上涨方向的九转刚好数满 9，但这次没有进行『完美』核对，无法判断是否通过" +
    "确认。",
  "magic-nine-bearish-complete-unknown":
    "下跌方向的九转刚好数满 9，但这次没有进行『完美』核对，无法判断是否通过" +
    "确认。",
};

export function magicNineProgressReading(
  magicNine: MagicNineProgressInput,
): PlainReading {
  const state = classifyMagicNineProgress(magicNine);
  const template = MAGIC_NINE_PROGRESS_HEADLINE_TEMPLATES[state];
  if (template === undefined) {
    throw new Error(`magic nine: no plain-language copy for state ${state}`);
  }
  const headline =
    !magicNine.completed && magicNine.direction !== null && magicNine.count > 0
      ? template.replace("{count}", String(magicNine.count))
      : template;
  return reading(headline, MAGIC_NINE_EXPLANATION);
}

export type MagicNineLastCompletedState =
  | "magic-nine-last-completed-none"
  | "magic-nine-last-completed-bullish-perfected"
  | "magic-nine-last-completed-bullish-unperfected"
  | "magic-nine-last-completed-bearish-perfected"
  | "magic-nine-last-completed-bearish-unperfected";

const MAGIC_NINE_LAST_COMPLETED_READINGS: Record<
  MagicNineLastCompletedState,
  PlainReading
> = {
  "magic-nine-last-completed-none": reading(
    "目前还没有出现过完整数到 9 的九转记录。",
    MAGIC_NINE_EXPLANATION,
  ),
  "magic-nine-last-completed-bullish-perfected": reading(
    "最近一次数满 9 的九转方向是上涨，并且通过了『完美』确认——这是历史记录，" +
      "不代表现在这一刻还成立。",
    MAGIC_NINE_EXPLANATION,
  ),
  "magic-nine-last-completed-bullish-unperfected": reading(
    "最近一次数满 9 的九转方向是上涨，但没有通过『完美』确认——这是历史记录，" +
      "不代表现在这一刻还成立。",
    MAGIC_NINE_EXPLANATION,
  ),
  "magic-nine-last-completed-bearish-perfected": reading(
    "最近一次数满 9 的九转方向是下跌，并且通过了『完美』确认——这是历史记录，" +
      "不代表现在这一刻还成立。",
    MAGIC_NINE_EXPLANATION,
  ),
  "magic-nine-last-completed-bearish-unperfected": reading(
    "最近一次数满 9 的九转方向是下跌，但没有通过『完美』确认——这是历史记录，" +
      "不代表现在这一刻还成立。",
    MAGIC_NINE_EXPLANATION,
  ),
};

export function classifyMagicNineLastCompleted(
  last: CompletedTdSetup | null,
): MagicNineLastCompletedState {
  if (last === null) return "magic-nine-last-completed-none";
  const direction = directionKey(last.direction);
  const suffix = last.perfected ? "perfected" : "unperfected";
  return `magic-nine-last-completed-${direction}-${suffix}` as MagicNineLastCompletedState;
}

export function magicNineLastCompletedReading(
  last: CompletedTdSetup | null,
): PlainReading {
  return MAGIC_NINE_LAST_COMPLETED_READINGS[classifyMagicNineLastCompleted(last)];
}

/** The full three-layer reading for the stock page's Magic Nine badge. */
export function readMagicNine(
  magicNine: MagicNineProgressInput,
  lastCompleted: CompletedTdSetup | null,
): FullPlainReading {
  const progress = magicNineProgressReading(magicNine);
  const value =
    magicNine.qualityStatus === "unavailable" || magicNine.direction === null
      ? "暂不可用"
      : `${magicNine.count}/9`;
  return {
    ...progress,
    numbers: {
      value,
      sampleSize: "基于价格序列本身的连续计数，不涉及统计学意义上的历史样本量。",
      invalidation:
        "计数中断（收盘价不再单调偏离4根K线前的收盘价）就会重新计数，当前进度" +
        "作废；已经数满的9不会因为后续行情被撤销，但也不代表接下来一定反转。",
      ...(lastCompleted !== null
        ? { note: magicNineLastCompletedReading(lastCompleted).headline }
        : {}),
    },
  };
}
