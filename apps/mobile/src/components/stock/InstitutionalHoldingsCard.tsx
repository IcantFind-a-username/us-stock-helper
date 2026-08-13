import { StyleSheet, Text, View } from "react-native";

import type { DelayedInstitutionalHolding } from "@/domain/models";
import { colors, radius, shadow, spacing } from "@/theme/tokens";

type InstitutionalHoldingsCardProps = {
  holdings: readonly DelayedInstitutionalHolding[];
};

const DAY_MS = 24 * 60 * 60 * 1000;
const HISTORY_LIMIT = 5;

function formatDate(value: string): string {
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime())
    ? parsed.toISOString().slice(0, 10)
    : "日期未知";
}

function disclosureLag(
  reportedAt: string,
  availableAt: string,
): string | null {
  const reported = new Date(reportedAt).getTime();
  const available = new Date(availableAt).getTime();
  if (!Number.isFinite(reported) || !Number.isFinite(available) || available < reported) {
    return null;
  }
  return `${Math.ceil((available - reported) / DAY_MS)} 天`;
}

function signed(value: number, digits = 0): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(digits)}`;
}

function compactShares(value: number): string {
  const absolute = Math.abs(value);
  if (absolute >= 100_000_000) return `${(value / 100_000_000).toFixed(2)} 亿`;
  if (absolute >= 10_000) return `${(value / 10_000).toFixed(1)} 万`;
  return `${Math.round(value).toLocaleString("en-US")} 股`;
}

function signedShares(value: number): string {
  if (value === 0) return "持平";
  return `${value > 0 ? "+" : ""}${compactShares(value)}`;
}

function changeColor(value: number) {
  return value > 0 ? colors.green : value < 0 ? colors.red : colors.muted;
}

function percentChangeText(value: number): string {
  if (value === 0) return "较上季持平";
  const direction = value > 0 ? "▲ 增加" : "▼ 减少";
  return `${direction} · 较上季 ${signed(value, 2)} 个百分点`;
}

export function InstitutionalHoldingsCard({
  holdings,
}: InstitutionalHoldingsCardProps) {
  const latest = holdings[0];

  if (!latest) {
    return (
      <View style={styles.card} testID="institutional-holdings-empty">
        <Text style={styles.eyebrow}>机构持仓披露 · 延迟数据</Text>
        <Text style={styles.emptyTitle}>本次快照未提供机构持仓披露</Text>
        <Text style={styles.body}>暂无数字可展示，不将缺失误写为零持仓。</Text>
      </View>
    );
  }

  const lag = disclosureLag(latest.reportedAt, latest.availableAt);
  const history = holdings.slice(0, HISTORY_LIMIT);

  return (
    <View style={styles.card} testID="institutional-holdings-card">
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>机构持仓披露 · 延迟数据</Text>
          <Text style={styles.period} testID="institutional-holdings-period">
            {latest.period} · {formatDate(latest.reportedAt)}
          </Text>
        </View>
        <View style={styles.delayBadge}>
          <Text style={styles.delayBadgeText}>非实时</Text>
        </View>
      </View>

      <View style={styles.lagPanel}>
        <Text style={styles.lag} testID="institutional-holdings-lag">
          季度披露 · {lag ? `滞后 ${lag}` : "滞后未知"}
        </Text>
        <Text style={styles.basis} testID="institutional-holdings-basis">
          数据基于报告期末，不是当前持仓
        </Text>
      </View>

      <Text style={styles.metricLabel}>机构持股比例</Text>
      <Text style={styles.headline} testID="institutional-holdings-percent">
        {latest.holdingPercent.toFixed(2)}%
      </Text>
      <Text
        style={[
          styles.primaryChange,
          { color: changeColor(latest.holdingPercentChange) },
        ]}
        testID="institutional-holdings-percent-change">
        {percentChangeText(latest.holdingPercentChange)}
      </Text>

      <View style={styles.metrics}>
        <View style={styles.metric}>
          <Text style={styles.metricLabel}>披露机构数</Text>
          <Text style={styles.metricValue} testID="institutional-holdings-count">
            {latest.institutionCount.toLocaleString("en-US")} 家
          </Text>
          <Text
            style={[
              styles.metricChange,
              { color: changeColor(latest.institutionCountChange) },
            ]}
            testID="institutional-holdings-count-change">
            较上季 {signed(latest.institutionCountChange)}
          </Text>
        </View>
        <View style={styles.verticalDivider} />
        <View style={styles.metric}>
          <Text style={styles.metricLabel}>披露持股数</Text>
          <Text style={styles.metricValue} testID="institutional-holdings-shares">
            {compactShares(latest.sharesHeld)}
          </Text>
          <Text
            style={[
              styles.metricChange,
              { color: changeColor(latest.sharesHeldChange) },
            ]}
            testID="institutional-holdings-shares-change">
            较上季 {signedShares(latest.sharesHeldChange)}
          </Text>
        </View>
      </View>

      <View style={styles.divider} />
      <Text style={styles.historyTitle}>最近季度趋势</Text>
      {history.map((item) => (
        <View
          key={`${item.period}-${item.reportedAt}`}
          style={styles.historyRow}
          testID="institutional-holdings-history-row">
          <Text style={styles.historyPeriod}>{item.period}</Text>
          <Text style={styles.historyPercent}>{item.holdingPercent.toFixed(2)}%</Text>
          <Text
            style={[
              styles.historyChange,
              { color: changeColor(item.holdingPercentChange) },
            ]}>
            {item.holdingPercentChange === 0
              ? "持平"
              : signed(item.holdingPercentChange, 2)}
          </Text>
        </View>
      ))}
      <Text style={styles.coverage} testID="institutional-holdings-coverage">
        共 {holdings.length} 期 · 已显示最近 {history.length} 期
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    ...shadow.card,
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.lg,
  },
  header: {
    alignItems: "flex-start",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  headerCopy: { flex: 1, gap: spacing.xs },
  eyebrow: { color: colors.muted, fontSize: 12, fontWeight: "800" },
  period: {
    color: colors.ink,
    fontSize: 15,
    fontVariant: ["tabular-nums"],
    fontWeight: "900",
  },
  delayBadge: {
    backgroundColor: colors.amberSoft,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  delayBadgeText: { color: "#8B5C08", fontSize: 12, fontWeight: "900" },
  lagPanel: {
    backgroundColor: colors.backgroundRaised,
    borderRadius: radius.md,
    gap: spacing.xs,
    padding: spacing.md,
  },
  lag: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  basis: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  metricLabel: { color: colors.muted, fontSize: 12, fontWeight: "700" },
  headline: {
    color: colors.ink,
    fontSize: 34,
    fontVariant: ["tabular-nums"],
    fontWeight: "900",
    letterSpacing: -1,
  },
  primaryChange: { fontSize: 13, fontWeight: "900" },
  metrics: { flexDirection: "row", paddingVertical: spacing.xs },
  metric: { flex: 1, gap: spacing.xs },
  metricValue: {
    color: colors.ink,
    fontSize: 19,
    fontVariant: ["tabular-nums"],
    fontWeight: "900",
  },
  metricChange: { fontSize: 12, fontWeight: "800" },
  verticalDivider: {
    backgroundColor: colors.line,
    marginHorizontal: spacing.md,
    width: StyleSheet.hairlineWidth,
  },
  divider: { backgroundColor: colors.line, height: StyleSheet.hairlineWidth },
  historyTitle: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  historyRow: { alignItems: "center", flexDirection: "row", minHeight: 24 },
  historyPeriod: { color: colors.muted, flex: 1, fontSize: 12, fontWeight: "700" },
  historyPercent: {
    color: colors.ink,
    flex: 1,
    fontSize: 13,
    fontVariant: ["tabular-nums"],
    fontWeight: "900",
    textAlign: "right",
  },
  historyChange: {
    flex: 1,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
    textAlign: "right",
  },
  coverage: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  emptyTitle: { color: colors.ink, fontSize: 17, fontWeight: "900" },
  body: { color: colors.muted, fontSize: 12, lineHeight: 18 },
});
