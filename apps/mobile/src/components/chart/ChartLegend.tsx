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
    <View accessibilityLabel="图表图例" style={styles.row}>
      {items.map((item) => (
        <View key={item.label} style={styles.item}>
          <View style={[styles.dot, { backgroundColor: item.color }]} />
          <Text style={styles.label}>{item.label}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
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
});
