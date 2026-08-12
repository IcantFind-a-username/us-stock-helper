import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "@/theme/tokens";

/**
 * Shown wherever a screen would otherwise render fixture analysis while the
 * app is on real market data. Presenting a developer fixture as a conclusion
 * about a live market is the most damaging thing this app could do, so the
 * surface stays empty and says why until a real analysis service backs it.
 */
export function AnalysisNotConnected({
  surface,
  testID = "analysis-not-connected",
}: {
  surface: string;
  testID?: string;
}) {
  return (
    <View style={styles.container} testID={testID}>
      <Text style={styles.title}>{surface}尚未接入真实数据</Text>
      <Text style={styles.body}>
        这里的内容只在演示模式展示确定性演示数据。真实分析服务上线前，不显示任何可能被误读为实盘结论的内容。
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.blueSoft,
    borderRadius: radius.md,
    gap: spacing.xs,
    padding: spacing.md,
  },
  title: { color: colors.ink, fontSize: 12, fontWeight: "800" },
  body: { color: colors.muted, fontSize: 10, lineHeight: 15 },
});
