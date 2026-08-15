import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { PlainReadingNumbers } from "@/i18n/plainLanguage";
import { colors, radius, spacing } from "@/theme/tokens";

/**
 * The three-layer plain-language contract, rendered.
 *
 * Layer 1 (一句话白话结论) is always visible -- it is the whole point, the
 * one sentence a novice reads without doing anything. Layers 2 (展开解释,
 * the mechanism + a lived-world analogy) and 3 (数字层: value, sample size,
 * 失效条件) are one tap away, same pattern as `Disclosure`: caveats a reader
 * has to be able to reach, not a paragraph forced onto every screen that
 * uses this card.
 *
 * The copy itself never originates here -- every caller builds `headline`/
 * `explanation`/`numbers` from `@/i18n/plainLanguage`'s `reading()` and its
 * per-indicator helpers, which already enforce 白话不喊单 at construction.
 * This component only lays the three layers out; it has no vocabulary of
 * its own.
 */
export function PlainReadingCard({
  headline,
  explanation,
  numbers,
  testID,
}: {
  headline: string;
  explanation: string;
  numbers: PlainReadingNumbers;
  testID?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <View style={styles.card} testID={testID ?? "plain-reading-card"}>
      <Pressable
        accessibilityLabel={`白话解读，${open ? "已展开" : "已折叠"}`}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen((current) => !current)}
        style={({ pressed }) => [styles.headlineRow, pressed && styles.pressed]}>
        <Text style={styles.headline} testID="plain-reading-headline">
          {headline}
        </Text>
        <Text style={styles.toggle}>{open ? "收起" : "展开"}</Text>
      </Pressable>
      {open ? (
        <View style={styles.body}>
          <Text style={styles.explanation} testID="plain-reading-explanation">
            {explanation}
          </Text>
          <View style={styles.numbers} testID="plain-reading-numbers">
            <Text style={styles.numberLine}>数值：{numbers.value}</Text>
            <Text style={styles.numberLine}>样本：{numbers.sampleSize}</Text>
            <Text style={styles.numberLine}>失效条件：{numbers.invalidation}</Text>
            {numbers.note ? (
              <Text style={styles.numberLine} testID="plain-reading-note">
                {numbers.note}
              </Text>
            ) : null}
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.backgroundRaised,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: spacing.md,
  },
  headlineRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "space-between",
    minHeight: 44,
  },
  pressed: { opacity: 0.68 },
  headline: { color: colors.ink, flex: 1, fontSize: 12, fontWeight: "700" },
  toggle: { color: colors.blue, fontSize: 11, fontWeight: "800" },
  body: { gap: spacing.xs, paddingBottom: spacing.md },
  explanation: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  numbers: { gap: spacing.xxs },
  numberLine: { color: colors.muted, fontSize: 11, lineHeight: 16 },
});
