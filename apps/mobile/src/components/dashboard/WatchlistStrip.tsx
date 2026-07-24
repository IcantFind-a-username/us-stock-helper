import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import type { WatchlistQuote } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type WatchlistStripProps = {
  title: string;
  quotes: WatchlistQuote[];
  onPress(symbol: string): void;
};

const directionCopy = { bullish: "上涨", neutral: "持平", bearish: "下跌" } as const;

export function WatchlistStrip({ title, quotes, onPress }: WatchlistStripProps) {
  return (
    <View accessibilityLabel="自选行情，演示" style={styles.card}>
      <Text style={styles.marker}>演示</Text>
      <Text style={styles.title}>{title}</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.quotes} testID="watchlist-scroll">
        {quotes.map((quote) => (
          <Pressable
            accessibilityHint="前往股票详情"
            accessibilityLabel={`查看 ${quote.symbol} 行情详情：$${quote.price.toFixed(2)}，${quote.changePercent >= 0 ? "+" : ""}${quote.changePercent.toFixed(2)}%，${directionCopy[quote.direction]}，当前脉冲 ${quote.summary}`}
            accessibilityRole="button"
            key={quote.symbol}
            onPress={() => onPress(quote.symbol)}
            style={styles.quote}>
            <View style={styles.quoteCopy}>
              <Text style={styles.symbol}>{quote.symbol}</Text>
              <Text style={styles.pulse}>当前脉冲：{quote.summary}</Text>
            </View>
            <View style={styles.priceArea}>
              <Text style={styles.price}>${quote.price.toFixed(2)}</Text>
              <Text style={[styles.change, quote.direction === "bearish" ? styles.down : quote.direction === "bullish" ? styles.up : styles.flat]}>{quote.changePercent >= 0 ? "+" : ""}{quote.changePercent.toFixed(2)}% · {directionCopy[quote.direction]}</Text>
            </View>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: radius.lg, padding: spacing.lg },
  marker: { color: colors.amber, fontSize: 11, fontWeight: "800" },
  title: { color: colors.ink, fontSize: 17, fontWeight: "800", marginBottom: spacing.sm },
  quotes: { gap: spacing.sm, paddingVertical: spacing.xs },
  quote: { alignItems: "center", backgroundColor: colors.background, borderColor: colors.line, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, flexDirection: "row", gap: spacing.sm, justifyContent: "space-between", minHeight: 64, padding: spacing.sm, width: 176 },
  quoteCopy: { flex: 1, minWidth: 0 },
  symbol: { color: colors.ink, fontSize: 15, fontWeight: "800" },
  pulse: { color: colors.muted, fontSize: 12, marginTop: 2 },
  priceArea: { alignItems: "flex-end", flexShrink: 0 },
  price: { color: colors.ink, fontSize: 14, fontVariant: ["tabular-nums"], fontWeight: "800" },
  change: { fontSize: 12, fontVariant: ["tabular-nums"], fontWeight: "700", marginTop: 2 },
  up: { color: colors.green },
  down: { color: colors.red },
  flat: { color: colors.muted },
});
