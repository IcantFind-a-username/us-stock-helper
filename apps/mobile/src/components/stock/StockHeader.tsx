import { SymbolView } from "expo-symbols";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { ChartSnapshot } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

const backSymbol = {
  android: "arrow_back",
  ios: "chevron.left",
  web: "arrow_back",
} as const;

type StockHeaderProps = {
  stock: ChartSnapshot;
  onBack(): void;
};

function formatUtc(value: string) {
  return value.replace("T", " ").replace(".000Z", " UTC");
}

export function StockHeader({ stock, onBack }: StockHeaderProps) {
  const positive = stock.quote.changePercent >= 0;

  return (
    <View style={styles.wrap}>
      <View style={styles.topRow}>
        <Pressable
          accessibilityLabel="返回"
          accessibilityRole="button"
          onPress={onBack}
          style={({ pressed }) => [
            styles.iconButton,
            pressed && styles.pressed,
          ]}>
          <SymbolView name={backSymbol} size={19} tintColor={colors.ink} />
        </Pressable>
        <Text style={styles.symbol}>{stock.symbol}</Text>
        <View
          accessibilityLabel={
            stock.demoData ? "演示数据，非实时行情" : "实时只读行情"
          }
          style={[
            styles.sourceBadge,
            stock.demoData && styles.demoSourceBadge,
          ]}>
          <Text
            style={[
              styles.sourceText,
              stock.demoData && styles.demoSourceText,
            ]}>
            {stock.demoData ? "演示数据" : "实时只读"}
          </Text>
        </View>
      </View>
      <View style={styles.quoteRow}>
        <View>
          <Text style={styles.price}>${stock.quote.price.toFixed(2)}</Text>
          <Text
            style={[
              styles.change,
              { color: positive ? colors.green : colors.red },
            ]}>
            {positive ? "+" : ""}
            {stock.quote.changePercent.toFixed(2)}%
          </Text>
        </View>
        <View style={styles.meta}>
          <Text style={styles.interval}>{stock.interval}</Text>
          <Text style={styles.asOf}>截止 {formatUtc(stock.quote.asOf)}</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  topRow: { alignItems: "center", flexDirection: "row" },
  iconButton: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderRadius: radius.round,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  pressed: { opacity: 0.65 },
  symbol: {
    color: colors.ink,
    flex: 1,
    fontSize: 20,
    fontWeight: "900",
    marginHorizontal: spacing.sm,
  },
  sourceBadge: {
    backgroundColor: colors.blueSoft,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  demoSourceBadge: { backgroundColor: colors.amberSoft },
  sourceText: { color: colors.blue, fontSize: 9, fontWeight: "900" },
  demoSourceText: { color: "#8B5C08" },
  quoteRow: {
    alignItems: "flex-end",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  price: {
    color: colors.ink,
    fontSize: 28,
    fontVariant: ["tabular-nums"],
    fontWeight: "900",
    letterSpacing: -0.8,
  },
  change: {
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
  },
  meta: { alignItems: "flex-end", gap: 2 },
  interval: { color: colors.ink, fontSize: 10, fontWeight: "800" },
  asOf: { color: colors.muted, fontSize: 9, fontWeight: "600" },
});
