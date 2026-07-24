import { StyleSheet, Text, View } from "react-native";

import type { FundamentalSnapshot, PatternSignal, StockSnapshot } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type PatternCardProps = {
  patterns: PatternSignal[];
  magicNine: StockSnapshot["magicNine"];
  dragonTrend: StockSnapshot["dragonTrend"];
  fundamentals: FundamentalSnapshot;
  showTechnical?: boolean;
};

const statusLabel = {
  forming: "形成中",
  confirmed: "已确认",
  invalidated: "已失效",
} as const;

const directionLabel = {
  bullish: "偏多",
  neutral: "中性",
  bearish: "偏空",
} as const;

export function PatternCard({
  patterns,
  magicNine,
  dragonTrend,
  fundamentals,
  showTechnical = true,
}: PatternCardProps) {
  return (
    <View style={styles.stack}>
      {showTechnical ? <View style={styles.card}>
        <Text style={styles.title}>技术形态与原创指标</Text>
        <View style={styles.signalRow}>
          <View style={styles.signal}>
            <Text style={styles.signalLabel}>神奇九转</Text>
            <Text style={styles.signalValue}>
              {magicNine.count} / 9 · {magicNine.complete ? "完成" : "未完成"}
            </Text>
          </View>
          <View style={styles.signal}>
            <Text style={styles.signalLabel}>神龙趋势 · 原创</Text>
            <Text
              style={[
                styles.signalValue,
                dragonTrend.state === "bearish"
                  ? styles.bearish
                  : dragonTrend.state === "bullish"
                    ? styles.bullish
                    : styles.neutral,
              ]}>
              {directionLabel[dragonTrend.state]} {dragonTrend.score} / 100
            </Text>
          </View>
        </View>
        <Text style={styles.method}>
          神龙版本 {dragonTrend.methodVersion} · 失效：{dragonTrend.invalidation}
        </Text>
        <View style={styles.patterns}>
          {patterns.map((pattern) => (
            <View key={pattern.name} style={styles.pattern}>
              <Text style={styles.patternName}>{pattern.name}</Text>
              <Text
                style={[
                  styles.patternStatus,
                  pattern.status === "confirmed"
                    ? styles.confirmed
                    : pattern.status === "invalidated"
                      ? styles.invalidated
                      : styles.forming,
                ]}>
                {statusLabel[pattern.status]}
              </Text>
            </View>
          ))}
        </View>
      </View> : null}

      <View style={styles.card}>
        <Text style={styles.title}>财务健康与发展前景</Text>
        <Text style={styles.summary}>{fundamentals.financialHealth}</Text>
        <View style={styles.metrics}>
          {[
            ["现金", fundamentals.cash],
            ["债务", fundamentals.debt],
            ["增长", fundamentals.growth],
            ["毛利", fundamentals.margins],
          ].map(([label, value]) => (
            <View key={label} style={styles.metric}>
              <Text style={styles.metricLabel}>{label}</Text>
              <Text style={styles.metricValue}>{value}</Text>
            </View>
          ))}
        </View>
        <Text style={styles.context}>{fundamentals.industryContext}</Text>
        <Text style={styles.context}>供应链：{fundamentals.supplyChainContext}</Text>
        <Text style={styles.risk}>
          主要风险：{fundamentals.materialRisks.join(" · ")}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: spacing.sm },
  card: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.md,
  },
  title: { color: colors.ink, fontSize: 15, fontWeight: "900" },
  signalRow: { flexDirection: "row", gap: spacing.sm },
  signal: { backgroundColor: colors.background, borderRadius: radius.md, flex: 1, padding: spacing.sm },
  signalLabel: { color: colors.muted, fontSize: 9, fontWeight: "700" },
  signalValue: { color: colors.ink, fontSize: 11, fontWeight: "900", marginTop: 2 },
  bullish: { color: colors.green },
  neutral: { color: colors.muted },
  bearish: { color: colors.red },
  method: { color: colors.muted, fontSize: 9, lineHeight: 13 },
  patterns: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  pattern: { alignItems: "center", backgroundColor: colors.backgroundRaised, borderRadius: radius.pill, flexDirection: "row", gap: 5, paddingHorizontal: 8, paddingVertical: 5 },
  patternName: { color: colors.ink, fontSize: 9, fontWeight: "700" },
  patternStatus: { fontSize: 8, fontWeight: "900" },
  confirmed: { color: colors.green },
  invalidated: { color: colors.red },
  forming: { color: colors.amber },
  summary: { color: colors.muted, fontSize: 11, lineHeight: 16 },
  metrics: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  metric: { backgroundColor: colors.background, borderRadius: radius.sm, minWidth: "46%", padding: spacing.sm },
  metricLabel: { color: colors.muted, fontSize: 9, fontWeight: "700" },
  metricValue: { color: colors.ink, fontSize: 11, fontVariant: ["tabular-nums"], fontWeight: "800", marginTop: 2 },
  context: { color: colors.muted, fontSize: 10, lineHeight: 15 },
  risk: { backgroundColor: colors.redSoft, borderRadius: radius.sm, color: colors.red, fontSize: 10, fontWeight: "700", lineHeight: 15, overflow: "hidden", padding: spacing.sm },
});
