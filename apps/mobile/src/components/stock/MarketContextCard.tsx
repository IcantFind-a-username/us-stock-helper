import { StyleSheet, Text, View } from "react-native";

import type { MarketContext } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type MarketContextCardProps = {
  context: MarketContext;
};

export function MarketContextCard({ context }: MarketContextCardProps) {
  const factors = [
    ["大盘", context.marketDirection],
    ["行业", context.sectorState],
    ["宏观", context.macroState],
    ["地缘", context.geopoliticalState],
  ] as const;

  return (
    <View style={styles.card} testID="market-context-card">
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>同一时间点快照 · {formatAsOf(context.asOf)}</Text>
          <Text style={styles.title}>大盘 · 宏观 · 地缘上下文</Text>
        </View>
        <Text style={[styles.adjustment, context.scoreAdjustment < 0 && styles.negative]}>
          调整 {context.scoreAdjustment > 0 ? "+" : ""}
          {context.scoreAdjustment}
        </Text>
      </View>
      {factors.map(([label, value]) => (
        <View key={label} style={styles.factor}>
          <Text style={styles.factorLabel}>{label}</Text>
          <View style={styles.factorCopy}>
            <Text style={styles.factorValue}>{value}</Text>
          </View>
        </View>
      ))}
      <View style={styles.constraint}>
        <Text style={styles.constraintTitle}>对建议的实际约束</Text>
        {context.planChanges.map((change) => (
          <Text key={change} style={styles.constraintBody}>
            · {change}
          </Text>
        ))}
      </View>
    </View>
  );
}

function formatAsOf(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", {
        hour12: false,
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.md,
  },
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  eyebrow: { color: colors.muted, fontSize: 9, fontWeight: "700" },
  title: { color: colors.ink, fontSize: 15, fontWeight: "900", marginTop: 1 },
  adjustment: {
    backgroundColor: colors.greenSoft,
    borderRadius: radius.pill,
    color: colors.green,
    fontSize: 10,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  negative: { backgroundColor: colors.redSoft, color: colors.red },
  factor: { alignItems: "flex-start", flexDirection: "row", gap: spacing.sm },
  factorLabel: {
    backgroundColor: colors.background,
    borderRadius: radius.sm,
    color: colors.ink,
    fontSize: 9,
    fontWeight: "900",
    minWidth: 35,
    overflow: "hidden",
    paddingHorizontal: 6,
    paddingVertical: 4,
    textAlign: "center",
  },
  factorCopy: { flex: 1, paddingTop: 2 },
  factorValue: { color: colors.muted, fontSize: 11, fontWeight: "600", lineHeight: 15 },
  constraint: { backgroundColor: colors.amberSoft, borderRadius: radius.md, gap: 3, padding: spacing.sm },
  constraintTitle: { color: "#704B05", fontSize: 10, fontWeight: "900" },
  constraintBody: { color: "#8B5C08", fontSize: 10, lineHeight: 14 },
});
