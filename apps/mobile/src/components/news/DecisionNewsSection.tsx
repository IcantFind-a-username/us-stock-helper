import { useMemo } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import {
  compareByRecency,
  evidenceMarker,
  formatAbsoluteUtc,
  formatRelativeTime,
} from "@/domain/news";
import type { MarketDataErrorCategory } from "@/data/marketRepository";
import type { Decision, DecisionCitation } from "@/domain/models";
import { useNow } from "@/hooks/use-now";
import { describeMarketError } from "@/i18n/marketErrorCopy";
import { radius, spacing } from "@/theme/tokens";

import { DecisionInterpretationCard } from "./DecisionInterpretationCard";
import { useNewsPalette } from "./newsPalette";

/**
 * The news surface the deployed backend can actually fill.
 *
 * It lives on the stock page, and it reads from the decision rather than from a
 * news service of its own, because both of those follow from what the server
 * exposes. `/decision` is the only route that carries reports at all — it
 * answers per symbol and returns the evidence its conclusion stood on — so
 * there is no symbol-free feed a standalone tab could have shown.
 *
 * What it deliberately does not render is the point of the file. The full news
 * surface prints a claim status and a per-source reliability; a decision
 * citation carries neither, so this section prints neither and says so, rather
 * than dressing an unrated link up as a rated one.
 */

type DecisionNewsSectionProps = {
  symbol: string;
  /** null while the analysis request is unfinished or has failed. */
  decision: Decision | null;
  /** Set only when the request failed, which is a different fact from "no news". */
  errorCategory: MarketDataErrorCategory | null;
};

function absolute(value: string) {
  return formatAbsoluteUtc(value) ?? "时间不可用";
}

export function DecisionNewsSection({
  symbol,
  decision,
  errorCategory,
}: DecisionNewsSectionProps) {
  const palette = useNewsPalette();
  const now = useNow();
  const citations = useMemo(
    () => [...(decision?.citations ?? [])].sort(compareByRecency),
    [decision],
  );

  return (
    <View style={styles.section} testID="decision-news">
      <Text style={[styles.title, { color: palette.ink }]}>
        {`新闻与解读 · ${symbol}`}
      </Text>
      {decision ? (
        <Text
          style={[styles.asOf, { color: palette.muted }]}
          testID="decision-news-asof">
          {`快照截止 ${absolute(decision.decisionCutoff)}`}
        </Text>
      ) : null}

      <View
        style={[
          styles.card,
          { backgroundColor: palette.surface, borderColor: palette.line },
        ]}
        testID="decision-news-feed">
        <Text style={[styles.cardTitle, { color: palette.ink }]}>原始报道</Text>

        {decision === null ? (
          errorCategory === null ? (
            <View
              style={[styles.notice, { backgroundColor: palette.surfaceInset }]}
              testID="decision-news-loading">
              <Text style={[styles.noticeTitle, { color: palette.ink }]}>
                正在读取新闻证据…
              </Text>
            </View>
          ) : (
            <View
              style={[styles.notice, { backgroundColor: palette.noticeSurface }]}
              testID="decision-news-unavailable">
              <Text style={[styles.noticeTitle, { color: palette.ink }]}>
                {`新闻证据不可用 · ${describeMarketError(errorCategory).label}`}
              </Text>
              <Text style={[styles.noticeBody, { color: palette.muted }]}>
                {/* A failed request tells us nothing about the market, so it
                    must never be shown as a quiet news day. */}
                这是取数失败，不是「今天没有消息」。
              </Text>
              <Text style={[styles.noticeBody, { color: palette.muted }]}>
                {describeMarketError(errorCategory).body}
              </Text>
            </View>
          )
        ) : decision.status === "unavailable" ? (
          <View
            style={[styles.notice, { backgroundColor: palette.noticeSurface }]}
            testID="decision-news-not-connected">
            <Text style={[styles.noticeTitle, { color: palette.ink }]}>
              分析未能给出结论，因此没有引用报道
            </Text>
            {decision.notes.map((note) => (
              <Text
                key={note}
                style={[styles.noticeBody, { color: palette.muted }]}>
                {`· ${note}`}
              </Text>
            ))}
          </View>
        ) : citations.length === 0 ? (
          <View
            style={[styles.notice, { backgroundColor: palette.surfaceInset }]}
            testID="decision-news-empty">
            <Text style={[styles.noticeTitle, { color: palette.ink }]}>
              分析已接入 · 该时段没有可核实的报道
            </Text>
            <Text style={[styles.noticeBody, { color: palette.muted }]}>
              没有报道与没有接入是两件事，这里说的是前者。
            </Text>
          </View>
        ) : (
          citations.map((item, index) => (
            <CitationRow
              citation={item}
              key={item.id}
              marker={evidenceMarker(index)}
              now={now}
              palette={palette}
            />
          ))
        )}

        {citations.length > 0 ? (
          <Text
            style={[styles.limits, { color: palette.notice }]}
            testID="decision-news-limits">
            引用来自分析结论，未提供来源可靠度与消息证实状态；这些字段分析接口不返回，不做推测。
          </Text>
        ) : null}
      </View>

      <DecisionInterpretationCard decision={decision} palette={palette} />
    </View>
  );
}

function CitationRow({
  citation,
  marker,
  now,
  palette,
}: {
  citation: DecisionCitation;
  marker: string;
  now: Date;
  palette: ReturnType<typeof useNewsPalette>;
}) {
  const relative = formatRelativeTime(citation.availableAt, now);
  return (
    <View
      style={[
        styles.row,
        { backgroundColor: palette.surfaceInset, borderColor: palette.line },
      ]}
      testID={`decision-news-row-${citation.id}`}>
      <View style={styles.rowHeader}>
        <Text
          style={[
            styles.marker,
            { borderColor: palette.accent, color: palette.accent },
          ]}
          testID={`decision-news-marker-${citation.id}`}>
          {marker}
        </Text>
        <View style={styles.spacer} />
        <Text style={[styles.relative, { color: palette.muted }]}>
          {relative ?? "相对时间不可用"}
        </Text>
      </View>

      <Text style={[styles.headline, { color: palette.ink }]}>
        {citation.headline}
      </Text>
      <Text style={[styles.absolute, { color: palette.muted }]}>
        {`发布 ${absolute(citation.availableAt)}`}
      </Text>

      <Pressable
        accessibilityHint="在浏览器中打开原始报道"
        accessibilityLabel={`打开来源：${citation.publisher}`}
        accessibilityRole="link"
        onPress={() => {
          void Linking.openURL(citation.url);
        }}
        style={({ pressed }) => [styles.source, pressed && styles.pressed]}>
        <Text style={[styles.sourceText, { color: palette.accent }]}>
          {citation.publisher}
        </Text>
        <Text style={[styles.sourceArrow, { color: palette.muted }]}>↗</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.sm },
  title: { fontSize: 15, fontWeight: "900" },
  asOf: { fontSize: 12, fontVariant: ["tabular-nums"], fontWeight: "600" },
  card: {
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.md,
  },
  cardTitle: { fontSize: 12, fontWeight: "900", letterSpacing: 0.4 },
  notice: { borderRadius: radius.md, gap: spacing.xxs, padding: spacing.sm },
  noticeTitle: { fontSize: 12, fontWeight: "800", lineHeight: 17 },
  noticeBody: { fontSize: 12, lineHeight: 18 },
  limits: { fontSize: 12, fontWeight: "700", lineHeight: 18 },
  row: {
    borderRadius: radius.md,
    borderWidth: 1,
    gap: spacing.xs,
    padding: spacing.sm,
  },
  rowHeader: { alignItems: "center", flexDirection: "row", gap: spacing.xs },
  marker: {
    borderRadius: radius.pill,
    borderWidth: 1,
    fontSize: 12,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  spacer: { flex: 1 },
  relative: { fontSize: 12, fontWeight: "800" },
  headline: { fontSize: 14, fontWeight: "800", lineHeight: 19 },
  absolute: { fontSize: 12, fontVariant: ["tabular-nums"], lineHeight: 18 },
  source: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.xs,
    justifyContent: "space-between",
    minHeight: 44,
  },
  sourceText: { flexShrink: 1, fontSize: 12, fontWeight: "700" },
  sourceArrow: { fontSize: 14, fontWeight: "800" },
  pressed: { opacity: 0.68 },
});
