import { StyleSheet, Text, View } from "react-native";

import type { ParticipationGeometry } from "@/domain/chart";
import type { Candle } from "@/domain/models";
import { serviceTextLabel } from "@/i18n/serverVocabulary";
import { colors, radius, spacing } from "@/theme/tokens";

const stampLabel = (timestamp: string) => {
  const time = new Date(Date.parse(timestamp));
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(time.getUTCMonth() + 1)}-${pad(time.getUTCDate())} ${pad(
    time.getUTCHours(),
  )}:${pad(time.getUTCMinutes())}`;
};

function participationText(participation: ParticipationGeometry | undefined) {
  if (
    participation?.available &&
    participation.mainShare !== null &&
    participation.retailShare !== null &&
    participation.coverage !== null &&
    participation.source !== null
  ) {
    return `主力代理 ${(participation.mainShare * 100).toFixed(2)}% · 散户代理 ${(participation.retailShare * 100).toFixed(2)}% · 覆盖率 ${(participation.coverage * 100).toFixed(2)}% · ${participation.source}`;
  }
  const coverage =
    participation?.coverage === null || participation === undefined
      ? "覆盖率不可用"
      : `覆盖率 ${(participation.coverage * 100).toFixed(2)}%`;
  const source = participation?.source
    ? `来源 ${participation.source}`
    : "来源不可用";
  const reason = participation?.missingReason
    ? serviceTextLabel(participation.missingReason)
    : "活动占比不可用";
  return `活动占比缺失 · ${coverage} · ${source} · ${reason}`;
}

/**
 * One fixed-height strip under the chart.
 *
 * Its height never changes with the content, so selecting a bar cannot push
 * the chart around; the label is the only thing that moves.
 */
export function ChartReadout({
  candle,
  participation,
  showParticipation,
  detailLabel,
}: {
  candle: Candle | undefined;
  participation: ParticipationGeometry | undefined;
  showParticipation: boolean;
  detailLabel: string | null;
}) {
  return (
    <View
      accessibilityLabel={detailLabel ?? undefined}
      accessibilityLiveRegion="polite"
      accessible={detailLabel !== null}
      style={styles.strip}
      testID="chart-detail-strip">
      {candle && detailLabel ? (
        <>
          <Text style={styles.primary}>
            {stampLabel(candle.timestamp)} 开 {candle.open.toFixed(2)} 高{" "}
            {candle.high.toFixed(2)} 低 {candle.low.toFixed(2)} 收{" "}
            {candle.close.toFixed(2)} 量 {candle.volume}
          </Text>
          {showParticipation ? (
            <Text
              ellipsizeMode="tail"
              numberOfLines={2}
              style={styles.secondary}
              testID="participation-detail-text">
              {participationText(participation)}
            </Text>
          ) : null}
        </>
      ) : (
        <Text style={styles.primary}>轻点或长按图表读取精确 K 线</Text>
      )}
      {showParticipation ? (
        <Text style={styles.identity}>订单规模活动代理 · 非真实机构身份</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  strip: {
    backgroundColor: colors.background,
    borderRadius: radius.sm,
    gap: 3,
    justifyContent: "center",
    minHeight: 58,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
  },
  primary: {
    color: colors.ink,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "700",
    lineHeight: 18,
  },
  secondary: {
    color: colors.muted,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "600",
    lineHeight: 18,
  },
  identity: { color: colors.muted, fontSize: 12, fontWeight: "700" },
});
