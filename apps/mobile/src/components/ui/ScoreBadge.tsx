import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "@/theme/tokens";

type ScoreBadgeProps = {
  score: number;
  label?: string;
};

function scoreStyle(score: number) {
  if (score >= 70) return { backgroundColor: colors.greenSoft, color: colors.green };
  if (score <= 40) return { backgroundColor: colors.redSoft, color: colors.red };
  return { backgroundColor: colors.amberSoft, color: colors.amber };
}

export function ScoreBadge({ score, label = "评分" }: ScoreBadgeProps) {
  const tone = scoreStyle(score);

  return (
    <View accessibilityLabel={`${label} ${score}`} style={[styles.badge, { backgroundColor: tone.backgroundColor }]}>
      <Text style={[styles.text, { color: tone.color }]}>{`${label} ${score}`}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { alignSelf: "flex-start", borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: spacing.xs },
  text: { fontSize: 12, fontVariant: ["tabular-nums"], fontWeight: "700" },
});
