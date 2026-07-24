import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "@/theme/tokens";

export function DemoDataBadge() {
  return (
    <View accessibilityLabel="演示数据，非实时建议" style={styles.badge}>
      <Text style={styles.text}>演示数据 · 非实时建议</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: "flex-start",
    backgroundColor: colors.amberSoft,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  text: {
    color: colors.amber,
    fontSize: 12,
    fontWeight: "700",
  },
});
