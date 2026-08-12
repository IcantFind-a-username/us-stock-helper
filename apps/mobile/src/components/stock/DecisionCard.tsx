import { StyleSheet, Text, View } from "react-native";

import type { Decision } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

/**
 * Renders one composed decision.
 *
 * The service states what it could not see; showing the score without its
 * coverage would hand the reader a number that looks like a full picture.
 */
export function DecisionCard({ decision }: { decision: Decision }) {
  if (decision.status === "unavailable" || !decision.score) {
    return (
      <View style={styles.card} testID="decision-card">
        <Text style={styles.eyebrow}>综合结论</Text>
        <Text style={styles.unavailable}>暂不可用</Text>
        {decision.notes.map((note) => (
          <Text key={note} style={styles.note}>
            · {note}
          </Text>
        ))}
      </View>
    );
  }

  const { score } = decision;
  return (
    <View style={styles.card} testID="decision-card">
      <View style={styles.header}>
        <Text style={styles.eyebrow}>综合结论</Text>
        <Text style={styles.coverage} testID="decision-coverage">
          因子覆盖 {(score.factorCoverage * 100).toFixed(0)}%
        </Text>
      </View>
      <Text style={styles.score} testID="decision-score">
        {score.value.toFixed(1)}
        <Text style={styles.direction}>
          {"  "}
          {score.direction === "bullish"
            ? "偏多"
            : score.direction === "bearish"
              ? "偏空"
              : "中性"}
        </Text>
      </Text>
      {score.unavailableFactors.length ? (
        <Text style={styles.missing} testID="decision-missing-factors">
          未接入因子：{score.unavailableFactors.join("、")}
        </Text>
      ) : null}
      {decision.forecast ? (
        <View style={styles.scenarios} testID="decision-scenarios">
          {decision.forecast.cases.map((item) => (
            <Text key={item.kind} style={styles.scenario}>
              {item.kind === "bear" ? "下行" : item.kind === "bull" ? "上行" : "基准"}{" "}
              {(item.probability * 100).toFixed(0)}% ·{" "}
              {item.priceLow.toFixed(2)}–{item.priceHigh.toFixed(2)}
            </Text>
          ))}
          <Text style={styles.note}>{decision.forecast.disclaimer}</Text>
        </View>
      ) : (
        <Text style={styles.missing} testID="decision-no-forecast">
          情景预测暂不可用
        </Text>
      )}
      {decision.riskPlan ? (
        <View style={styles.plan} testID="decision-plan">
          <Text style={styles.planLine}>
            建议 {planLabel(decision.riskPlan.action)} · 仓位上限{" "}
            {decision.riskPlan.maxPositionPercent.toFixed(0)}% · 杠杆上限{" "}
            {decision.riskPlan.leverage.toFixed(2)}×
          </Text>
          {decision.riskPlan.warnings.map((warning) => (
            <Text key={warning} style={styles.warning}>
              · {warning}
            </Text>
          ))}
        </View>
      ) : null}
      {decision.notes.map((note) => (
        <Text key={note} style={styles.note}>
          · {note}
        </Text>
      ))}
    </View>
  );
}

function planLabel(action: string) {
  return { long: "做多", short: "做空", watch: "观望", avoid: "回避" }[action] ?? action;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: 1,
    gap: spacing.xs,
    padding: spacing.md,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  eyebrow: { color: colors.muted, fontSize: 9, fontWeight: "800", letterSpacing: 0.6 },
  coverage: { color: colors.amber, fontSize: 10, fontWeight: "800" },
  score: { color: colors.ink, fontSize: 26, fontWeight: "900" },
  direction: { color: colors.muted, fontSize: 12, fontWeight: "800" },
  missing: { color: colors.amber, fontSize: 10, fontWeight: "700", lineHeight: 15 },
  unavailable: { color: colors.muted, fontSize: 14, fontWeight: "800" },
  scenarios: { gap: 2, marginTop: 2 },
  scenario: { color: colors.ink, fontSize: 11, fontVariant: ["tabular-nums"] },
  plan: { gap: 2, marginTop: 2 },
  planLine: { color: colors.ink, fontSize: 11, fontWeight: "700" },
  warning: { color: colors.muted, fontSize: 9, lineHeight: 13 },
  note: { color: colors.muted, fontSize: 9, lineHeight: 13 },
});
