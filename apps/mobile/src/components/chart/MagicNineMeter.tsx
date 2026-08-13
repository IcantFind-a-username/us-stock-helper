import { StyleSheet, Text, View } from "react-native";

import type { ChartMagicNineSnapshot } from "@/domain/models";
import { colors, spacing } from "@/theme/tokens";

const setupLength = 9;

const directionLabel = (direction: string | null) => {
  if (direction === "bullish") return "看涨";
  if (direction === "bearish") return "看跌";
  return "无方向";
};

/**
 * Nine steps, filled to the count the server reported.
 *
 * A single circle carrying the number told the reader neither how far the
 * setup had run nor how far it had left, which is the only thing a nine-count
 * is for. The steps carry both, and an unavailable count fills none of them
 * rather than drawing a zero that looks like a measurement.
 */
export function MagicNineMeter({
  magicNine,
}: {
  magicNine: ChartMagicNineSnapshot;
}) {
  const available = magicNine.qualityStatus !== "unavailable";
  const filled = available
    ? Math.max(0, Math.min(setupLength, Math.round(magicNine.count)))
    : 0;
  const tone = magicNine.direction === "bearish" ? colors.red : colors.green;

  return (
    <View style={styles.row} testID="magic-nine-meter">
      <Text style={styles.label}>
        {available
          ? `九转 ${directionLabel(magicNine.direction)} ${magicNine.count}/${setupLength}${
              magicNine.completed ? " · 序列完成" : ""
            }`
          : "九转 暂不可用"}
      </Text>
      <View style={styles.steps}>
        {Array.from({ length: setupLength }, (_, index) => (
          <View
            key={index}
            style={[
              styles.step,
              index < filled ? { backgroundColor: tone } : styles.emptyStep,
            ]}
            testID={
              index < filled ? "magic-nine-step-filled" : "magic-nine-step-empty"
            }
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
  },
  label: {
    color: colors.ink,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
  },
  steps: { flexDirection: "row", gap: 2 },
  step: { borderRadius: 1, height: 8, width: 4 },
  emptyStep: { backgroundColor: colors.line },
});
