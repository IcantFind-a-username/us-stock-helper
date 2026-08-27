import { StyleSheet, Text, View } from "react-native";

import type {
  ParticipationBar,
} from "@/domain/models";
import { serviceTextLabel } from "@/i18n/serverVocabulary";
import { colors, radius, spacing } from "@/theme/tokens";

type ParticipationCardProps = {
  bars: ParticipationBar[];
};

/** One line per distinct reason, with how many bars gave it. */
function summariseMissing(missing: readonly ParticipationBar[]) {
  const counts = new Map<string, number>();
  for (const { missingReason } of missing) {
    const label =
      missingReason === null ? "未给出原因" : serviceTextLabel(missingReason);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  const only = counts.size === 1;
  return [...counts.entries()]
    .map(([label, count]) => (only ? label : `${label}（${count} 根）`))
    .join("；");
}

export function ParticipationCard({ bars }: ParticipationCardProps) {
  const latestAvailable = [...bars]
    .reverse()
    .find(
      (bar) =>
        bar.qualityStatus === "live" &&
        bar.mainShare !== null &&
        bar.retailShare !== null,
    );
  const missing = bars.filter(
    ({ qualityStatus }) => qualityStatus === "unavailable",
  );
  return (
    <View style={styles.card} testID="participation-summary">
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>盘中参与结构</Text>
          <Text style={styles.title}>订单规模活动占比</Text>
        </View>
        <View style={styles.proxyBadge}>
          <Text style={styles.proxyText}>非账户身份</Text>
        </View>
      </View>

      {latestAvailable ? (
        <View
          accessibilityLabel={`主力代理 ${(latestAvailable.mainShare! * 100).toFixed(1)}%，散户代理 ${(latestAvailable.retailShare! * 100).toFixed(1)}%`}
          style={styles.bar}>
          <View
            style={[
              styles.institution,
              { flex: latestAvailable.mainShare! },
            ]}
          />
          <View
            style={[styles.retail, { flex: latestAvailable.retailShare! }]}
          />
        </View>
      ) : null}
      <Text style={styles.latest}>
        {latestAvailable
          ? `主力代理 ${(latestAvailable.mainShare! * 100).toFixed(1)}% · 散户代理 ${(latestAvailable.retailShare! * 100).toFixed(1)}%`
          : "暂无可用活动占比"}
      </Text>
      {latestAvailable ? (
        <Text
          style={styles.methodVersion}
          testID="participation-method-version">
          算法版本 {latestAvailable.methodVersion}
        </Text>
      ) : null}
      {/* The proxy caption lives in the screen's disclosure now: one card
          repeating it under every chart is what buried the numbers. */}
      {missing.length ? (
        // Grouped, because every bar in a snapshot without capital flow
        // carries the same sentence: printing it per bar filled the screen
        // with two hundred copies and buried the disclosure below it.
        <Text style={styles.uncertainty} testID="participation-missing-summary">
          {missing.length} 根缺失 · {summariseMissing(missing)}
        </Text>
      ) : null}

    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.md,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  eyebrow: { color: colors.muted, fontSize: 12, fontWeight: "700" },
  title: { color: colors.ink, fontSize: 15, fontWeight: "900", marginTop: 1 },
  proxyBadge: {
    backgroundColor: colors.amberSoft,
    borderRadius: radius.pill,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  proxyText: { color: "#8B5C08", fontSize: 12, fontWeight: "900" },
  bar: {
    borderRadius: radius.sm,
    flexDirection: "row",
    height: 12,
    overflow: "hidden",
  },
  institution: { backgroundColor: colors.navyRaised },
  retail: { backgroundColor: colors.blue },
  latest: {
    color: colors.ink,
    fontSize: 13,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
  },
  methodVersion: { color: colors.muted, fontSize: 11 },
  note: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  uncertainty: { color: colors.muted, fontSize: 12, lineHeight: 18 },
});
