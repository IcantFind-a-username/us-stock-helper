import { Pressable, StyleSheet, Text, View } from "react-native";

import type { Candidate } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type CandidateListProps = {
  title: string;
  candidates: Candidate[];
  onPress(symbol: string): void;
  onOpenEvidence(title: string, citationIds: string[]): void;
};

const stateLabels = {
  observation: "观察池",
  "action-eligible": "达到行动研究门槛",
  risk: "风险升高",
} as const;

const freshnessLabel = { fresh: "新鲜", stale: "可能延迟", conflict: "存在冲突" } as const;

export function CandidateList({ title, candidates, onPress, onOpenEvidence }: CandidateListProps) {
  return (
    <View accessibilityLabel="潜力候选，演示" style={styles.section}>
      <Text style={styles.marker}>演示</Text>
      <Text style={styles.title}>{title}</Text>
      {candidates.map((candidate) => <CandidateCard candidate={candidate} key={candidate.symbol} onOpenEvidence={onOpenEvidence} onPress={onPress} />)}
    </View>
  );
}

function CandidateCard({ candidate, onPress, onOpenEvidence }: { candidate: Candidate; onPress(symbol: string): void; onOpenEvidence(title: string, citationIds: string[]): void }) {
  const designation = candidate.designation === "asymmetric-upside" ? "非对称上行" : "常规";
  const side = candidate.side === "long" ? "做多" : "做空";

  return (
    <View accessibilityLabel={`${candidate.symbol} 候选，演示`} style={styles.card}>
      <Text style={styles.cardMarker}>演示</Text>
      <View style={styles.cardHeading}>
        <View style={styles.cardCopy}>
          <Text style={styles.symbol}>{candidate.symbol} · {candidate.company}</Text>
          <Text style={styles.designation}>{side} · {designation}</Text>
        </View>
        <Text style={styles.score}>评分 {candidate.score}</Text>
      </View>
      <Text style={styles.state}>{stateLabels[candidate.state]}</Text>
      <Text style={styles.meta}>新鲜度：{candidate.evidenceFreshness === "fresh" ? "新鲜" : candidate.evidenceFreshness === "stale" ? "可能延迟" : "存在冲突"} · 证据 {candidate.evidenceCount} · 反证 {candidate.counterEvidenceCount}</Text>
      <Text style={styles.label}>原因</Text>
      <Text style={styles.detail}>{candidate.reason}</Text>
      <Text style={styles.label}>最强反例</Text>
      <Text style={styles.detail}>{candidate.counterCase}</Text>
      <Text style={styles.label}>失效条件</Text>
      <Text style={styles.detail}>{candidate.invalidation}</Text>
      <View style={styles.actions}>
        <Pressable accessibilityHint="打开该候选的演示引用" accessibilityLabel={`查看 ${candidate.symbol} 候选证据：${side}，${stateLabels[candidate.state]}，评分 ${candidate.score}，新鲜度 ${freshnessLabel[candidate.evidenceFreshness]}`} accessibilityRole="button" onPress={() => onOpenEvidence(`${candidate.symbol} 候选证据`, candidate.citationIds)} style={styles.evidenceButton}>
          <Text style={styles.evidenceText}>引用</Text>
        </Pressable>
        <Pressable accessibilityHint="前往股票详情" accessibilityLabel={`查看 ${candidate.symbol} 候选详情：${side}，${designation}，${stateLabels[candidate.state]}，评分 ${candidate.score}`} accessibilityRole="button" onPress={() => onPress(candidate.symbol)} style={styles.detailButton}>
          <Text style={styles.detailText}>股票详情</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.sm },
  marker: { color: colors.amber, fontSize: 11, fontWeight: "800" },
  title: { color: colors.ink, fontSize: 17, fontWeight: "800" },
  card: { backgroundColor: colors.card, borderRadius: radius.lg, gap: spacing.xs, padding: spacing.lg },
  cardMarker: { color: colors.amber, fontSize: 11, fontWeight: "800" },
  cardHeading: { alignItems: "flex-start", flexDirection: "row", gap: spacing.sm, justifyContent: "space-between" },
  cardCopy: { flex: 1, minWidth: 0 },
  symbol: { color: colors.ink, fontSize: 16, fontWeight: "800" },
  designation: { color: colors.blue, fontSize: 12, fontWeight: "800", marginTop: 2 },
  score: { color: colors.ink, fontSize: 12, fontVariant: ["tabular-nums"], fontWeight: "800" },
  state: { alignSelf: "flex-start", backgroundColor: colors.blueSoft, borderRadius: radius.pill, color: colors.blue, fontSize: 12, fontWeight: "800", overflow: "hidden", paddingHorizontal: spacing.sm, paddingVertical: 3 },
  meta: { color: colors.muted, fontSize: 11, lineHeight: 17 },
  label: { color: colors.ink, fontSize: 13, fontWeight: "800", marginTop: spacing.xs },
  detail: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  evidenceButton: { alignItems: "center", backgroundColor: colors.blueSoft, borderRadius: radius.md, flex: 1, justifyContent: "center", minHeight: 44, paddingHorizontal: spacing.sm },
  detailButton: { alignItems: "center", backgroundColor: colors.navy, borderRadius: radius.md, flex: 2, justifyContent: "center", minHeight: 44, paddingHorizontal: spacing.sm },
  evidenceText: { color: colors.blue, fontSize: 13, fontWeight: "800" },
  detailText: { color: colors.card, fontSize: 13, fontWeight: "800" },
});
