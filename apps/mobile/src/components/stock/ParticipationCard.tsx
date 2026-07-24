import { StyleSheet, Text, View } from "react-native";

import type { ParticipationProxy, ReportedOwnership } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

type ParticipationCardProps = {
  proxy: ParticipationProxy;
  reported: ReportedOwnership;
};

const confidenceLabels = { low: "低", medium: "中", high: "高" } as const;

export function ParticipationCard({ proxy, reported }: ParticipationCardProps) {
  const uncertainty = { low: 12, medium: 8, high: 5 }[proxy.confidence];
  return (
    <View style={styles.card} testID="participation-proxy">
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>盘中参与结构</Text>
          <Text style={styles.title}>主力 / 散户资金代理</Text>
        </View>
        <View style={styles.proxyBadge}>
          <Text style={styles.proxyText}>{proxy.label}</Text>
        </View>
      </View>
      <View
        accessibilityLabel={`机构代理 ${proxy.institutionalPercent}%，散户代理 ${proxy.retailPercent}%`}
        style={styles.bar}>
        <View style={[styles.institution, { flex: proxy.institutionalPercent }]}>
          <Text style={styles.barText}>{`机构代理 ${proxy.institutionalPercent}%`}</Text>
        </View>
        <View style={[styles.retail, { flex: proxy.retailPercent }]}>
          <Text style={styles.barText}>{`散户代理 ${proxy.retailPercent}%`}</Text>
        </View>
      </View>
      <Text style={styles.note}>
        并非真实账户身份；由成交规模、场所与时序特征估算。置信度{" "}
        {confidenceLabels[proxy.confidence]} · {proxy.sourceCoverage} · {proxy.methodVersion}
      </Text>
      <Text style={styles.uncertainty}>
        估算时点 {formatAsOf(proxy.estimatedAt)} · 误差带约 ±{uncertainty} 个百分点；未分类流量会降低置信度。
      </Text>
      <View style={styles.divider} />
      <View style={styles.reportedHeader}>
        <Text style={styles.reportedTitle}>正式申报持仓</Text>
        <Text style={styles.date}>{`报告期 ${reported.reportedAt}`}</Text>
      </View>
      <View style={styles.ownershipRow}>
        <Text style={styles.ownership}>机构 {reported.institutionalPercent}%</Text>
        <Text style={styles.ownership}>内部人 {reported.insiderPercent}%</Text>
        <Text style={styles.ownership}>其他 {reported.otherPercent}%</Text>
      </View>
      {reported.changes.map((change) => (
        <Text key={change} style={styles.change}>
          · {change}
        </Text>
      ))}
      <Text style={styles.uncertainty}>披露可用时间 {formatAsOf(reported.availableAt)}</Text>
    </View>
  );
}

function formatAsOf(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", {
        hour12: false,
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
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
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  eyebrow: { color: colors.muted, fontSize: 9, fontWeight: "700" },
  title: { color: colors.ink, fontSize: 15, fontWeight: "900", marginTop: 1 },
  proxyBadge: { backgroundColor: colors.amberSoft, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 4 },
  proxyText: { color: "#8B5C08", fontSize: 9, fontWeight: "900" },
  bar: { borderRadius: radius.sm, flexDirection: "row", height: 31, overflow: "hidden" },
  institution: { alignItems: "center", backgroundColor: colors.navyRaised, justifyContent: "center" },
  retail: { alignItems: "center", backgroundColor: colors.blue, justifyContent: "center" },
  barText: { color: colors.card, fontSize: 9, fontWeight: "800" },
  note: { color: colors.muted, fontSize: 10, lineHeight: 15 },
  uncertainty: { color: colors.muted, fontSize: 8, lineHeight: 12 },
  divider: { backgroundColor: colors.line, height: StyleSheet.hairlineWidth },
  reportedHeader: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  reportedTitle: { color: colors.ink, fontSize: 12, fontWeight: "800" },
  date: { color: colors.muted, fontSize: 9, fontWeight: "700" },
  ownershipRow: { flexDirection: "row", gap: spacing.md },
  ownership: { color: colors.ink, fontSize: 10, fontVariant: ["tabular-nums"], fontWeight: "700" },
  change: { color: colors.muted, fontSize: 10, lineHeight: 14 },
});
