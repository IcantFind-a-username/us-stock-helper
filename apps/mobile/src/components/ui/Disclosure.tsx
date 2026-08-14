import { useState, type ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "@/theme/tokens";

/**
 * Caveats the reader can open, rather than a paragraph above the chart.
 *
 * The disclosures still have to be one tap away — they are the terms the
 * numbers are true under — but printing them all inline is what turned the
 * page into an even block of text with no subject.
 */
export function Disclosure({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <View style={styles.card}>
      <Pressable
        accessibilityLabel={`${title}，${open ? "已展开" : "已折叠"}`}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen((current) => !current)}
        style={({ pressed }) => [styles.header, pressed && styles.pressed]}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.action}>{open ? "收起" : "展开"}</Text>
      </Pressable>
      {open ? <View style={styles.body}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: spacing.md,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 44,
  },
  title: { color: colors.ink, fontSize: 11, fontWeight: "800" },
  action: { color: colors.blue, fontSize: 11, fontWeight: "800" },
  pressed: { opacity: 0.68 },
  body: { gap: spacing.xs, paddingBottom: spacing.md },
});
