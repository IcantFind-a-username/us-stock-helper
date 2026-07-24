import { Pressable, StyleSheet, Text, View } from "react-native";

import type { AlertThread } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type PriorityAlertCardProps = {
  alert: AlertThread;
  onPress(): void;
  onOpenEvidence(title: string, citationIds: string[]): void;
};

const freshnessLabel = { fresh: "新鲜", stale: "可能延迟", conflict: "存在冲突" } as const;

export function PriorityAlertCard({ alert, onPress, onOpenEvidence }: PriorityAlertCardProps) {
  return (
    <View accessibilityLabel="优先提醒，演示" style={styles.card}>
      <Text style={styles.marker}>演示</Text>
      <Text style={styles.title}>{alert.title}</Text>
      <Text style={styles.summary}>{alert.summary}</Text>
      <Text style={styles.detail}>触发：{alert.triggeredAt}</Text>
      <Text style={styles.detail}>当前状态：{alert.currentState}</Text>
      <Text style={styles.detail}>证据 {alert.evidenceCount} · 反证 {alert.counterEvidenceCount}</Text>
      <Text style={styles.detail}>新鲜度：{freshnessLabel[alert.sourceFreshness]}</Text>
      <Text style={styles.detail}>更新时间：{alert.updatedAt}</Text>
      {alert.adviserAdjustment === null ? null : <Text style={styles.detail}>顾问调整 {alert.adviserAdjustment >= 0 ? "+" : ""}{alert.adviserAdjustment}</Text>}
      <Text style={styles.label}>失效条件</Text>
      <Text style={styles.detail}>{alert.invalidation}</Text>
      <View style={styles.actions}>
        <Pressable accessibilityHint="打开此提醒的演示引用" accessibilityLabel={`查看 ${alert.symbol} 提醒证据：当前状态 ${alert.currentState}，证据 ${alert.evidenceCount}，反证 ${alert.counterEvidenceCount}，新鲜度 ${freshnessLabel[alert.sourceFreshness]}`} accessibilityRole="button" onPress={() => onOpenEvidence(`${alert.symbol} 提醒证据`, alert.citations.map((citation) => citation.id))} style={styles.evidenceButton}>
          <Text style={styles.evidenceText}>查看证据</Text>
        </Pressable>
        <Pressable accessibilityHint="前往股票详情" accessibilityLabel={`查看 ${alert.symbol} 提醒详情：${alert.title}，当前状态 ${alert.currentState}，新鲜度 ${freshnessLabel[alert.sourceFreshness]}`} accessibilityRole="button" onPress={onPress} style={styles.detailButton}>
          <Text style={styles.detailText}>查看详情</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: radius.lg, gap: spacing.xs, padding: spacing.lg },
  marker: { color: colors.amber, fontSize: 11, fontWeight: "800" },
  title: { color: colors.ink, fontSize: 17, fontWeight: "800" },
  summary: { color: colors.muted, fontSize: 14, lineHeight: 20, marginBottom: spacing.xs },
  label: { color: colors.ink, fontSize: 13, fontWeight: "800", marginTop: spacing.xs },
  detail: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  evidenceButton: { alignItems: "center", backgroundColor: colors.blueSoft, borderRadius: radius.md, flex: 1, justifyContent: "center", minHeight: 44, paddingHorizontal: spacing.sm },
  detailButton: { alignItems: "center", backgroundColor: colors.navy, borderRadius: radius.md, flex: 1, justifyContent: "center", minHeight: 44, paddingHorizontal: spacing.sm },
  evidenceText: { color: colors.blue, fontSize: 13, fontWeight: "800" },
  detailText: { color: colors.card, fontSize: 13, fontWeight: "800" },
});
