import { StyleSheet, Text, View } from "react-native";

import type {
  ChartIndicatorValue,
  ChartMacdIndicator,
} from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type IndicatorStripProps = {
  rsi: ChartIndicatorValue;
  macd: ChartMacdIndicator;
};

function formatUtc(value: string) {
  return value.replace("T", " ").replace(".000Z", " UTC");
}

function rsiLabel(value: number) {
  if (value >= 70) return "超买";
  if (value >= 60) return "接近超买";
  if (value <= 30) return "超卖";
  return "中性";
}

function lastHistogram(value: ChartMacdIndicator["histogram"]) {
  return Array.isArray(value) ? (value.at(-1) ?? null) : value;
}

export function IndicatorStrip({ rsi, macd }: IndicatorStripProps) {
  const histogram = lastHistogram(macd.histogram);
  const rsiAvailable = rsi.qualityStatus !== "unavailable" && rsi.value !== null;
  const macdAvailable =
    macd.qualityStatus !== "unavailable" &&
    macd.line !== null &&
    macd.signal !== null &&
    histogram !== null;
  const normalizedRsi = Math.max(0, Math.min(100, rsi.value ?? 0));

  return (
    <View style={styles.row}>
      <View style={styles.card} testID="indicator-rsi">
        <View style={styles.headingRow}>
          <Text style={styles.title}>
            {rsiAvailable ? `RSI ${rsi.value!.toFixed(1)}` : "RSI 暂不可用"}
          </Text>
          <Text style={styles.warm}>
            {rsiAvailable ? rsiLabel(rsi.value!) : "缺失"}
          </Text>
        </View>
        <View style={styles.rsiTrack}>
          <View
            style={[
              styles.rsiFill,
              { width: `${rsiAvailable ? normalizedRsi : 0}%` },
            ]}
          />
          <View
            style={[styles.threshold, { left: "30%" }]}
            testID="rsi-threshold-30"
          />
          <View
            style={[styles.threshold, { left: "70%" }]}
            testID="rsi-threshold-70"
          />
        </View>
        <Text style={styles.meta}>{rsi.methodVersion}</Text>
        <Text style={styles.asOf}>
          仅用已完成 K 线 · 截止 {formatUtc(rsi.asOf)}
        </Text>
      </View>

      <View style={styles.card} testID="indicator-macd">
        <View style={styles.headingRow}>
          <Text style={styles.title}>MACD</Text>
          <Text
            style={
              !macdAvailable
                ? styles.warm
                : macd.line! >= macd.signal!
                  ? styles.good
                  : styles.bad
            }>
            {!macdAvailable
              ? "暂不可用"
              : macd.line! >= macd.signal!
                ? "多头"
                : "空头"}
          </Text>
        </View>
        <View style={styles.histogram}>
          <View style={styles.zeroAxis} testID="macd-zero-axis" />
          {macdAvailable ? (
            <View
              style={[
                styles.histogramBar,
                histogram! >= 0 ? styles.positiveBar : styles.negativeBar,
                { height: 4 + Math.min(Math.abs(histogram!) * 24, 18) },
              ]}
            />
          ) : null}
        </View>
        <Text style={styles.meta}>
          {macdAvailable
            ? `DIF ${macd.line!.toFixed(2)} · DEA ${macd.signal!.toFixed(2)} · 柱 ${histogram!.toFixed(2)}`
            : macd.methodVersion}
        </Text>
        <Text style={styles.asOf}>
          仅用已完成 K 线 · 截止 {formatUtc(macd.asOf)}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", gap: spacing.sm },
  card: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    flex: 1,
    gap: spacing.sm,
    minHeight: 112,
    padding: spacing.md,
  },
  headingRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  title: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  warm: { color: colors.amber, fontSize: 9, fontWeight: "800" },
  good: { color: colors.green, fontSize: 9, fontWeight: "800" },
  bad: { color: colors.red, fontSize: 9, fontWeight: "800" },
  rsiTrack: {
    backgroundColor: colors.background,
    borderRadius: radius.pill,
    height: 9,
    overflow: "hidden",
    position: "relative",
  },
  rsiFill: { backgroundColor: colors.amber, height: "100%", opacity: 0.85 },
  threshold: {
    backgroundColor: colors.ink,
    height: "100%",
    opacity: 0.4,
    position: "absolute",
    width: 1,
  },
  histogram: {
    alignItems: "center",
    height: 28,
    justifyContent: "center",
    position: "relative",
  },
  zeroAxis: {
    backgroundColor: colors.line,
    height: StyleSheet.hairlineWidth,
    left: 0,
    position: "absolute",
    right: 0,
    top: 14,
  },
  histogramBar: {
    borderRadius: 2,
    position: "absolute",
    width: "42%",
  },
  positiveBar: { backgroundColor: colors.green, bottom: 14 },
  negativeBar: { backgroundColor: colors.red, top: 14 },
  meta: {
    color: colors.muted,
    fontSize: 9,
    fontWeight: "600",
    lineHeight: 13,
  },
  asOf: { color: colors.muted, fontSize: 8, fontWeight: "600" },
});
