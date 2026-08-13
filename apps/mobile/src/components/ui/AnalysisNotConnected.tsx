import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "@/theme/tokens";

/**
 * Shown wherever a screen would otherwise render fixture analysis while the
 * app is on real market data. Presenting a developer fixture as a conclusion
 * about a live market is the most damaging thing this app could do, so the
 * surface stays empty and says why.
 *
 * `missing` is required, and it is required because the copy it replaced was a
 * single fixed sentence blaming an analysis service that had not shipped yet.
 * That service is deployed now, and each of these screens is waiting on
 * something different — a route, a key, a scan — so the reason has to be
 * supplied per surface or it goes stale again the moment one of them lands.
 */
export function AnalysisNotConnected({
  surface,
  missing,
  testID = "analysis-not-connected",
}: {
  surface: string;
  /** What is actually absent, stated concretely enough to act on. */
  missing: string;
  testID?: string;
}) {
  return (
    <View style={styles.container} testID={testID}>
      <Text style={styles.title}>{surface}尚未接入</Text>
      <Text style={styles.body}>{missing}</Text>
      <Text style={styles.body}>
        接上之前这里保持空白，不会用演示内容顶替。
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
