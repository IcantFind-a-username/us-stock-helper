import { StyleSheet, Text, View } from "react-native";

import { PlainReadingCard } from "@/components/ui/PlainReadingCard";
import type { PatternShapeDetection, PatternShapeSignal } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

/**
 * Lists this snapshot's current 形态 (chart-shape) detections -- 顶分型/
 * 底分型/W底/双头/头肩顶/头肩底/回踩五日线企稳 -- each status-colored and
 * expandable into its full three-layer reading (via `PlainReadingCard`, the
 * shared house component for that contract; this card supplies no vocabulary
 * of its own, only the served signal's already-Chinese, already-versioned
 * copy from `services/analysis_core/us_stock_helper_core/patterns_shapes.py`).
 *
 * Absence is disclosed honestly and distinctly: every detector below its own
 * minimum window ("样本不足") reads differently from every detector having
 * run and found nothing ("看过了，没有") -- the same distinction
 * patterns_shapes.py itself draws between `qualityStatus: "unavailable"` and
 * a live detection with an empty `signals` array.
 */

const STATUS_LABEL: Record<PatternShapeSignal["status"], string> = {
  forming: "形成中",
  confirmed: "已确认",
  invalidated: "已失效",
};

const STATUS_STYLE_KEY: Record<PatternShapeSignal["status"], "forming" | "confirmed" | "invalidated"> =
  {
    forming: "forming",
    confirmed: "confirmed",
    invalidated: "invalidated",
  };

const DIRECTION_LABEL: Record<PatternShapeSignal["direction"], string> = {
  bullish: "偏多",
  bearish: "偏空",
};

function allSignals(detections: PatternShapeDetection[]): PatternShapeSignal[] {
  return detections.flatMap((detection) => detection.signals);
}

export function PatternHintsCard({
  detections,
}: {
  detections: PatternShapeDetection[];
}) {
  const signals = allSignals(detections);
  const anyLive = detections.some((detection) => detection.qualityStatus === "live");
  const allUnavailable = detections.length > 0 && !anyLive;

  return (
    <View style={styles.card} testID="pattern-hints-card">
      <Text style={styles.title}>形态提示</Text>
      {allUnavailable ? (
        <Text style={styles.empty} testID="pattern-hints-insufficient">
          完整K线数量不足，形态检测暂不可用。
        </Text>
      ) : signals.length === 0 ? (
        <Text style={styles.empty} testID="pattern-hints-empty">
          当前没有识别到形态。
        </Text>
      ) : (
        <View style={styles.list}>
          {signals.map((signal, index) => (
            <View
              key={`${signal.kind}-${signal.eventIndex}-${index}`}
              style={styles.item}
              testID={`pattern-hint-${index}`}>
              <View style={styles.itemHeader}>
                <Text style={styles.itemName}>{signal.name}</Text>
                <Text style={[styles.itemStatus, styles[STATUS_STYLE_KEY[signal.status]]]}>
                  {STATUS_LABEL[signal.status]}
                </Text>
              </View>
              <PlainReadingCard
                explanation={signal.reading.detail}
                headline={signal.reading.summary}
                numbers={{
                  value: `${STATUS_LABEL[signal.status]} · ${DIRECTION_LABEL[signal.direction]}`,
                  sampleSize: `第 ${signal.anchorIndex} 根K线`,
                  invalidation: signal.invalidation,
                  note: signal.reading.honesty,
                }}
                testID={`pattern-hint-reading-${index}`}
              />
            </View>
          ))}
        </View>
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
  title: { color: colors.ink, fontSize: 15, fontWeight: "900" },
  empty: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  list: { gap: spacing.sm },
  item: { gap: spacing.xs },
  itemHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.xs,
    justifyContent: "space-between",
  },
  itemName: { color: colors.ink, fontSize: 13, fontWeight: "800" },
  itemStatus: { fontSize: 12, fontWeight: "900" },
  confirmed: { color: colors.green },
  invalidated: { color: colors.red },
  forming: { color: colors.amber },
});
