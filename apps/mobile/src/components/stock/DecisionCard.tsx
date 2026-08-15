import { StyleSheet, Text, View } from "react-native";

import { ADVISER_SCORE_CAP } from "@/domain/models";
import type { Decision } from "@/domain/models";
import {
  factorLabel,
  gateLabel,
  intervalLabel,
  planActionLabel,
  scenarioLabel,
  scoreDirectionLabel,
  serviceTextLabel,
} from "@/i18n/serverVocabulary";
import { colors, radius, spacing } from "@/theme/tokens";

/**
 * Renders one composed decision.
 *
 * The service states what it could not see; showing the score without its
 * coverage would hand the reader a number that looks like a full picture.
 *
 * Everything the service says arrives in English or in its own identifiers,
 * and every one of them passes through @/i18n/serverVocabulary on the way to a
 * Text node. A gate this app has no name for is still printed, unreadable and
 * all: the reader has to learn the conclusion was gated even when the reason
 * is new.
 */
export function DecisionCard({ decision }: { decision: Decision }) {
  if (decision.status === "unavailable" || !decision.score) {
    return (
      <View style={styles.card} testID="decision-card">
        <Text style={styles.eyebrow}>综合结论</Text>
        <Text style={styles.interval} testID="decision-interval">
          分析周期 · {intervalLabel(decision.interval)}
        </Text>
        <Text style={styles.unavailable}>暂不可用</Text>
        {decision.notes.map((note) => (
          <Text key={note} style={styles.note}>
            · {serviceTextLabel(note)}
          </Text>
        ))}
      </View>
    );
  }

  const { score } = decision;
  const measuredFactors = score.contributions.filter(
    (contribution) => contribution.rawValue !== null,
  );
  return (
    <View style={styles.card} testID="decision-card">
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>综合结论</Text>
          <Text style={styles.interval} testID="decision-interval">
            分析周期 · {intervalLabel(decision.interval)}
          </Text>
        </View>
        <Text style={styles.coverage} testID="decision-coverage">
          因子覆盖 {(score.factorCoverage * 100).toFixed(0)}%
        </Text>
      </View>
      <Text style={styles.score} testID="decision-score">
        {score.value.toFixed(1)}
        <Text style={styles.direction}>
          {"  "}
          {scoreDirectionLabel(score.direction)}
        </Text>
      </Text>
      {/* The split renders only once an adviser council actually ran for this
          response — adviserAdjustment is null, not zero, for every request
          that never convened one (adviser=off, adviser="news"), so a score
          nobody's council touched must not read as adviser-checked. */}
      {decision.adviserCouncil?.status === "available" &&
      decision.adviserAdjustment !== null &&
      decision.baselineScore !== null ? (
        <Text style={styles.adviserFold} testID="decision-adviser-fold">
          顾问核验前 {decision.baselineScore.value.toFixed(1)} · 顾问调整{" "}
          {decision.adviserAdjustment > 0 ? "+" : ""}
          {decision.adviserAdjustment.toFixed(1)}（上限 ±
          {ADVISER_SCORE_CAP.toFixed(1)}）
        </Text>
      ) : null}
      {/* A blocked conclusion must not look like an ordinary one. The gate used
          to reach the screen only through the risk plan's warnings, and a
          decision with no measurable volatility has no risk plan — so a score
          the engine had refused to act on was displayed exactly like a clean
          one. */}
      {!score.actionable ? (
        <View style={styles.blocked} testID="decision-blocked">
          <Text style={styles.blockedTitle}>不可行动</Text>
          {score.blockedBy.length ? (
            <Text style={styles.blockedReason}>
              被拦截：{score.blockedBy.map(gateLabel).join("、")}
            </Text>
          ) : (
            <Text style={styles.blockedReason}>
              可用因子不足以形成结论
            </Text>
          )}
        </View>
      ) : null}
      {score.unavailableFactors.length ? (
        <Text style={styles.missing} testID="decision-missing-factors">
          未接入因子：{score.unavailableFactors.map(factorLabel).join("、")}
        </Text>
      ) : null}
      {measuredFactors.length ? (
        <View style={styles.factors} testID="decision-factor-breakdown">
          <Text style={styles.factorSectionTitle}>分析因子明细</Text>
          {measuredFactors.map((contribution) => (
            <View key={contribution.name} style={styles.factorRow}>
              <View style={styles.factorHeader}>
                <Text style={styles.factorName}>
                  {factorLabel(contribution.name)}
                </Text>
                <Text style={styles.factorPoints}>
                  贡献 {contribution.points >= 0 ? "+" : ""}
                  {contribution.points.toFixed(2)}
                </Text>
              </View>
              <Text style={styles.factorMeta}>
                输入 {contribution.rawValue!.toFixed(2)} · 权重{" "}
                {(contribution.weight * 100).toFixed(0)}%
              </Text>
              <Text style={styles.factorExplanation}>
                {serviceTextLabel(contribution.explanation)}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
      {decision.forecast ? (
        <View style={styles.scenarios} testID="decision-scenarios">
          {decision.forecast.cases.map((item) => (
            <Text key={item.kind} style={styles.scenario}>
              {scenarioLabel(item.kind)}{" "}
              {(item.probability * 100).toFixed(0)}% ·{" "}
              {item.priceLow.toFixed(2)}–{item.priceHigh.toFixed(2)}
            </Text>
          ))}
          <Text style={styles.note}>
            {serviceTextLabel(decision.forecast.disclaimer)}
          </Text>
        </View>
      ) : (
        <Text style={styles.missing} testID="decision-no-forecast">
          情景预测暂不可用
        </Text>
      )}
      {decision.riskPlan ? (
        <View style={styles.plan} testID="decision-plan">
          <Text style={styles.planLine}>
            建议 {planActionLabel(decision.riskPlan.action)} · 仓位上限{" "}
            {decision.riskPlan.maxPositionPercent.toFixed(0)}% · 杠杆上限{" "}
            {decision.riskPlan.leverage.toFixed(2)}×
          </Text>
          {decision.riskPlan.warnings.map((warning) => (
            <Text key={warning} style={styles.warning}>
              · {serviceTextLabel(warning)}
            </Text>
          ))}
        </View>
      ) : null}
      {decision.notes.map((note) => (
        <Text key={note} style={styles.note}>
          · {serviceTextLabel(note)}
        </Text>
      ))}
    </View>
  );
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
  eyebrow: { color: colors.muted, fontSize: 12, fontWeight: "800", letterSpacing: 0.6 },
  interval: { color: colors.ink, fontSize: 12, fontWeight: "800", marginTop: 2 },
  coverage: { color: colors.amber, fontSize: 12, fontWeight: "800" },
  score: { color: colors.ink, fontSize: 26, fontWeight: "900" },
  direction: { color: colors.muted, fontSize: 12, fontWeight: "800" },
  adviserFold: { color: colors.muted, fontSize: 12, fontWeight: "700" },
  blocked: {
    backgroundColor: colors.amberSoft,
    borderRadius: radius.sm,
    gap: 2,
    padding: spacing.xs,
  },
  blockedTitle: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  blockedReason: { color: colors.ink, fontSize: 12, lineHeight: 18 },
  missing: { color: colors.amber, fontSize: 12, fontWeight: "700", lineHeight: 18 },
  factors: { gap: spacing.xs, marginTop: spacing.xs },
  factorSectionTitle: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  factorRow: {
    backgroundColor: colors.background,
    borderRadius: radius.sm,
    gap: 3,
    padding: spacing.sm,
  },
  factorHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  factorName: { color: colors.ink, fontSize: 12, fontWeight: "900" },
  factorPoints: {
    color: colors.blue,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "900",
  },
  factorMeta: {
    color: colors.muted,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "700",
  },
  factorExplanation: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  unavailable: { color: colors.muted, fontSize: 14, fontWeight: "800" },
  scenarios: { gap: 2, marginTop: 2 },
  scenario: { color: colors.ink, fontSize: 12, fontVariant: ["tabular-nums"] },
  plan: { gap: 2, marginTop: 2 },
  planLine: { color: colors.ink, fontSize: 12, fontWeight: "700", lineHeight: 18 },
  warning: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  note: { color: colors.muted, fontSize: 12, lineHeight: 18 },
});
