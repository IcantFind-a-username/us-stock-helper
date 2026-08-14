import { Pressable, StyleSheet, Text, View } from "react-native";

import { DashboardSectionHeader } from "@/components/dashboard/DashboardSectionHeader";
import type { Candidate } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type CandidateListProps = {
  candidates: Candidate[];
  onPress(symbol: string): void;
  onOpenEvidence(candidate: Candidate): void;
  onOpenDiscover(): void;
};

const stateLabels = {
  observation: "观察池",
  "action-eligible": "达到行动研究门槛",
  risk: "风险升高",
} as const;

export function CandidateList({
  candidates,
  onPress,
  onOpenEvidence,
  onOpenDiscover,
}: CandidateListProps) {
  return (
    <View accessibilityLabel="潜力候选，演示" style={styles.section} testID="candidate-list">
      <DashboardSectionHeader
        actionLabel="发现器 ›"
        onAction={onOpenDiscover}
        title="潜力候选"
      />
      {candidates.slice(0, 2).map((candidate) => (
        <View key={candidate.symbol} style={styles.row}>
          <Pressable
            accessibilityLabel={`查看 ${candidate.symbol} 候选详情`}
            accessibilityRole="button"
            onPress={() => onPress(candidate.symbol)}
            style={styles.mainAction}>
            <View style={styles.logo}>
              <Text style={styles.logoText}>{candidate.symbol.slice(0, 2)}</Text>
            </View>
            <View style={styles.copy}>
              <Text style={styles.symbol}>
                {candidate.symbol} · {stateLabels[candidate.state]}
              </Text>
              <Text numberOfLines={1} style={styles.catalyst}>{candidate.catalyst}</Text>
            </View>
          </Pressable>
          <Pressable
            accessibilityLabel={`查看 ${candidate.symbol} 候选依据`}
            accessibilityRole="button"
            onPress={() => onOpenEvidence(candidate)}
            style={styles.rankAction}>
            <Text style={styles.rank}>{candidate.score}</Text>
            <Text style={styles.evidenceCount}>证据 {candidate.evidenceCount}</Text>
          </Pressable>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: 7 },
  row: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
  },
  mainAction: {
    alignItems: "center",
    flex: 1,
    flexDirection: "row",
    gap: spacing.sm,
    minHeight: 44,
    minWidth: 0,
  },
  logo: {
    alignItems: "center",
    backgroundColor: colors.blueSoft,
    borderRadius: radius.sm,
    height: 34,
    justifyContent: "center",
    width: 34,
  },
  logoText: { color: colors.blue, fontSize: 12, fontWeight: "800" },
  copy: { flex: 1, minWidth: 0 },
  symbol: { color: colors.ink, fontSize: 14, fontWeight: "800" },
  catalyst: { color: colors.muted, fontSize: 11, marginTop: spacing.xxs },
  rankAction: {
    alignItems: "flex-end",
    justifyContent: "center",
    minHeight: 44,
    minWidth: 58,
    paddingLeft: spacing.sm,
  },
  rank: { color: colors.ink, fontSize: 18, fontVariant: ["tabular-nums"], fontWeight: "800" },
  evidenceCount: { color: colors.muted, fontSize: 11, marginTop: spacing.xxs },
});
