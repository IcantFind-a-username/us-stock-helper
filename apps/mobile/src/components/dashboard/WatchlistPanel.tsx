import { Pressable, StyleSheet, Text, View, type TextStyle } from "react-native";

import { DashboardSectionHeader } from "@/components/dashboard/DashboardSectionHeader";
import type { WatchlistQuote } from "@/domain/models";
import { describeMarketError } from "@/i18n/marketErrorCopy";
import { gateLabel } from "@/i18n/serverVocabulary";
import type { WatchlistDecisionState } from "@/state/MarketDataProvider";
import { colors, radius, spacing } from "@/theme/tokens";

/**
 * How many rows the dashboard shows before the reader asks for the rest. A
 * watchlist of dozens of symbols does not fit above the fold, but the ones
 * beyond this count are hidden, never dropped: the panel always states the
 * full size and offers the way to the rest.
 */
export const COLLAPSED_WATCHLIST_COUNT = 8;

/**
 * The screen slices with this same helper when it decides which symbols to
 * score, so what is displayed and what is requested cannot drift apart.
 */
export function visibleWatchlistQuotes<T>(
  quotes: readonly T[],
  expanded: boolean,
): T[] {
  return expanded ? [...quotes] : quotes.slice(0, COLLAPSED_WATCHLIST_COUNT);
}

type WatchlistPanelProps = {
  accessibilityLabel: string;
  quotes: WatchlistQuote[];
  decisions: Record<string, WatchlistDecisionState>;
  expanded: boolean;
  onToggleExpanded(): void;
  onPress(symbol: string): void;
  onOpenSource(): void;
};

const directionCopy = { bullish: "上涨", neutral: "持平", bearish: "下跌" } as const;
const scoreDirectionCopy = {
  bullish: "偏多",
  neutral: "中性",
  bearish: "偏空",
} as const;

type ScoreCell = {
  /** What the number column shows; never empty, even with no score. */
  value: string;
  meta: string;
  spoken: string;
  tone: TextStyle;
};

function scoreCell(state: WatchlistDecisionState | undefined): ScoreCell {
  // A row the screen has not asked about yet is pending, not scoreless.
  if (state === undefined || state.status === "loading") {
    return {
      value: "…",
      meta: "读取中",
      spoken: "评分读取中",
      tone: styles.scorePending,
    };
  }
  if (state.status === "demo") {
    return {
      value: "—",
      meta: "演示无评分",
      spoken: "演示模式不提供评分",
      tone: styles.scorePending,
    };
  }
  if (state.status === "unavailable") {
    // The row has one short column for this, so the reader gets the four-word
    // name of the failure here and the whole sentence when the row is spoken
    // or opened. What it must never be again is the wire category: "malformed"
    // in a Chinese list told the reader nothing at all.
    const copy = describeMarketError(state.error?.category ?? "offline");
    return {
      value: "—",
      meta: `不可用 · ${copy.label}`,
      spoken: `评分不可用 · ${copy.title}`,
      tone: styles.scoreMissing,
    };
  }
  if (state.score === null) {
    return {
      value: "—",
      meta: "未给出评分",
      spoken: "分析未给出评分",
      tone: styles.scoreMissing,
    };
  }
  if (!state.score.actionable) {
    // The engine computed a number but refused to act on it. Showing it with
    // the same direction/coverage line and green "strong" tone as a clean
    // score is the exact defect DecisionCard's blocked banner exists to
    // avoid on the stock screen — the watchlist row must read as gated too.
    const value = Math.round(state.score.value);
    const gates = state.score.blockedBy;
    const meta = gates.length ? `不可行动 · ${gates.map(gateLabel).join("、")}` : "不可行动";
    return {
      value: String(value),
      meta,
      spoken: `评分 ${value} · ${meta}`,
      tone: styles.scoreBlocked,
    };
  }
  const value = Math.round(state.score.value);
  const direction = scoreDirectionCopy[state.score.direction];
  // Coverage travels with the score because a number built on part of the
  // factors is not the same claim as one built on all of them.
  const coverage = Math.round(state.score.factorCoverage * 100);
  return {
    value: String(value),
    meta: `${direction} · 覆盖 ${coverage}%`,
    spoken: `评分 ${value} · ${direction} · 因子覆盖 ${coverage}%`,
    tone: scoreTone(value),
  };
}

export function WatchlistPanel({
  accessibilityLabel,
  quotes,
  decisions,
  expanded,
  onToggleExpanded,
  onOpenSource,
  onPress,
}: WatchlistPanelProps) {
  const visible = visibleWatchlistQuotes(quotes, expanded);
  const hidden = quotes.length - visible.length;

  return (
    <View accessibilityLabel={accessibilityLabel}>
      <DashboardSectionHeader
        actionLabel="来自 moomoo ›"
        onAction={onOpenSource}
        title="我的关注"
      />
      <Text style={styles.count} testID="watchlist-count">
        {`共 ${quotes.length} 只 · ${
          hidden === 0 ? "已全部显示" : `已显示 ${visible.length} 只`
        }`}
      </Text>
      <View style={styles.list} testID="watchlist-list">
        {visible.map((quote) => {
          const cell = scoreCell(decisions[quote.symbol]);
          const changeSign = quote.changePercent >= 0 ? "+" : "";
          return (
            <Pressable
              accessibilityLabel={`查看 ${quote.symbol} 行情详情：$${quote.price.toFixed(2)}，${changeSign}${quote.changePercent.toFixed(2)}%，${directionCopy[quote.direction]}，当前脉冲 ${quote.summary}，${cell.spoken}`}
              accessibilityRole="button"
              key={quote.symbol}
              onPress={() => onPress(quote.symbol)}
              style={styles.row}
              testID="watchlist-quote">
              <View style={styles.identity}>
                <Text style={styles.symbol}>{quote.symbol}</Text>
                <Text numberOfLines={1} style={styles.pulse}>
                  {quote.summary}
                </Text>
              </View>
              <View style={styles.quoteColumn}>
                <Text style={styles.price}>
                  {`$${quote.price.toFixed(2)}`}
                </Text>
                <Text style={[styles.change, toneFor(quote.direction)]}>
                  {`${changeSign}${quote.changePercent.toFixed(2)}%`}
                </Text>
              </View>
              <View style={styles.scoreColumn}>
                <Text
                  style={[styles.scoreValue, cell.tone]}
                  testID={`watchlist-score-${quote.symbol}`}>
                  {cell.value}
                </Text>
                <Text style={styles.scoreMeta}>{cell.meta}</Text>
              </View>
            </Pressable>
          );
        })}
      </View>
      {quotes.length > COLLAPSED_WATCHLIST_COUNT ? (
        <Pressable
          accessibilityLabel={
            expanded ? "收起自选列表" : `查看全部 ${quotes.length} 只自选`
          }
          accessibilityRole="button"
          onPress={onToggleExpanded}
          style={styles.expand}
          testID="watchlist-expand">
          <Text style={styles.expandText}>
            {expanded ? "收起" : `查看全部 ${quotes.length} 只 ›`}
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function toneFor(direction: WatchlistQuote["direction"]) {
  if (direction === "bullish") return styles.up;
  if (direction === "bearish") return styles.down;
  return styles.flat;
}

function scoreTone(value: number) {
  if (value >= 70) return styles.scoreStrong;
  if (value <= 40) return styles.scoreWeak;
  return styles.scoreMixed;
}

const styles = StyleSheet.create({
  count: { color: colors.muted, fontSize: 11, fontWeight: "700", marginBottom: spacing.xs },
  list: { gap: 6 },
  row: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: spacing.sm,
    minHeight: 56,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  identity: { flex: 1, gap: 2, minWidth: 0 },
  symbol: { color: colors.ink, fontSize: 14, fontWeight: "800" },
  pulse: { color: colors.muted, fontSize: 11 },
  quoteColumn: { alignItems: "flex-end", gap: 2 },
  price: {
    color: colors.ink,
    fontSize: 13,
    fontVariant: ["tabular-nums"],
    fontWeight: "700",
  },
  change: { fontSize: 12, fontVariant: ["tabular-nums"], fontWeight: "800" },
  scoreColumn: { alignItems: "flex-end", gap: 2, minWidth: 92 },
  scoreValue: { fontSize: 16, fontVariant: ["tabular-nums"], fontWeight: "900" },
  scoreMeta: { color: colors.muted, fontSize: 11, fontWeight: "700" },
  scoreStrong: { color: colors.green },
  scoreMixed: { color: colors.amber },
  scoreWeak: { color: colors.red },
  scorePending: { color: colors.muted },
  scoreMissing: { color: colors.muted },
  scoreBlocked: { color: colors.amber },
  up: { color: colors.green },
  down: { color: colors.red },
  flat: { color: colors.muted },
  expand: {
    alignItems: "center",
    backgroundColor: colors.blueSoft,
    borderRadius: radius.md,
    justifyContent: "center",
    marginTop: spacing.sm,
    minHeight: 44,
  },
  expandText: { color: colors.blue, fontSize: 12, fontWeight: "800" },
});
