import { SymbolView } from "expo-symbols";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { MARKET_SESSION_LABELS } from "@/components/dashboard/MarketBriefCard";
import type { DataHealth, MarketBrief } from "@/domain/models";
import { shanghaiGreeting } from "@/domain/greeting";
import { colors, radius, spacing } from "@/theme/tokens";

const healthLabels: Record<DataHealth, string> = {
  fresh: "数据新鲜",
  stale: "数据延迟",
  conflict: "数据冲突",
  insufficient: "数据不足",
};

const actionSymbols = {
  alerts: { android: "notifications", ios: "bell", web: "notifications" },
  search: { android: "search", ios: "magnifyingglass", web: "search" },
} as const;

type DashboardHeaderProps = {
  marketSession: string;
  health: DataHealth;
  demoMode: boolean;
  updatedAt: string;
  now: Date;
  onSearch(): void;
  onAlerts(): void;
  /**
   * The decoded market brief, real-mode only. `null` while it has not
   * loaded (or could not) -- the session/data-health line simply does not
   * render rather than guessing at a value the server never sent.
   */
  realBrief?: MarketBrief | null;
};

export function DashboardHeader({
  marketSession,
  health,
  updatedAt,
  demoMode,
  now,
  onSearch,
  onAlerts,
  realBrief = null,
}: DashboardHeaderProps) {
  const realSessionLine =
    realBrief && realBrief.status === "available" && realBrief.dataHealth
      ? `${MARKET_SESSION_LABELS[realBrief.marketSession]} · ${
          healthLabels[realBrief.dataHealth]
        } · 更新 ${realBrief.decisionCutoff.slice(11, 16)}`
      : null;

  return (
    <View testID="dashboard-header" style={styles.header}>
      <View style={styles.copy}>
        {/* The demo session line comes from the fixture, so outside demo mode
            it would announce an invented data-health verdict and timestamp
            over real quotes. Real mode's own line is driven by the brief
            instead, and only appears once one has actually loaded. */}
        {demoMode ? (
          <Text style={styles.session}>
            {marketSession} · {healthLabels[health]} · 更新{" "}
            {updatedAt.slice(11, 16)}
          </Text>
        ) : realSessionLine ? (
          <Text style={styles.session} testID="dashboard-header-real-session">
            {realSessionLine}
          </Text>
        ) : null}
        <Text style={styles.greeting}>{shanghaiGreeting(now, "Franz")}</Text>
        {demoMode ? (
          <Text style={styles.demoStatus}>演示数据 · 非实时行情</Text>
        ) : null}
      </View>
      <View style={styles.actions}>
        <Pressable
          accessibilityLabel="搜索股票"
          accessibilityRole="button"
          onPress={onSearch}
          style={styles.iconButton}>
          <View style={styles.iconCircle}>
            <SymbolView name={actionSymbols.search} size={18} tintColor={colors.ink} />
          </View>
        </Pressable>
        <Pressable
          accessibilityLabel="查看提醒"
          accessibilityRole="button"
          onPress={onAlerts}
          style={styles.iconButton}>
          <View style={styles.iconCircle}>
            <SymbolView name={actionSymbols.alerts} size={18} tintColor={colors.ink} />
          </View>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  copy: { flex: 1, minWidth: 0 },
  session: { color: colors.muted, fontSize: 11, fontWeight: "700" },
  greeting: { color: colors.ink, fontSize: 22, fontWeight: "800", marginTop: spacing.xxs },
  demoStatus: { color: colors.muted, fontSize: 11, marginTop: spacing.xxs },
  actions: { flexDirection: "row", gap: spacing.xs, marginLeft: spacing.sm },
  iconButton: { alignItems: "center", justifyContent: "center", minHeight: 44, minWidth: 44 },
  iconCircle: { alignItems: "center", backgroundColor: colors.card, borderRadius: radius.round, height: 32, justifyContent: "center", width: 32 },
});
