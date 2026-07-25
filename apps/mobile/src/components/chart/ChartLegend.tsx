import { StyleSheet, Text, View } from "react-native";

import { colors, spacing } from "@/theme/tokens";

const baseItems = [
  { label: "上涨", color: colors.green },
  { label: "下跌", color: colors.red },
] as const;

export function ChartLegend({
  showForecast,
  showMovingAverage,
}: {
  showForecast: boolean;
  showMovingAverage: boolean;
}) {
  const items = [
    ...baseItems,
    ...(showMovingAverage ? [{ label: "MA5", color: colors.amber }] : []),
    ...(showForecast
      ? [
          { label: "50% 区间", color: colors.blue },
          { label: "80% 区间", color: colors.blueBright },
          { label: "预测中位", color: colors.purple },
        ]
      : []),
  ];
  return (
    <View accessibilityLabel="图表图例" style={styles.legend}>
      <View style={styles.row}>
        {items.map((item) => (
          <View key={item.label} style={styles.item}>
            <View style={[styles.dot, { backgroundColor: item.color }]} />
            <Text style={styles.label}>{item.label}</Text>
          </View>
        ))}
      </View>
      <View style={styles.participation}>
        <View style={[styles.bar, styles.mainBar]} />
        <View style={[styles.bar, styles.retailBar]} />
        <Text style={styles.participationLabel}>
          订单规模活动占比 · 深色主力代理 / 浅色散户代理
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  legend: {
    gap: spacing.xs,
  },
  row: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  item: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.xs,
  },
  dot: {
    borderRadius: 4,
    height: 6,
    width: 6,
  },
  label: {
    color: colors.muted,
    fontSize: 9,
    fontWeight: "700",
  },
  participation: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.xs,
  },
  bar: {
    height: 7,
    width: 5,
  },
  mainBar: {
    backgroundColor: colors.blue,
  },
  retailBar: {
    backgroundColor: colors.navyMuted,
  },
  participationLabel: {
    color: colors.navyMuted,
    flexShrink: 1,
    fontSize: 9,
    fontWeight: "700",
  },
});
