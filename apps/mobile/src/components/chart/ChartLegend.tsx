import { StyleSheet, Text, View } from "react-native";

import { colors, spacing } from "@/theme/tokens";

import { chartPalette, overlayColor } from "./chartPalette";

export type LegendItem = { key: string; label: string; color: string };

/**
 * One row, and only for marks that are actually on the chart.
 *
 * Rising and falling candles are not listed: the colour is the convention, and
 * spending a legend slot on it pushed the chart itself further down the page.
 */
export function ChartLegend({
  overlays,
  showForecast,
  showParticipation,
}: {
  overlays: { key: string; label: string }[];
  showForecast: boolean;
  showParticipation: boolean;
}) {
  const items: LegendItem[] = [
    ...overlays.map(({ key, label }) => ({
      key,
      label,
      color: overlayColor(key),
    })),
    ...(showParticipation
      ? [
          { key: "main", label: "主力代理", color: chartPalette.main },
          { key: "retail", label: "散户代理", color: chartPalette.retail },
        ]
      : []),
    ...(showForecast
      ? [
          { key: "band50", label: "50% 区间", color: chartPalette.forecastBand },
          {
            key: "band80",
            label: "80% 区间",
            color: chartPalette.forecastWideBand,
          },
          {
            key: "median",
            label: "预测中位",
            color: chartPalette.forecastMedian,
          },
        ]
      : []),
  ];

  if (!items.length) return null;

  return (
    <View accessibilityLabel="图表图例" style={styles.row}>
      {items.map((item) => (
        <View key={item.key} style={styles.item}>
          <View style={[styles.dot, { backgroundColor: item.color }]} />
          <Text style={styles.label}>{item.label}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  item: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.xs,
  },
  dot: { borderRadius: 4, height: 6, width: 6 },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700" },
});
