import { SymbolView } from "expo-symbols";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { DataHealth } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

const healthLabels: Record<DataHealth, string> = {
  fresh: "数据新鲜",
  stale: "数据延迟",
  conflict: "数据冲突",
  insufficient: "数据不足",
};

type DashboardHeaderProps = {
  marketSession: string;
  health: DataHealth;
  updatedAt: string;
  onSearch(): void;
  onAlerts(): void;
};

export function DashboardHeader({
  marketSession,
  health,
  updatedAt,
  onSearch,
  onAlerts,
}: DashboardHeaderProps) {
  return (
    <View testID="dashboard-header" style={styles.header}>
      <View style={styles.copy}>
        <Text style={styles.session}>
          {marketSession} · {healthLabels[health]} · 更新 {updatedAt.slice(11, 16)}
        </Text>
        <Text style={styles.greeting}>早上好，Franz</Text>
        <Text style={styles.demoStatus}>演示数据 · 非实时行情</Text>
      </View>
      <View style={styles.actions}>
        <Pressable accessibilityLabel="搜索股票" onPress={onSearch} style={styles.iconButton}>
          <View style={styles.iconCircle}>
            <SymbolView name="magnifyingglass" size={18} tintColor={colors.ink} />
          </View>
        </Pressable>
        <Pressable accessibilityLabel="查看提醒" onPress={onAlerts} style={styles.iconButton}>
          <View style={styles.iconCircle}>
            <SymbolView name="bell" size={18} tintColor={colors.ink} />
          </View>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  copy: { flex: 1, minWidth: 0 },
  session: { color: colors.muted, fontSize: 10, fontWeight: "700" },
  greeting: { color: colors.ink, fontSize: 18, fontWeight: "800", marginTop: spacing.xxs },
  demoStatus: { color: colors.muted, fontSize: 10, marginTop: spacing.xxs },
  actions: { flexDirection: "row", gap: spacing.xs, marginLeft: spacing.sm },
  iconButton: { alignItems: "center", justifyContent: "center", minHeight: 44, minWidth: 44 },
  iconCircle: { alignItems: "center", backgroundColor: colors.card, borderRadius: radius.round, height: 32, justifyContent: "center", width: 32 },
});
