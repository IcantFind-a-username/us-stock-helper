import { useState } from "react";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { AlertThreadCard } from "@/components/alerts/AlertThreadCard";
import { AnalysisNotConnected } from "@/components/ui/AnalysisNotConnected";
import {
  DashboardDetailSheet,
  type DetailSection,
} from "@/components/dashboard/DashboardDetailSheet";
import { Screen } from "@/components/ui/Screen";
import { useMarketDataMode } from "@/state/MarketDataProvider";
import type { AlertThread, Citation } from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
import { colors, radius, spacing } from "@/theme/tokens";

type SeverityFilter = "all" | AlertThread["severity"];

type DetailState = {
  title: string;
  sections: DetailSection[];
  citations: Citation[];
} | null;

export function AlertsScreen() {
  const router = useRouter();
  const { demoMode } = useMarketDataMode();
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [detail, setDetail] = useState<DetailState>(null);
  const allAlerts = fixtureRepository.getAlerts();
  const alerts = allAlerts.filter(
    (alert) => severity === "all" || alert.severity === severity,
  );
  const highPriority = allAlerts.filter(
    ({ severity: level }) => level === "action" || level === "risk",
  ).length;

  const openEvidence = (alert: AlertThread) =>
    setDetail({
      title: `${alert.symbol} 提醒证据`,
      sections: [
        { label: "当前状态", body: alert.currentState },
        { label: "触发原因", body: alert.summary },
        { label: "来源覆盖", body: alert.sourceCoverage },
        {
          label: "评分贡献",
          body: `基础 ${alert.baseScoreContribution > 0 ? "+" : ""}${alert.baseScoreContribution} · 顾问软因子 ${
            alert.adviserAdjustment === null
              ? "未调用"
              : `${alert.adviserAdjustment > 0 ? "+" : ""}${alert.adviserAdjustment}`
          }`,
        },
        { label: "失效条件", body: alert.invalidation },
        {
          label: "证据状态",
          body: `证据 ${alert.evidenceCount} · 反证 ${alert.counterEvidenceCount} · ${alert.sourceFreshness}`,
        },
      ],
      citations: alert.citations,
    });

  if (!demoMode) {
    return (
      <Screen hideGlobalHeader style={styles.screen}>
        <AnalysisNotConnected surface="提醒" />
      </Screen>
    );
  }

  return (
    <Screen hideGlobalHeader style={styles.screen}>
      <View style={styles.header}>
        <View>
          <Text style={styles.demoLabel}>演示数据 · 非实时行情</Text>
          <Text style={styles.eyebrow}>证据门控 · 事件线程</Text>
          <Text style={styles.title}>提醒中心</Text>
        </View>
        <View style={styles.summary}>
          <Text style={styles.summaryValue}>{highPriority}</Text>
          <Text style={styles.summaryLabel}>高优先级</Text>
        </View>
      </View>

      <View style={styles.hero}>
        <View>
          <Text style={styles.heroEyebrow}>当前处理框架</Text>
          <Text style={styles.heroTitle}>提醒不等于下单指令</Text>
        </View>
        <Text style={styles.heroBody}>
          只有确定性基础算法和足够证据能提升等级；顾问意见只能有限调整，并始终显示反证与失效条件。
        </Text>
      </View>

      <View style={styles.filters}>
        {([
          ["all", "全部提醒"],
          ["action", "只看行动研究"],
          ["risk", "只看风险提醒"],
          ["observation", "只看观察提醒"],
          ["info", "只看信息提醒"],
        ] as const).map(([value, label]) => {
          const selected = severity === value;
          return (
            <Pressable
              accessibilityLabel={label}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              key={value}
              onPress={() => setSeverity(value)}
              style={({ pressed }) => [
                styles.filter,
                selected && styles.filterSelected,
                pressed && styles.pressed,
              ]}>
              <Text style={[styles.filterText, selected && styles.filterTextSelected]}>
                {label.replace("只看", "")}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.list}>
        {alerts.map((alert) => (
          <AlertThreadCard
            alert={alert}
            key={alert.id}
            onOpen={() =>
              router.push({
                pathname: "/stocks/[symbol]",
                params: { symbol: alert.symbol },
              })
            }
            onOpenEvidence={() => openEvidence(alert)}
          />
        ))}
      </View>

      <DashboardDetailSheet
        citations={detail?.citations ?? []}
        onClose={() => setDetail(null)}
        sections={detail?.sections ?? []}
        title={detail?.title ?? ""}
        visible={detail !== null}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { gap: spacing.md, paddingTop: spacing.xs },
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  demoLabel: { color: colors.amber, fontSize: 8, fontWeight: "900" },
  eyebrow: { color: colors.muted, fontSize: 9, fontWeight: "800" },
  title: { color: colors.ink, fontSize: 23, fontWeight: "900", marginTop: spacing.xxs },
  summary: { alignItems: "flex-end" },
  summaryValue: { color: colors.red, fontSize: 20, fontWeight: "900" },
  summaryLabel: { color: colors.muted, fontSize: 8, fontWeight: "800" },
  hero: { backgroundColor: colors.navy, borderRadius: radius.lg, gap: spacing.xs, padding: spacing.md },
  heroEyebrow: { color: colors.blueBright, fontSize: 9, fontWeight: "900" },
  heroTitle: { color: colors.card, fontSize: 17, fontWeight: "900", marginTop: 3 },
  heroBody: { color: colors.navyMuted, fontSize: 10, lineHeight: 15 },
  filters: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  filter: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: "center",
    minHeight: 44,
    paddingHorizontal: spacing.md,
  },
  filterSelected: { backgroundColor: colors.blue, borderColor: colors.blue },
  filterText: { color: colors.muted, fontSize: 9, fontWeight: "900" },
  filterTextSelected: { color: colors.card },
  list: { gap: spacing.sm },
  pressed: { opacity: 0.66 },
});
