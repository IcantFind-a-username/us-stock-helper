import { Pressable, StyleSheet, Text, View } from "react-native";

import type { MarketDriver } from "@/domain/models";
import { ScoreRing } from "@/components/ui/ScoreRing";
import { colors, radius, shadow, spacing } from "@/theme/tokens";

type MarketRegimeHeroProps = {
  score: number;
  conclusion: string;
  rationale: string;
  advice: string;
  drivers: MarketDriver[];
  updatedAt: string;
  onOpenDetail(): void;
};

export function MarketRegimeHero({
  score,
  conclusion,
  rationale,
  advice,
  drivers,
  updatedAt,
  onOpenDetail,
}: MarketRegimeHeroProps) {
  const compactDrivers = drivers.slice(0, 4);

  return (
    <View testID="market-regime-hero" style={styles.hero}>
      <View style={styles.topRow}>
        <View style={styles.copy}>
          <Text style={styles.eyebrow}>市场情绪结论 · 最近更新 {updatedAt.slice(11, 16)}</Text>
          <Text style={styles.conclusion}>{conclusion}</Text>
          <Text numberOfLines={2} style={styles.rationale}>{rationale}</Text>
        </View>
        <ScoreRing score={score} />
      </View>
      <View style={styles.playbook}>
        <Text style={styles.playbookLabel}>今日建议</Text>
        <Text numberOfLines={3} style={styles.advice}>{advice}</Text>
      </View>
      <View style={styles.driverRow}>
        {compactDrivers.map((driver) => (
          <View key={driver.id} style={styles.driverChip} testID="market-driver-chip">
            <Text style={styles.driverText}>
              {driver.label} {driver.score > 0 ? "+" : ""}{driver.score}
            </Text>
          </View>
        ))}
      </View>
      <Pressable
        accessibilityLabel="查看完整依据"
        accessibilityRole="button"
        onPress={onOpenDetail}
        style={styles.detailAction}>
        <Text style={styles.detailActionText}>查看依据 ›</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: {
    backgroundColor: colors.navy,
    borderRadius: radius.lg,
    gap: spacing.sm,
    padding: 13,
    ...shadow.hero,
  },
  topRow: { alignItems: "flex-start", flexDirection: "row", gap: spacing.sm },
  copy: { flex: 1, minWidth: 0 },
  eyebrow: { color: colors.navyEyebrow, fontSize: 9, fontWeight: "800", letterSpacing: 0.8 },
  conclusion: { color: "#EFF6FF", fontSize: 20, fontWeight: "800", marginTop: 4 },
  rationale: { color: colors.navyMuted, fontSize: 11, lineHeight: 16, marginTop: 3 },
  playbook: {
    backgroundColor: "rgba(53, 113, 194, 0.18)",
    borderColor: "rgba(79, 155, 255, 0.28)",
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: spacing.xs,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  playbookLabel: { color: colors.blueBright, fontSize: 10, fontWeight: "800" },
  advice: { color: "#D7E4F5", flex: 1, fontSize: 10, lineHeight: 15 },
  driverRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  driverChip: {
    backgroundColor: "rgba(255,255,255,0.07)",
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 4,
  },
  driverText: { color: "#D7E4F5", fontSize: 8, fontWeight: "700" },
  detailAction: { alignSelf: "flex-start", justifyContent: "center", minHeight: 44, paddingRight: spacing.md },
  detailActionText: { color: colors.blueBright, fontSize: 11, fontWeight: "800" },
});
