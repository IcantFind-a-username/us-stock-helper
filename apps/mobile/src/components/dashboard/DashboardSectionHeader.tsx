import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors } from "@/theme/tokens";

type DashboardSectionHeaderProps = {
  title: string;
  actionLabel: string;
  onAction(): void;
};

export function DashboardSectionHeader({
  title,
  actionLabel,
  onAction,
}: DashboardSectionHeaderProps) {
  return (
    <View style={styles.row}>
      <Text style={styles.title}>{title}</Text>
      <Pressable
        accessibilityLabel={actionLabel}
        accessibilityRole="button"
        onPress={onAction}
        style={styles.action}>
        <Text style={styles.actionText}>{actionLabel}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  title: { color: colors.ink, fontSize: 12, fontWeight: "800" },
  action: { alignItems: "flex-end", justifyContent: "center", minHeight: 44, minWidth: 44 },
  actionText: { color: colors.blue, fontSize: 10, fontWeight: "700" },
});
