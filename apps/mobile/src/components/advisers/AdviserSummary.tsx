import { StyleSheet, Text, View } from "react-native";

import type { AdviserOpinion } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type AdviserSummaryProps = {
  opinion: AdviserOpinion;
  compact?: boolean;
};

const directionLabel = {
  bullish: "偏多",
  neutral: "中性",
  bearish: "反对",
} as const;

export function AdviserSummary({ opinion, compact = false }: AdviserSummaryProps) {
  const initials = opinion.displayName
    .replace(" 风格", "")
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  const directionColor =
    opinion.direction === "bullish"
      ? colors.green
      : opinion.direction === "bearish"
        ? colors.red
        : colors.muted;

  return (
    <View style={[styles.card, compact && styles.compact]}>
      <View style={styles.top}>
        <View style={styles.avatar}>
          <Text style={styles.initials}>{initials}</Text>
        </View>
        <View style={styles.nameWrap}>
          <Text numberOfLines={1} style={styles.name}>{opinion.displayName}</Text>
          <Text style={styles.focus}>{opinion.focus}</Text>
        </View>
        <Text style={[styles.direction, { color: directionColor }]}>
          {opinion.abstained ? "弃权" : directionLabel[opinion.direction]}
        </Text>
      </View>
      {compact ? null : (
        <>
          <Text style={styles.thesis}>{opinion.thesis}</Text>
          <Text style={styles.counter}>反证：{opinion.counterargument}</Text>
          <Text style={styles.confidence}>
            置信度 {Math.round(opinion.confidence * 100)}% ·{" "}
            {opinion.active ? "本轮激活" : "按需调用"}
          </Text>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderColor: colors.line, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, gap: spacing.sm, padding: spacing.sm },
  compact: { minWidth: "48%" },
  top: { alignItems: "center", flexDirection: "row", gap: spacing.sm },
  avatar: { alignItems: "center", backgroundColor: colors.navy, borderRadius: radius.round, height: 32, justifyContent: "center", width: 32 },
  initials: { color: colors.card, fontSize: 9, fontWeight: "900" },
  nameWrap: { flex: 1, minWidth: 0 },
  name: { color: colors.ink, fontSize: 10, fontWeight: "900" },
  focus: { color: colors.muted, fontSize: 8, fontWeight: "600", marginTop: 1 },
  direction: { fontSize: 9, fontWeight: "900" },
  thesis: { color: colors.ink, fontSize: 10, lineHeight: 15 },
  counter: { color: colors.muted, fontSize: 9, lineHeight: 14 },
  confidence: { color: colors.blue, fontSize: 9, fontWeight: "800" },
});
