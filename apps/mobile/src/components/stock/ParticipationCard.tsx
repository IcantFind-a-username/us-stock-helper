import { StyleSheet, Text, View } from "react-native";

import type {
  DelayedInstitutionalHolding,
  ParticipationBar,
} from "@/domain/models";
import { serviceTextLabel, snapshotSourceLabel } from "@/i18n/serverVocabulary";
import { colors, radius, spacing } from "@/theme/tokens";

type ParticipationCardProps = {
  bars: ParticipationBar[];
  holdings: DelayedInstitutionalHolding[];
};

function formatUtc(value: string) {
  return value.replace("T", " ").replace(".000Z", " UTC");
}

export function ParticipationCard({
  bars,
  holdings,
}: ParticipationCardProps) {
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
  const latestHolding = holdings[0];

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
      {/* The proxy caption lives in the screen's disclosure now: one card
          repeating it under every chart is what buried the numbers. */}
      {missing.length ? (
        <Text style={styles.uncertainty}>
          {missing.length} 根缺失 ·{" "}
          {missing
            .map(({ missingReason }) =>
              missingReason === null ? "未给出原因" : serviceTextLabel(missingReason),
            )
            .join("；")}
        </Text>
      ) : null}

      <View style={styles.divider} />
      <View style={styles.reportedHeader}>
        <Text style={styles.reportedTitle}>机构持仓披露 · 延迟数据</Text>
        <Text style={styles.date}>独立于盘中活动</Text>
      </View>
      {latestHolding ? (
        <>
          <Text style={styles.ownership}>
            {latestHolding.period} · {latestHolding.holdingPercent.toFixed(2)}% ·{" "}
            {latestHolding.institutionCount} 家机构
          </Text>
          <Text style={styles.uncertainty}>
            报告期 {formatUtc(latestHolding.reportedAt)} · 可用时间{" "}
            {formatUtc(latestHolding.availableAt)}
          </Text>
          <Text style={styles.uncertainty}>
            {snapshotSourceLabel(latestHolding.source)} ·{" "}
            {latestHolding.methodVersion}
          </Text>
        </>
      ) : (
        <Text style={styles.uncertainty}>暂无延迟申报持仓</Text>
      )}
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
  eyebrow: { color: colors.muted, fontSize: 9, fontWeight: "700" },
  title: { color: colors.ink, fontSize: 15, fontWeight: "900", marginTop: 1 },
  proxyBadge: {
    backgroundColor: colors.amberSoft,
    borderRadius: radius.pill,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  proxyText: { color: "#8B5C08", fontSize: 9, fontWeight: "900" },
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
    fontSize: 10,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
  },
  note: { color: colors.muted, fontSize: 10, lineHeight: 15 },
  uncertainty: { color: colors.muted, fontSize: 8, lineHeight: 12 },
  divider: { backgroundColor: colors.line, height: StyleSheet.hairlineWidth },
  reportedHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  reportedTitle: { color: colors.ink, fontSize: 12, fontWeight: "800" },
  date: { color: colors.muted, fontSize: 9, fontWeight: "700" },
  ownership: {
    color: colors.ink,
    fontSize: 10,
    fontVariant: ["tabular-nums"],
    fontWeight: "700",
  },
});
