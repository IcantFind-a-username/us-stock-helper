import { Pressable, StyleSheet, Text, View } from "react-native";

import type { PlanSide, RiskPreference } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type PlanSelectorProps = {
  side: PlanSide;
  preference: RiskPreference;
  onSideChange(side: PlanSide): void;
  onPreferenceChange(preference: RiskPreference): void;
};

const sides: { value: PlanSide; label: string }[] = [
  { value: "long", label: "做多" },
  { value: "short", label: "做空" },
];

const preferences: { value: RiskPreference; label: string; detail: string }[] = [
  { value: "conservative", label: "稳健", detail: "更严确认" },
  { value: "balanced", label: "均衡", detail: "风险收益平衡" },
  { value: "aggressive", label: "进取", detail: "高回报倾向" },
];

export function PlanSelector({
  side,
  preference,
  onSideChange,
  onPreferenceChange,
}: PlanSelectorProps) {
  return (
    <View style={styles.stack}>
      <View accessibilityRole="tablist" style={styles.sideSwitch}>
        {sides.map((option) => {
          const selected = option.value === side;
          return (
            <Pressable
              accessibilityLabel={`${option.label}方案${selected ? "，已选择" : ""}`}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              key={option.value}
              onPress={() => onSideChange(option.value)}
              style={[styles.sideOption, selected && styles.sideSelected]}>
              <Text style={[styles.sideText, selected && styles.sideTextSelected]}>
                {option.label}方案
              </Text>
            </Pressable>
          );
        })}
      </View>
      <View>
        <View style={styles.preferenceHeader}>
          <Text style={styles.heading}>风险—回报倾向</Text>
          <Text style={styles.caption}>只调整方案，不调整事实</Text>
        </View>
        <View style={styles.preferences}>
          {preferences.map((option) => {
            const selected = option.value === preference;
            return (
              <Pressable
                accessibilityLabel={`${option.label}风险偏好${selected ? "，已选择" : ""}`}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                key={option.value}
                onPress={() => onPreferenceChange(option.value)}
                style={[styles.preference, selected && styles.preferenceSelected]}>
                <Text style={[styles.preferenceLabel, selected && styles.preferenceLabelSelected]}>
                  {option.label}
                </Text>
                <Text style={[styles.preferenceDetail, selected && styles.preferenceDetailSelected]}>
                  {option.detail}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>
      <Text style={styles.guardrail}>
        进取仍受单笔亏损、流动性、波动率、跳空、相关性与总敞口硬约束。
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: spacing.md },
  sideSwitch: { backgroundColor: colors.background, borderRadius: radius.md, flexDirection: "row", padding: 3 },
  sideOption: { alignItems: "center", borderRadius: radius.sm, flex: 1, justifyContent: "center", minHeight: 44 },
  sideSelected: { backgroundColor: colors.navy },
  sideText: { color: colors.muted, fontSize: 12, fontWeight: "800" },
  sideTextSelected: { color: colors.card },
  preferenceHeader: { alignItems: "center", flexDirection: "row", justifyContent: "space-between", marginBottom: spacing.sm },
  heading: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  caption: { color: colors.muted, fontSize: 11, fontWeight: "600" },
  preferences: { flexDirection: "row", gap: spacing.xs },
  preference: { alignItems: "center", backgroundColor: colors.card, borderColor: colors.line, borderRadius: radius.md, borderWidth: 1, flex: 1, justifyContent: "center", minHeight: 58, paddingHorizontal: 4 },
  preferenceSelected: { backgroundColor: colors.blueSoft, borderColor: colors.blue },
  preferenceLabel: { color: colors.ink, fontSize: 11, fontWeight: "900" },
  preferenceLabelSelected: { color: colors.blue },
  preferenceDetail: { color: colors.muted, fontSize: 11, fontWeight: "600", marginTop: 2 },
  preferenceDetailSelected: { color: "#3B5F91" },
  guardrail: { backgroundColor: colors.amberSoft, borderRadius: radius.sm, color: "#7A5208", fontSize: 11, fontWeight: "700", lineHeight: 14, overflow: "hidden", padding: spacing.sm },
});
