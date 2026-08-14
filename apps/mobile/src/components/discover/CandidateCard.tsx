import { Pressable, StyleSheet, Text, View } from "react-native";

import type { Candidate } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type CandidateCardProps = {
  candidate: Candidate;
  onOpen(): void;
  onOpenEvidence(): void;
};

const stateLabels = {
  observation: "观察池",
  "action-eligible": "行动研究",
  risk: "风险升高",
} as const;

export function CandidateCard({
  candidate,
  onOpen,
  onOpenEvidence,
}: CandidateCardProps) {
  return (
    <View style={styles.card}>
      <Pressable
        accessibilityLabel={`打开 ${candidate.symbol} 个股分析`}
        accessibilityRole="button"
        onPress={onOpen}
        style={({ pressed }) => [styles.main, pressed && styles.pressed]}>
        <View style={styles.top}>
          <View style={styles.monogram}>
            <Text style={styles.monogramText}>{candidate.symbol.slice(0, 2)}</Text>
          </View>
          <View style={styles.titleCopy}>
            <Text style={styles.symbol}>
              {candidate.symbol} · {candidate.company}
            </Text>
            <View style={styles.badges}>
              <Text style={[styles.badge, candidate.side === "long" ? styles.long : styles.short]}>
                {candidate.side === "long" ? "做多观察" : "做空观察"}
              </Text>
              <Text style={styles.state}>{stateLabels[candidate.state]}</Text>
              {candidate.designation === "asymmetric-upside" ? (
                <Text style={styles.asymmetric}>非对称上行</Text>
              ) : null}
            </View>
          </View>
          <View style={styles.score}>
            <Text style={styles.scoreValue}>{candidate.score}</Text>
            <Text style={styles.scoreLabel}>综合分</Text>
          </View>
        </View>
        <Text style={styles.catalyst}>{candidate.catalyst}</Text>
        <Text numberOfLines={2} style={styles.reason}>{candidate.reason}</Text>
        <View style={styles.signalRow}>
          <Text numberOfLines={1} style={styles.signal}>{candidate.technicalState}</Text>
          <Text numberOfLines={1} style={styles.signal}>{candidate.institutionalProxy}</Text>
        </View>
      </Pressable>
      <Pressable
        accessibilityLabel={`查看 ${candidate.symbol} 候选依据`}
        accessibilityRole="button"
        onPress={onOpenEvidence}
        style={({ pressed }) => [styles.evidence, pressed && styles.pressed]}>
        <Text style={styles.evidenceText}>
          证据 {candidate.evidenceCount} · 反证 {candidate.counterEvidenceCount} · 查看依据 ›
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: "hidden",
  },
  main: {
    gap: spacing.sm,
    minHeight: 128,
    padding: spacing.md,
  },
  top: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  monogram: {
    alignItems: "center",
    backgroundColor: colors.navy,
    borderRadius: radius.sm,
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  monogramText: { color: colors.card, fontSize: 11, fontWeight: "900" },
  titleCopy: { flex: 1, minWidth: 0 },
  symbol: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  badges: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: 4 },
  badge: {
    borderRadius: radius.pill,
    fontSize: 11,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 6,
    paddingVertical: 3,
  },
  long: { backgroundColor: colors.greenSoft, color: colors.green },
  short: { backgroundColor: colors.redSoft, color: colors.red },
  state: {
    backgroundColor: colors.blueSoft,
    borderRadius: radius.pill,
    color: colors.blue,
    fontSize: 11,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 6,
    paddingVertical: 3,
  },
  asymmetric: {
    backgroundColor: colors.purpleSoft,
    borderRadius: radius.pill,
    color: colors.purple,
    fontSize: 11,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 6,
    paddingVertical: 3,
  },
  score: { alignItems: "flex-end", minWidth: 38 },
  scoreValue: { color: colors.green, fontSize: 20, fontWeight: "900" },
  scoreLabel: { color: colors.muted, fontSize: 11, fontWeight: "800" },
  catalyst: { color: colors.ink, fontSize: 12, fontWeight: "900" },
  reason: { color: colors.muted, fontSize: 11, lineHeight: 15 },
  signalRow: { flexDirection: "row", gap: spacing.xs },
  signal: {
    backgroundColor: colors.backgroundRaised,
    borderRadius: radius.sm,
    color: colors.muted,
    flex: 1,
    fontSize: 11,
    overflow: "hidden",
    padding: 6,
  },
  evidence: {
    alignItems: "flex-end",
    borderTopColor: colors.line,
    borderTopWidth: StyleSheet.hairlineWidth,
    justifyContent: "center",
    minHeight: 44,
    paddingHorizontal: spacing.md,
  },
  evidenceText: { color: colors.blue, fontSize: 11, fontWeight: "900" },
  pressed: { opacity: 0.66 },
});
