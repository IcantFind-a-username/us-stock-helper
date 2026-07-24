import { Pressable, StyleSheet, Text, View } from "react-native";

import type { MarketDriver } from "@/domain/models";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { colors, radius, spacing } from "@/theme/tokens";

type MarketPlaybookCardProps = {
  score: number;
  confidence: number;
  scoreChange: number;
  conclusion: string;
  advice: string;
  invalidation: string;
  contradictions: string[];
  drivers: MarketDriver[];
  updatedAt: string;
  onOpenEvidence(citationIds: string[]): void;
};

export const normalizedWidth = (score: number) =>
  `${Math.min(Math.abs(score), 100)}%` as `${number}%`;

const freshnessLabel = { fresh: "新鲜", stale: "可能延迟", conflict: "存在冲突" } as const;

export function MarketPlaybookCard({
  score,
  confidence,
  scoreChange,
  conclusion,
  advice,
  invalidation,
  contradictions,
  drivers,
  updatedAt,
  onOpenEvidence,
}: MarketPlaybookCardProps) {
  const citationIds = [...new Set(drivers.flatMap((driver) => driver.citationIds))];

  return (
    <View accessibilityLabel="市场行动手册，演示" style={styles.card}>
      <View style={styles.heading}>
        <View>
          <Text style={styles.eyebrow}>演示</Text>
          <Text style={styles.title}>市场行动手册</Text>
        </View>
        <ScoreBadge label="市场评分" score={score} />
      </View>
      <Text style={styles.conclusion}>{conclusion}</Text>
      <View style={styles.metrics}>
        <Text style={styles.metric}>置信度 {Math.round(confidence * 100)}%</Text>
        <Text style={styles.metric}>评分变动 {scoreChange >= 0 ? "+" : ""}{scoreChange}</Text>
      </View>

      <Text style={styles.label}>为什么</Text>
      <Text style={styles.copy}>{advice}</Text>
      <Text style={styles.label}>今日建议</Text>
      <Text style={styles.copy}>当前策略 / 风险姿态：控制仓位，先等证据确认。</Text>

      <Text style={styles.label}>最强反证</Text>
      {contradictions.map((contradiction) => <Text key={contradiction} style={styles.bullet}>• {contradiction}</Text>)}
      <Text style={styles.label}>失效条件</Text>
      <Text style={styles.copy}>{invalidation}</Text>

      <View style={styles.driverHeader}>
        <Text style={styles.label}>驱动因素</Text>
        <Text style={styles.scale}>固定刻度 −100 至 +100</Text>
      </View>
      {drivers.map((driver) => (
        <Pressable
          accessibilityHint="查看该驱动因素的演示引用"
          accessibilityLabel={`查看 ${driver.label} 证据`}
          accessibilityRole="button"
          key={driver.id}
          onPress={() => onOpenEvidence(driver.citationIds)}
          style={styles.driver}>
          <View style={styles.driverCopy}>
            <Text style={styles.driverLabel}>{driver.label}</Text>
            <Text style={styles.driverConclusion}>{driver.conclusion}</Text>
            <Text style={styles.freshness}>新鲜度：{freshnessLabel[driver.freshness]}</Text>
          </View>
          <View style={styles.barArea}>
            <Text style={styles.score}>{driver.score > 0 ? "+" : ""}{driver.score}</Text>
            <View style={styles.barTrack}>
              <View style={[styles.bar, driver.score < 0 ? styles.negative : styles.positive, { width: normalizedWidth(driver.score) }]} />
            </View>
          </View>
        </Pressable>
      ))}
      <Text style={styles.updatedAt}>更新：{updatedAt}</Text>
      <Pressable
        accessibilityHint="打开市场结论所依据的演示引用"
        accessibilityLabel="查看市场证据"
        accessibilityRole="button"
        onPress={() => onOpenEvidence(citationIds)}
        style={styles.evidenceButton}>
        <Text style={styles.evidenceText}>查看市场证据</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderRadius: radius.lg, gap: spacing.sm, padding: spacing.lg },
  heading: { alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between", gap: spacing.md },
  eyebrow: { color: colors.amber, fontSize: 11, fontWeight: "800" },
  title: { color: colors.ink, fontSize: 18, fontWeight: "800" },
  conclusion: { color: colors.blue, fontSize: 24, fontWeight: "800", marginTop: spacing.xs },
  metrics: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  metric: { color: colors.muted, fontSize: 13, fontVariant: ["tabular-nums"], fontWeight: "700" },
  label: { color: colors.ink, fontSize: 14, fontWeight: "800", marginTop: spacing.sm },
  copy: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  bullet: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  driverHeader: { alignItems: "baseline", flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", gap: spacing.xs },
  scale: { color: colors.muted, fontSize: 11 },
  driver: { flexDirection: "row", gap: spacing.sm, minHeight: 44, paddingVertical: spacing.sm },
  driverCopy: { flex: 1, minWidth: 0 },
  driverLabel: { color: colors.ink, fontSize: 13, fontWeight: "700" },
  driverConclusion: { color: colors.muted, fontSize: 12, marginTop: 2 },
  freshness: { color: colors.muted, fontSize: 11, marginTop: 2 },
  barArea: { alignItems: "flex-end", flex: 0.38, justifyContent: "center" },
  score: { color: colors.ink, fontSize: 12, fontVariant: ["tabular-nums"], fontWeight: "800" },
  barTrack: { alignItems: "flex-start", backgroundColor: colors.line, borderRadius: radius.pill, height: 6, marginTop: 4, overflow: "hidden", width: "100%" },
  bar: { borderRadius: radius.pill, height: "100%" },
  positive: { backgroundColor: colors.green },
  negative: { backgroundColor: colors.red },
  updatedAt: { color: colors.muted, fontSize: 11, marginTop: spacing.sm },
  evidenceButton: { alignItems: "center", backgroundColor: colors.blueSoft, borderRadius: radius.md, justifyContent: "center", minHeight: 44, paddingHorizontal: spacing.md },
  evidenceText: { color: colors.blue, fontSize: 14, fontWeight: "800" },
});
