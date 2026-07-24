import { StyleSheet, Text, View } from "react-native";

import type { MacdSnapshot, RsiSnapshot } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

const rsiStateLabels: Record<RsiSnapshot["state"], string> = {
  oversold: "超卖",
  neutral: "中性",
  "near-overbought": "接近超买",
  overbought: "超买",
};

const rsiDirectionLabels: Record<RsiSnapshot["direction"], string> = {
  rising: "向上",
  flat: "走平",
  falling: "向下",
};

const macdStateLabels: Record<MacdSnapshot["state"], string> = {
  "bull-expanding": "多头扩张",
  "bull-contracting": "多头收缩",
  "bear-expanding": "空头扩张",
  "bear-contracting": "空头收缩",
};

const divergenceLabels: Record<RsiSnapshot["divergence"], string> = {
  bullish: "看涨背离",
  none: "无背离",
  bearish: "看跌背离",
};

type IndicatorStripProps = {
  rsi: RsiSnapshot;
  macd: MacdSnapshot;
};

const shortTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};

export function IndicatorStrip({ rsi, macd }: IndicatorStripProps) {
  const histogramMax = Math.max(...macd.histogram.map(Math.abs), 0.01);
  const normalizedRsi = Math.max(0, Math.min(100, rsi.value));
  const bearishMacd = macd.state.startsWith("bear-");
  return (
    <View style={styles.row}>
      <View style={styles.card} testID="indicator-rsi">
        <View style={styles.headingRow}>
          <Text style={styles.title}>{`RSI ${rsi.value.toFixed(1)}`}</Text>
          <Text style={styles.warm}>{rsiStateLabels[rsi.state]}</Text>
        </View>
        <View style={styles.rsiTrack}>
          <View style={[styles.rsiFill, { width: `${normalizedRsi}%` }]} />
          <View
            style={[styles.threshold, { left: "30%" }]}
            testID="rsi-threshold-30"
          />
          <View
            style={[styles.threshold, { left: "70%" }]}
            testID="rsi-threshold-70"
          />
        </View>
        <Text style={styles.meta}>
          {`${rsi.interval} · ${rsi.period}期 · ${rsiDirectionLabels[rsi.direction]} · ${divergenceLabels[rsi.divergence]}`}
        </Text>
        <Text style={styles.asOf}>仅用已收盘 K 线 · 截止 {shortTime(rsi.asOf)}</Text>
      </View>

      <View style={styles.card} testID="indicator-macd">
        <View style={styles.headingRow}>
          <Text style={styles.title}>MACD</Text>
          <Text style={bearishMacd ? styles.bad : styles.good}>
            {macdStateLabels[macd.state]}
          </Text>
        </View>
        <View style={styles.histogram}>
          <View style={styles.zeroAxis} testID="macd-zero-axis" />
          {macd.histogram.map((value, index) => {
            const height = 2 + (Math.abs(value) / histogramMax) * 13;
            return (
              <View key={`${value}-${index}`} style={styles.histogramSlot}>
                <View
                  style={[
                    styles.histogramBar,
                    {
                      backgroundColor: value >= 0 ? colors.green : colors.red,
                      height,
                      [value >= 0 ? "bottom" : "top"]: 14,
                    },
                  ]}
                />
              </View>
            );
          })}
        </View>
        <Text style={styles.meta}>
          {`${macd.interval} · DIF ${macd.dif.toFixed(2)} · DEA ${macd.dea.toFixed(2)} · ${
            macd.crossover === "golden-cross"
              ? "金叉"
              : macd.crossover === "death-cross"
                ? "死叉"
                : "无交叉"
          }`}
        </Text>
        <Text style={styles.asOf}>仅用已收盘 K 线 · 截止 {shortTime(macd.asOf)}</Text>
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
  headingRow: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
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
  histogram: { flexDirection: "row", gap: 3, height: 28, position: "relative" },
  zeroAxis: {
    backgroundColor: colors.line,
    height: StyleSheet.hairlineWidth,
    left: 0,
    position: "absolute",
    right: 0,
    top: 14,
  },
  histogramSlot: { flex: 1, height: 28, position: "relative" },
  histogramBar: { borderRadius: 2, left: 0, minWidth: 3, position: "absolute", right: 0 },
  meta: { color: colors.muted, fontSize: 9, fontWeight: "600", lineHeight: 13 },
  asOf: { color: colors.muted, fontSize: 8, fontWeight: "600" },
});
