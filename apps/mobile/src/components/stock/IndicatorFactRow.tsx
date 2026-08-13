import { StyleSheet, Text, View } from "react-native";

import type {
  ChartIndicatorValue,
  ChartMacdIndicator,
} from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

function lastHistogram(value: ChartMacdIndicator["histogram"]) {
  return Array.isArray(value) ? (value.at(-1) ?? null) : value;
}

/**
 * The latest value of each indicator, stated once per page.
 *
 * The chart panels carry the shape of these indicators, so repeating them in a
 * second card left the page as an even wall of text with nothing leading it.
 */
export function IndicatorFactRow({
  ma5,
  rsi,
  macd,
  realizedVolatility,
}: {
  ma5: ChartIndicatorValue;
  rsi: ChartIndicatorValue;
  macd: ChartMacdIndicator;
  /** undefined on demo snapshots, which never carried a volatility field. */
  realizedVolatility: number | null | undefined;
}) {
  const histogram = lastHistogram(macd.histogram);
  return (
    <View style={styles.row} testID="indicator-fact-row">
      <Text style={styles.fact}>
        MA5 {ma5.value === null ? "暂不可用" : ma5.value.toFixed(2)}
      </Text>
      <Text style={styles.fact}>
        RSI {rsi.value === null ? "暂不可用" : rsi.value.toFixed(1)}
      </Text>
      <Text style={styles.fact}>
        MACD {histogram === null ? "暂不可用" : histogram.toFixed(2)}
      </Text>
      <Text style={styles.fact}>
        年化波动{" "}
        {realizedVolatility === null || realizedVolatility === undefined
          ? "暂不可用"
          : `${(realizedVolatility * 100).toFixed(1)}%`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  fact: {
    backgroundColor: colors.background,
    borderRadius: radius.pill,
    color: colors.ink,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
    overflow: "hidden",
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
});
