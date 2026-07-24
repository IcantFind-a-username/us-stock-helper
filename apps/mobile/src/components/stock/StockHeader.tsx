import { SymbolView } from "expo-symbols";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { StockSnapshot } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

const symbols = {
  back: { android: "arrow_back", ios: "chevron.left", web: "arrow_back" },
  star: { android: "star", ios: "star.fill", web: "star" },
} as const;

type StockHeaderProps = {
  stock: StockSnapshot;
  onBack(): void;
};

export function StockHeader({ stock, onBack }: StockHeaderProps) {
  const positive = stock.changePercent >= 0;
  return (
    <View style={styles.wrap}>
      <View style={styles.topRow}>
        <Pressable
          accessibilityLabel="返回"
          accessibilityRole="button"
          onPress={onBack}
          style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}>
          <SymbolView name={symbols.back} size={19} tintColor={colors.ink} />
        </Pressable>
        <View style={styles.identity}>
          <Text style={styles.symbol}>{stock.symbol}</Text>
          <View style={styles.companyRow}>
            <Text style={styles.company}>{stock.company}</Text>
            <Text style={styles.exchange}>{stock.exchange}</Text>
          </View>
        </View>
        <View accessibilityLabel={stock.watchlisted ? "已在关注列表" : "未关注"} style={styles.iconButton}>
          <SymbolView
            name={symbols.star}
            size={18}
            tintColor={stock.watchlisted ? colors.amber : colors.muted}
          />
        </View>
      </View>
      <View style={styles.quoteRow}>
        <View>
          <Text style={styles.price}>${stock.price.toFixed(2)}</Text>
          <Text style={[styles.change, { color: positive ? colors.green : colors.red }]}>
            {positive ? "+" : ""}
            {stock.changePercent.toFixed(2)}% · {positive ? "上涨" : "下跌"}
          </Text>
        </View>
        <View style={styles.meta}>
          <Text style={styles.session}>{stock.marketSession}</Text>
          <Text style={styles.latency}>延迟 {stock.quoteLatencyMs} ms</Text>
          <Text style={styles.demo}>演示数据 · 非实时行情</Text>
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
  identity: { flex: 1, marginHorizontal: spacing.sm },
  symbol: { color: colors.ink, fontSize: 20, fontWeight: "900" },
  companyRow: { alignItems: "center", flexDirection: "row", gap: spacing.xs, marginTop: 1 },
  company: { color: colors.muted, fontSize: 10, fontWeight: "700" },
  exchange: { color: colors.muted, fontSize: 9, fontWeight: "600" },
  quoteRow: { alignItems: "flex-end", flexDirection: "row", justifyContent: "space-between" },
  price: {
    color: colors.ink,
    fontSize: 28,
    fontVariant: ["tabular-nums"],
    fontWeight: "900",
    letterSpacing: -0.8,
  },
  change: { fontSize: 12, fontVariant: ["tabular-nums"], fontWeight: "800" },
  meta: { alignItems: "flex-end", gap: 1 },
  session: { color: colors.ink, fontSize: 10, fontWeight: "800" },
  latency: { color: colors.muted, fontSize: 9, fontWeight: "600" },
  demo: { color: colors.muted, fontSize: 9, fontWeight: "600" },
});
