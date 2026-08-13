import { Pressable, StyleSheet, Text, View } from "react-native";

import type { CandleInterval } from "@/data/marketGateway";
import { colors, radius, spacing } from "@/theme/tokens";

export type ChartDisplayInterval = Extract<
  CandleInterval,
  "day" | "60m" | "15m" | "5m"
>;

const intervalOptions: readonly {
  value: ChartDisplayInterval;
  label: string;
  count: number;
}[] = [
  { value: "day", label: "日K", count: 250 },
  { value: "60m", label: "60分", count: 240 },
  { value: "15m", label: "15分", count: 240 },
  { value: "5m", label: "5分", count: 200 },
];

export function candleCountForInterval(interval: ChartDisplayInterval): number {
  return intervalOptions.find(({ value }) => value === interval)?.count ?? 200;
}

type ChartIntervalSwitchProps = {
  value: ChartDisplayInterval;
  onChange(interval: ChartDisplayInterval): void;
};

export function ChartIntervalSwitch({
  value,
  onChange,
}: ChartIntervalSwitchProps) {
  return (
    <View accessibilityLabel="K线周期" accessibilityRole="tablist" style={styles.switch}>
      {intervalOptions.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            key={option.value}
            onPress={() => onChange(option.value)}
            style={({ pressed }) => [
              styles.option,
              selected && styles.optionSelected,
              pressed && styles.optionPressed,
            ]}>
            <Text style={[styles.label, selected && styles.labelSelected]}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  switch: {
    backgroundColor: "#E4E9F1",
    borderRadius: radius.md,
    flexDirection: "row",
    gap: spacing.sm,
    padding: spacing.xs,
  },
  option: {
    alignItems: "center",
    borderRadius: radius.sm,
    flex: 1,
    justifyContent: "center",
    minHeight: 44,
  },
  optionSelected: {
    backgroundColor: colors.card,
    shadowColor: colors.ink,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 3,
  },
  optionPressed: { opacity: 0.72 },
  label: { color: colors.muted, fontSize: 13, fontWeight: "800" },
  labelSelected: { color: colors.blue },
});
