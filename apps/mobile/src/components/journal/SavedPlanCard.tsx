import { StyleSheet, Text, View } from "react-native";

import type { TradePlan } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

export function SavedPlanCard({ plan }: { plan: TradePlan }) {
  return (
    <View style={styles.card}>
      <View style={styles.top}>
        <Text style={styles.symbol}>
          {plan.symbol} · {plan.side === "long" ? "做多" : "做空"} ·{" "}
          {plan.horizon === "short" ? "短线" : plan.horizon === "swing" ? "波段" : "中长期"}
        </Text>
        <Text style={styles.preference}>{preferenceLabel[plan.preference]}</Text>
      </View>
      <Text style={styles.entry}>{plan.entryMethod} · ${plan.entryRange.join("–")}</Text>
      <View style={styles.metrics}>
        <Metric label="数量" value={`${plan.quantity} 股`} />
        <Metric label="单笔风险" value={`${plan.riskBudgetPercent.toFixed(2)}%`} />
        <Metric label="最大杠杆" value={`${plan.maximumLeverage.toFixed(1)}×`} />
      </View>
      <Text style={styles.warning}>只保存分析方案，不会向券商提交订单。</Text>
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

const preferenceLabel = {
  conservative: "保守",
  balanced: "均衡",
  aggressive: "高回报倾向",
} as const;

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.md,
  },
  top: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  symbol: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  preference: {
    backgroundColor: colors.purpleSoft,
    borderRadius: radius.pill,
    color: colors.purple,
    fontSize: 8,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  entry: { color: colors.muted, fontSize: 10, fontWeight: "800" },
  metrics: { flexDirection: "row", justifyContent: "space-between" },
  metricLabel: { color: colors.muted, fontSize: 8 },
  metricValue: { color: colors.ink, fontSize: 10, fontWeight: "900", marginTop: 2 },
  warning: { color: colors.amber, fontSize: 8, fontWeight: "800" },
});
