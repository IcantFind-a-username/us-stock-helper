import { StyleSheet, Text, View } from "react-native";

import type {
  DelayedInstitutionalHolding,
  SnapshotSection,
} from "@/domain/models";
import { colors, radius, shadow, spacing } from "@/theme/tokens";

type InstitutionalHoldingsCardProps = {
  section: SnapshotSection<DelayedInstitutionalHolding[]>;
};

const DAY_MS = 24 * 60 * 60 * 1000;
const HISTORY_LIMIT = 5;
const HOLDINGS_UNAVAILABLE = "机构持仓数据不可用";
const AGGREGATE_PERCENT_WARNING =
  "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释";
const HOLDINGS_SECTION_COPY: Readonly<Record<string, string>> = {
  HOLDINGS_UNAVAILABLE,
  MISSING_REQUIRED_FIELD: "机构持仓记录缺少必填字段",
  INVALID_REPORTING_PERIOD: "机构持仓报告期格式无效",
  INVALID_NUMERIC_VALUE: "机构持仓数值无效",
  WRONG_HOLDINGS_SOURCE: "机构持仓来源无效",
  FUTURE_HOLDINGS_ROW: "机构持仓记录晚于决策截止时间",
  OUT_OF_ORDER_HOLDINGS_ROW: "机构持仓记录顺序无效",
  AGGREGATE_PERCENT_ABOVE_100: AGGREGATE_PERCENT_WARNING,
};

export function adaptDemoHoldingsSection(
  holdings: DelayedInstitutionalHolding[],
): SnapshotSection<DelayedInstitutionalHolding[]> {
  const latest = holdings[0];
  return latest
    ? {
        availabilityStatus: "delayed",
        qualityStatus: "validated",
        source: "moomoo-delayed-institutional-disclosure",
        asOf: latest.reportedAt,
        availableAt: latest.availableAt,
        receivedAt: latest.availableAt,
        data: holdings,
        errorCode: null,
        reason: null,
        warnings: [],
        anomalies: [],
        methodVersion: "reported-holdings-v1",
      }
    : {
        availabilityStatus: "unavailable",
        qualityStatus: "invalid",
        source: null,
        asOf: null,
        availableAt: null,
        receivedAt: null,
        data: null,
        errorCode: "HOLDINGS_UNAVAILABLE",
        reason: HOLDINGS_UNAVAILABLE,
        warnings: [],
        anomalies: [],
        methodVersion: "unavailable-v1",
      };
}

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

function safeSectionMessages(
  section: SnapshotSection<DelayedInstitutionalHolding[]>,
): string[] {
  const messages = [
    ...(section.warnings.includes(AGGREGATE_PERCENT_WARNING)
      ? [AGGREGATE_PERCENT_WARNING]
      : []),
    ...section.anomalies.flatMap(({ code }) => {
      const copy = HOLDINGS_SECTION_COPY[code];
      return copy ? [copy] : [];
    }),
  ];
  return [...new Set(messages)];
}

function safeUnavailableCopy(
  section: SnapshotSection<DelayedInstitutionalHolding[]>,
): string {
  const errorCopy = section.errorCode
    ? HOLDINGS_SECTION_COPY[section.errorCode]
    : undefined;
  if (errorCopy) return errorCopy;
  for (const { code } of section.anomalies) {
    const anomalyCopy = HOLDINGS_SECTION_COPY[code];
    if (anomalyCopy) return anomalyCopy;
  }
  return HOLDINGS_UNAVAILABLE;
}

function holdingPercentText(
  value: number,
  methodVersion: string,
): string {
  return methodVersion === "reported-holdings-v2-anomaly-aware"
    ? String(value)
    : value.toFixed(2);
}

export function InstitutionalHoldingsCard({
  section,
}: InstitutionalHoldingsCardProps) {
  const holdings = section.data ?? [];
  const latest = holdings[0];
  const safeMessages = safeSectionMessages(section);

  if (section.availabilityStatus === "unavailable" || !latest) {
    return (
      <View style={styles.card} testID="institutional-holdings-empty">
        <Text style={styles.eyebrow}>机构持仓披露 · 延迟数据</Text>
        <Text style={styles.emptyTitle}>{safeUnavailableCopy(section)}</Text>
        <Text style={styles.body}>
          本次快照不显示百分比，不将缺失误写为零持仓。
        </Text>
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
        <Text style={styles.source} testID="institutional-holdings-source">
          来源 moomoo · 延迟机构披露
        </Text>
      </View>

      {section.qualityStatus === "anomalous" ? (
        <View
          accessibilityRole="alert"
          style={styles.warningPanel}
          testID="institutional-holdings-warning">
          <Text style={styles.warningTitle}>持仓质量异常</Text>
          {safeMessages.map((message) => (
            <Text key={message} style={styles.warningText}>
              {message}
            </Text>
          ))}
        </View>
      ) : null}

      <Text style={styles.metricLabel}>机构持股比例</Text>
      <Text style={styles.headline} testID="institutional-holdings-percent">
        {holdingPercentText(latest.holdingPercent, section.methodVersion)}%
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
          <Text style={styles.historyPercent}>
            {holdingPercentText(item.holdingPercent, section.methodVersion)}%
          </Text>
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
  eyebrow: { color: colors.muted, fontSize: 13, fontWeight: "800" },
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
  delayBadgeText: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  lagPanel: {
    backgroundColor: colors.backgroundRaised,
    borderRadius: radius.md,
    gap: spacing.xs,
    padding: spacing.md,
  },
  lag: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  basis: { color: colors.muted, fontSize: 13, lineHeight: 20 },
  source: { color: colors.muted, fontSize: 13, lineHeight: 20 },
  warningPanel: {
    backgroundColor: colors.amberSoft,
    borderColor: colors.amber,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    padding: spacing.md,
  },
  warningTitle: { color: colors.ink, fontSize: 15, fontWeight: "900" },
  warningText: { color: colors.ink, fontSize: 13, lineHeight: 20 },
  metricLabel: { color: colors.muted, fontSize: 13, fontWeight: "700" },
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
  metricChange: { fontSize: 13, fontWeight: "800" },
  verticalDivider: {
    backgroundColor: colors.line,
    marginHorizontal: spacing.md,
    width: StyleSheet.hairlineWidth,
  },
  divider: { backgroundColor: colors.line, height: StyleSheet.hairlineWidth },
  historyTitle: { color: colors.ink, fontSize: 15, fontWeight: "900" },
  historyRow: { alignItems: "center", flexDirection: "row", minHeight: 28 },
  historyPeriod: { color: colors.muted, flex: 1, fontSize: 13, fontWeight: "700" },
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
    fontSize: 13,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
    textAlign: "right",
  },
  coverage: { color: colors.muted, fontSize: 13, lineHeight: 20 },
  emptyTitle: { color: colors.ink, fontSize: 16, fontWeight: "900" },
  body: { color: colors.muted, fontSize: 13, lineHeight: 20 },
});
