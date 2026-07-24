import { Pressable, StyleSheet, Text, View } from "react-native";

import type { Horizon } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

const horizonLabels = {
  short: "短线 · 0–5日",
  swing: "波段 · 1–8周",
  long: "中长线 · 2–24月",
} as const;

const horizons: Horizon[] = ["short", "swing", "long"];

type HorizonSwitchProps = {
  value: Horizon;
  onChange: (horizon: Horizon) => void;
};

export function HorizonSwitch({ value, onChange }: HorizonSwitchProps) {
  return (
    <View accessibilityRole="tablist" style={styles.switch}>
      {horizons.map((horizon) => {
        const selected = horizon === value;

        return (
          <Pressable
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            key={horizon}
            onPress={() => onChange(horizon)}
            style={[styles.option, selected && styles.optionSelected]}>
            <Text style={[styles.label, selected && styles.labelSelected]}>{horizonLabels[horizon]}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  switch: {
    backgroundColor: colors.blueSoft,
    borderRadius: radius.pill,
    flexDirection: "row",
    padding: spacing.xs,
  },
  option: {
    alignItems: "center",
    borderRadius: radius.pill,
    flex: 1,
    minHeight: 36,
    justifyContent: "center",
    paddingHorizontal: spacing.sm,
  },
  optionSelected: {
    backgroundColor: colors.card,
  },
  label: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
  },
  labelSelected: {
    color: colors.blue,
  },
});
