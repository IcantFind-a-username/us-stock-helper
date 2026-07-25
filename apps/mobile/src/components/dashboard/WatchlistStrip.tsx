import { Pressable, StyleSheet, Text, View } from "react-native";

import { DashboardSectionHeader } from "@/components/dashboard/DashboardSectionHeader";
import { MiniSparkline } from "@/components/ui/MiniSparkline";
import type { WatchlistQuote } from "@/domain/models";
import { colors } from "@/theme/tokens";

type WatchlistStripProps = {
  accessibilityLabel: string;
  title?: string;
  quotes: WatchlistQuote[];
  onPress(symbol: string): void;
  onOpenSource(): void;
};

const directionCopy = { bullish: "上涨", neutral: "持平", bearish: "下跌" } as const;

export function WatchlistStrip({
  accessibilityLabel,
  quotes,
  onOpenSource,
  onPress,
}: WatchlistStripProps) {
  return (
    <View accessibilityLabel={accessibilityLabel}>
      <DashboardSectionHeader
        actionLabel="来自 moomoo ›"
        onAction={onOpenSource}
        title="我的关注"
      />
      <View style={styles.grid} testID="watchlist-grid">
        {quotes.slice(0, 3).map((quote) => (
          <Pressable
            accessibilityLabel={`查看 ${quote.symbol} 行情详情：$${quote.price.toFixed(2)}，${quote.changePercent >= 0 ? "+" : ""}${quote.changePercent.toFixed(2)}%，${directionCopy[quote.direction]}，当前脉冲 ${quote.summary}`}
            accessibilityRole="button"
            key={quote.symbol}
            onPress={() => onPress(quote.symbol)}
            style={styles.quote}
            testID="watchlist-quote">
            <View style={styles.quoteTop}>
              <Text style={styles.symbol}>{quote.symbol}</Text>
              <Text style={[styles.change, toneFor(quote.direction)]}>
                {quote.changePercent >= 0 ? "+" : ""}
                {quote.changePercent.toFixed(1)}%
              </Text>
            </View>
            <MiniSparkline direction={quote.direction} width={74} />
            <Text numberOfLines={1} style={styles.pulse}>{quote.summary}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function toneFor(direction: WatchlistQuote["direction"]) {
  if (direction === "bullish") return styles.up;
  if (direction === "bearish") return styles.down;
  return styles.flat;
}

const styles = StyleSheet.create({
  grid: { flexDirection: "row", gap: 7 },
  quote: { backgroundColor: colors.card, borderColor: colors.line, borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, flex: 1, gap: 4, minHeight: 86, minWidth: 0, padding: 9 },
  quoteTop: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  symbol: { color: colors.ink, fontSize: 12, fontWeight: "800" },
  change: { fontSize: 10, fontVariant: ["tabular-nums"], fontWeight: "800" },
  pulse: { color: colors.muted, fontSize: 10 },
  up: { color: colors.green },
  down: { color: colors.red },
  flat: { color: colors.muted },
});
