import { Pressable, StyleSheet, Text, View } from "react-native";

import type { AlertThread } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type AlertThreadCardProps = {
  alert: AlertThread;
  onOpen(): void;
  onOpenEvidence(): void;
};

const severityCopy = {
  info: "信息",
  observation: "观察",
  action: "行动研究",
  risk: "风险",
} as const;

const freshnessCopy = {
  fresh: "新鲜",
  stale: "延迟",
  conflict: "冲突",
} as const;

export function AlertThreadCard({
  alert,
  onOpen,
  onOpenEvidence,
}: AlertThreadCardProps) {
  return (
    <View style={styles.card}>
      <Pressable
        accessibilityLabel={`打开 ${alert.symbol} 个股分析`}
        accessibilityRole="button"
        onPress={onOpen}
        style={({ pressed }) => [styles.main, pressed && styles.pressed]}>
        <View style={styles.top}>
          <View style={styles.symbolWrap}>
            <Text style={styles.symbol}>{alert.symbol}</Text>
            <Text style={[styles.severity, severityStyle(alert.severity)]}>
              {severityCopy[alert.severity]}
            </Text>
            <Text style={styles.freshness}>{freshnessCopy[alert.sourceFreshness]}</Text>
          </View>
          <View style={styles.score}>
            <Text style={[styles.scoreValue, alert.baseScoreContribution < 0 && styles.negative]}>
              {alert.baseScoreContribution > 0 ? "+" : ""}
              {alert.baseScoreContribution}
            </Text>
            <Text style={styles.scoreLabel}>基础贡献</Text>
          </View>
        </View>
        <Text style={styles.title}>{alert.title}</Text>
        <Text numberOfLines={2} style={styles.summary}>{alert.summary}</Text>
        <View style={styles.metaRow}>
          <Text style={styles.meta}>{alert.currentState}</Text>
          <Text style={styles.meta}>
            证据 {alert.evidenceCount} · 反证 {alert.counterEvidenceCount}
          </Text>
        </View>
        {alert.adviserAdjustment === null ? null : (
          <Text style={styles.adviser}>
            顾问软因子 {alert.adviserAdjustment > 0 ? "+" : ""}
            {alert.adviserAdjustment} · 不能独立触发
          </Text>
        )}
      </Pressable>
      <Pressable
        accessibilityLabel={`查看 ${alert.symbol} 提醒依据`}
        accessibilityRole="button"
        onPress={onOpenEvidence}
        style={({ pressed }) => [styles.evidence, pressed && styles.pressed]}>
        <Text style={styles.evidenceText}>
          {alert.updatedAt.slice(11, 16)} 更新 · 查看证据与失效条件 ›
        </Text>
      </Pressable>
    </View>
  );
}

function severityStyle(severity: AlertThread["severity"]) {
  if (severity === "risk") return styles.risk;
  if (severity === "action") return styles.action;
  if (severity === "observation") return styles.observation;
  return styles.info;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: "hidden",
  },
  main: { gap: 5, minHeight: 122, padding: spacing.md },
  top: { alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between" },
  symbolWrap: { alignItems: "center", flexDirection: "row", gap: spacing.xs },
  symbol: { color: colors.ink, fontSize: 14, fontWeight: "900" },
  severity: {
    borderRadius: radius.pill,
    fontSize: 8,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 6,
    paddingVertical: 3,
  },
  risk: { backgroundColor: colors.redSoft, color: colors.red },
  action: { backgroundColor: colors.greenSoft, color: colors.green },
  observation: { backgroundColor: colors.amberSoft, color: colors.amber },
  info: { backgroundColor: colors.blueSoft, color: colors.blue },
  freshness: { color: colors.muted, fontSize: 8, fontWeight: "800" },
  score: { alignItems: "flex-end" },
  scoreValue: { color: colors.green, fontSize: 17, fontWeight: "900" },
  negative: { color: colors.red },
  scoreLabel: { color: colors.muted, fontSize: 8, fontWeight: "800" },
  title: { color: colors.ink, fontSize: 13, fontWeight: "900", lineHeight: 18 },
  summary: { color: colors.muted, fontSize: 10, lineHeight: 15 },
  metaRow: { flexDirection: "row", justifyContent: "space-between" },
  meta: { color: colors.ink, fontSize: 8, fontWeight: "800" },
  adviser: { color: colors.purple, fontSize: 8, fontWeight: "800" },
  evidence: {
    alignItems: "flex-end",
    borderTopColor: colors.line,
    borderTopWidth: StyleSheet.hairlineWidth,
    justifyContent: "center",
    minHeight: 44,
    paddingHorizontal: spacing.md,
  },
  evidenceText: { color: colors.blue, fontSize: 9, fontWeight: "900" },
  pressed: { opacity: 0.66 },
});
