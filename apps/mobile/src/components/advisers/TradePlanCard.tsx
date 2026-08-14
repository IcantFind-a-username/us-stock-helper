import { StyleSheet, Text, View } from "react-native";

import type { TradePlan } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type TradePlanCardProps = {
  plan: TradePlan;
};

const moneyRange = ([low, high]: [number, number]) =>
  `$${low.toFixed(2)} – $${high.toFixed(2)}`;

export function TradePlanCard({ plan }: TradePlanCardProps) {
  return (
    <View style={styles.card} testID="trade-plan-card">
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>演示预置方案 · 上线后由确定性风险引擎重算</Text>
          <Text style={styles.title}>{plan.entryMethod}</Text>
        </View>
        <View style={styles.riskBadge}>
          <Text style={styles.riskBadgeText}>
            {plan.preference === "aggressive" ? "高风险" : "有约束"}
          </Text>
        </View>
      </View>
      <View style={styles.grid}>
        <Metric label="限价区间" value={moneyRange(plan.entryRange)} />
        <Metric label="数量" value={`${plan.quantity} 股`} />
        <Metric label="风险预算" value={`${plan.riskBudgetPercent.toFixed(2)}%`} />
        <Metric
          label="杠杆"
          value={`${plan.leverage.toFixed(2)}× / 上限 ${plan.maximumLeverage.toFixed(2)}×`}
        />
        <Metric label="失效价" value={`$${plan.invalidationPrice.toFixed(2)}`} />
        <Metric label="目标区间" value={moneyRange(plan.targetRange)} />
        <Metric label="预估盈亏比" value={`${plan.estimatedRewardRisk.toFixed(1)} : 1`} />
        <Metric label="持有窗口" value={plan.holdingWindow} />
      </View>
      <View style={styles.logic}>
        <Text style={styles.logicTitle}>止损逻辑</Text>
        <Text style={styles.logicBody}>{plan.stopLogic}</Text>
      </View>
      <View style={styles.cancel}>
        <Text style={styles.cancelTitle}>取消条件</Text>
        <Text style={styles.cancelBody}>{plan.cancelConditions.join(" · ")}</Text>
      </View>
      {plan.shortRisk ? (
        <View style={styles.shortRisk}>
          <Text style={styles.shortTitle}>做空专属硬检查</Text>
          <View style={styles.shortFacts}>
            <Text style={styles.shortFact}>
              {`可借券：${plan.shortRisk.borrowAvailable ? "是" : "否"}`}
            </Text>
            <Text style={styles.shortFact}>
              {`预计借券费 ${plan.shortRisk.estimatedBorrowFeePercent.toFixed(2)}%`}
            </Text>
            <Text style={styles.shortFact}>
              {`空头仓位 ${plan.shortRisk.shortInterestPercent.toFixed(1)}%`}
            </Text>
          </View>
          {plan.shortRisk.warnings.map((warning) => (
            <Text key={warning} style={styles.shortWarning}>· {warning}</Text>
          ))}
        </View>
      ) : null}
      <Text style={styles.warning}>{plan.riskWarning}</Text>
      <Text style={styles.snapshot}>
        证据快照 {plan.evidenceSnapshotId} · {plan.methodVersion} · 引用 {plan.citationIds.length}
      </Text>
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderColor: colors.line, borderRadius: radius.lg, borderWidth: 1, gap: spacing.md, padding: spacing.md },
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  eyebrow: { color: colors.muted, fontSize: 11, fontWeight: "700" },
  title: { color: colors.ink, fontSize: 16, fontWeight: "900", marginTop: 2 },
  riskBadge: { backgroundColor: colors.redSoft, borderRadius: radius.pill, paddingHorizontal: 9, paddingVertical: 5 },
  riskBadgeText: { color: colors.red, fontSize: 11, fontWeight: "900" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  metric: { backgroundColor: colors.background, borderRadius: radius.sm, minWidth: "46%", padding: spacing.sm },
  metricLabel: { color: colors.muted, fontSize: 11, fontWeight: "700" },
  metricValue: { color: colors.ink, fontSize: 11, fontVariant: ["tabular-nums"], fontWeight: "900", lineHeight: 14, marginTop: 2 },
  logic: { backgroundColor: colors.blueSoft, borderRadius: radius.sm, gap: 3, padding: spacing.sm },
  logicTitle: { color: colors.blue, fontSize: 11, fontWeight: "900" },
  logicBody: { color: "#3B5F91", fontSize: 11, lineHeight: 14 },
  cancel: { gap: 3 },
  cancelTitle: { color: colors.ink, fontSize: 11, fontWeight: "900" },
  cancelBody: { color: colors.muted, fontSize: 11, lineHeight: 14 },
  shortRisk: { backgroundColor: colors.redSoft, borderRadius: radius.md, gap: 4, padding: spacing.sm },
  shortTitle: { color: colors.red, fontSize: 11, fontWeight: "900" },
  shortFacts: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  shortFact: { color: colors.ink, fontSize: 11, fontVariant: ["tabular-nums"], fontWeight: "800" },
  shortWarning: { color: colors.red, fontSize: 11, fontWeight: "700", lineHeight: 13 },
  warning: { color: colors.red, fontSize: 11, fontWeight: "700", lineHeight: 14 },
  snapshot: { color: colors.muted, fontSize: 11, fontWeight: "600" },
});
