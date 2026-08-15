import { StyleSheet, Text, View } from "react-native";

import { PlainReadingCard } from "@/components/ui/PlainReadingCard";
import type {
  PatternShapeDetection,
  PatternShapeKind,
  PatternShapeSignal,
} from "@/domain/models";
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
 *
 * A detector re-fires on every bar it recognises the same shape on, so a
 * fractal detector alone can carry dozens of historical instances by the
 * time a snapshot ships -- flooding this card with identical reading copy,
 * over and over, tells a short-term reader nothing they did not already
 * know from the first instance. Presentation folds each kind down to one
 * row for its most recent instance with a count chip for the rest
 * (`summarizeSignals` below); the decoded data itself stays complete --
 * `PriceChart`'s markers and any future history view still see every
 * instance, this card just stops repeating them.
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

/**
 * Rarer, structural multi-bar shapes lead; fractals -- the detector that
 * fires on almost every third bar by construction -- sort last, so the
 * shapes that actually matter to a short-term reader are not buried under
 * routine fractal noise. A kind absent from this snapshot's detections
 * simply produces no row; nothing pads the card out to a fixed size.
 */
const KIND_PRIORITY: PatternShapeKind[] = [
  "double_bottom",
  "double_top",
  "head_shoulders_top",
  "head_shoulders_bottom",
  "ma5_pullback",
  "fractal_top",
  "fractal_bottom",
];

function kindPriority(kind: PatternShapeKind): number {
  const index = KIND_PRIORITY.indexOf(kind);
  return index === -1 ? KIND_PRIORITY.length : index;
}

function allSignals(detections: PatternShapeDetection[]): PatternShapeSignal[] {
  return detections.flatMap((detection) => detection.signals);
}

type PatternHintRow = {
  kind: PatternShapeKind;
  /** The most recent instance of this kind -- whatever status it carries. */
  signal: PatternShapeSignal;
  /** How many instances of this kind this snapshot's history holds. */
  count: number;
};

/**
 * One row per kind present, holding only that kind's most recent instance.
 *
 * `eventIndex` is the bar index a signal's status became true at, in the
 * same completed-candle numbering every detector shares, so the highest
 * `eventIndex` within a kind's group is unambiguously its most recent
 * instance. That instance's own status is shown even when it is
 * forming/invalidated and an older same-kind instance happened to read
 * "confirmed" -- the most recent state is the true current state, not
 * whichever historical instance looks the most reassuring.
 */
function summarizeSignals(signals: PatternShapeSignal[]): PatternHintRow[] {
  const groups = new Map<PatternShapeKind, PatternShapeSignal[]>();
  for (const signal of signals) {
    const group = groups.get(signal.kind);
    if (group) group.push(signal);
    else groups.set(signal.kind, [signal]);
  }

  const rows: PatternHintRow[] = [];
  for (const [kind, group] of groups) {
    const mostRecent = group.reduce((latest, candidate) =>
      candidate.eventIndex > latest.eventIndex ? candidate : latest,
    );
    rows.push({ kind, signal: mostRecent, count: group.length });
  }

  return rows.sort((a, b) => kindPriority(a.kind) - kindPriority(b.kind));
}

/** "2026-07-25T15:54:00.000Z" -> "07-25"; served closedAt strings are always this shape. */
function monthDay(closedAt: string): string {
  return closedAt.slice(5, 10);
}

function anchorClosedAt(signal: PatternShapeSignal): string | null {
  return (
    signal.bars.find((bar) => bar.index === signal.anchorIndex)?.closedAt ??
    signal.bars.at(-1)?.closedAt ??
    null
  );
}

export function PatternHintsCard({
  detections,
}: {
  detections: PatternShapeDetection[];
}) {
  const signals = allSignals(detections);
  const anyLive = detections.some((detection) => detection.qualityStatus === "live");
  const allUnavailable = detections.length > 0 && !anyLive;
  const rows = summarizeSignals(signals);

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
          {rows.map(({ kind, signal, count }) => {
            const closedAt = anchorClosedAt(signal);
            return (
              <View key={kind} style={styles.item} testID={`pattern-hint-row-${kind}`}>
                <View style={styles.itemHeader}>
                  <Text style={styles.itemName}>{signal.name}</Text>
                  <Text style={[styles.itemStatus, styles[STATUS_STYLE_KEY[signal.status]]]}>
                    {STATUS_LABEL[signal.status]}
                  </Text>
                </View>
                <Text style={styles.itemMeta} testID={`pattern-hint-meta-${kind}`}>
                  {closedAt ? `最近一次 ${monthDay(closedAt)}` : "最近一次未知"}
                  {count > 1 ? ` · 共 ${count} 次` : ""}
                </Text>
                <PlainReadingCard
                  explanation={signal.reading.detail}
                  headline={signal.reading.summary}
                  numbers={{
                    value: `${STATUS_LABEL[signal.status]} · ${DIRECTION_LABEL[signal.direction]}`,
                    sampleSize: `第 ${signal.anchorIndex} 根K线`,
                    invalidation: signal.invalidation,
                    note: signal.reading.honesty,
                  }}
                  testID={`pattern-hint-reading-${kind}`}
                />
              </View>
            );
          })}
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
  itemMeta: { color: colors.muted, fontSize: 11, fontWeight: "700" },
  confirmed: { color: colors.green },
  invalidated: { color: colors.red },
  forming: { color: colors.amber },
});
