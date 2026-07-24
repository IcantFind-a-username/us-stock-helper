import { Pressable, StyleSheet, Text, View } from "react-native";

import type { AlertThread } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type PriorityAlertCardProps = {
  alert: AlertThread;
  onPress(): void;
  onOpenDetail?(): void;
  onOpenEvidence?(title: string, citationIds: string[]): void;
};

const freshnessLabel = { fresh: "新鲜", stale: "可能延迟", conflict: "存在冲突" } as const;

export function PriorityAlertCard({ alert, onPress, onOpenDetail, onOpenEvidence }: PriorityAlertCardProps) {
  const openDetail = onOpenDetail ?? (() => onOpenEvidence?.(`${alert.symbol} 提醒证据`, alert.citations.map((citation) => citation.id)));

  return (
    <View testID="priority-alert-card" style={styles.card}>
      <Pressable
        accessibilityLabel={`查看 ${alert.symbol} 提醒详情：${alert.title}`}
        accessibilityRole="button"
        onPress={onPress}
        style={styles.mainAction}>
        <View style={styles.copy}>
          <View style={styles.tickerLine}>
            <Text style={styles.symbol}>{alert.symbol}</Text>
            <Text style={styles.badge}>{alert.currentState}</Text>
          </View>
          <Text numberOfLines={1} style={styles.title}>{alert.title}</Text>
          <Text numberOfLines={2} style={styles.summary}>{alert.summary}</Text>
          <Text style={styles.meta}>
            证据 {alert.evidenceCount} · 反证 {alert.counterEvidenceCount} · {" "}
            {freshnessLabel[alert.sourceFreshness]}
          </Text>
        </View>
        <View style={styles.scorePill}>
          <Text style={styles.score}>
            {alert.baseScoreContribution > 0 ? "+" : ""}
            {alert.baseScoreContribution}
          </Text>
          <Text style={styles.scoreLabel}>基础贡献</Text>
        </View>
      </Pressable>
      <Pressable
        accessibilityLabel={`查看 ${alert.symbol} 提醒依据`}
        accessibilityRole="button"
        onPress={openDetail}
        style={styles.evidenceAction}>
        <Text style={styles.evidenceText}>依据 ›</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: radius.md, padding: spacing.md },
  mainAction: { alignItems: "center", flexDirection: "row", gap: spacing.sm, minHeight: 86 },
  copy: { flex: 1, minWidth: 0 },
  tickerLine: { alignItems: "center", flexDirection: "row", gap: spacing.xs },
  symbol: { color: colors.ink, fontSize: 14, fontWeight: "800" },
  badge: { backgroundColor: colors.amberSoft, borderRadius: radius.pill, color: colors.amber, fontSize: 10, fontWeight: "800", paddingHorizontal: spacing.xs, paddingVertical: 2 },
  title: { color: colors.ink, fontSize: 15, fontWeight: "800", marginTop: 2 },
  summary: { color: colors.muted, fontSize: 12, lineHeight: 17, marginTop: 2 },
  meta: { color: colors.muted, fontSize: 11, marginTop: spacing.xs },
  scorePill: { alignItems: "center", backgroundColor: colors.blueSoft, borderRadius: radius.md, minWidth: 52, paddingHorizontal: spacing.sm, paddingVertical: spacing.xs },
  score: { color: colors.blue, fontSize: 16, fontVariant: ["tabular-nums"], fontWeight: "800" },
  scoreLabel: { color: colors.muted, fontSize: 9, fontWeight: "700" },
  evidenceAction: { alignItems: "flex-end", justifyContent: "center", minHeight: 44 },
  evidenceText: { color: colors.blue, fontSize: 11, fontWeight: "800" },
});
