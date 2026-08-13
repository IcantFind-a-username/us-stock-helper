import { StyleSheet, Text, View } from "react-native";

import {
  formatAbsoluteUtc,
  formatRelativeTime,
  isEvidenceExpired,
  type NewsInterpretationSection,
  type NewsStory,
} from "@/domain/news";
import { radius, spacing } from "@/theme/tokens";

import type { NewsPalette } from "./newsPalette";

type NewsInterpretationCardProps = {
  interpretation: NewsInterpretationSection;
  /** Ordered exactly as the feed shows them, so citation numbers line up. */
  stories: NewsStory[];
  markers: Map<string, string>;
  now: Date;
  palette: NewsPalette;
};

function absolute(value: string) {
  return formatAbsoluteUtc(value) ?? "时间不可用";
}

export function NewsInterpretationCard({
  interpretation,
  stories,
  markers,
  now,
  palette,
}: NewsInterpretationCardProps) {
  const expired = isEvidenceExpired(interpretation, now);
  const citations = (evidenceIds: string[]) =>
    stories
      .filter((story) => evidenceIds.includes(story.id))
      .map((story) => ({
        id: story.id,
        marker: markers.get(story.id) ?? "",
        publisher: story.sources[0]?.publisher ?? "",
      }));

  // Expired evidence takes everything that described the conclusions with it:
  // a model line or a withheld count left behind reads as an interpretation
  // that still stands.
  const showsConclusions = interpretation.status === "available" && !expired;
  const claims =
    interpretation.status === "available"
      ? interpretation.claims.map((claim) => ({
          claim,
          citations: citations(claim.evidenceIds),
        }))
      : [];
  // A conclusion whose citations cannot all be resolved to a visible row is
  // not traceable on this screen, whatever the payload said.
  const traceable = claims.filter(
    ({ claim, citations: resolved }) =>
      resolved.length === claim.evidenceIds.length,
  );
  const withheld = showsConclusions
    ? interpretation.withheldClaimCount + (claims.length - traceable.length)
    : 0;

  return (
    <View
      style={[
        styles.card,
        { backgroundColor: palette.surface, borderColor: palette.line },
      ]}
      testID="news-interpretation">
      <Text style={[styles.title, { color: palette.ink }]}>模型解读</Text>

      {interpretation.status === "unavailable" ? (
        <View
          style={[styles.notice, { backgroundColor: palette.noticeSurface }]}
          testID="news-interpretation-unavailable">
          <Text style={[styles.noticeTitle, { color: palette.ink }]}>
            解读暂不可用
          </Text>
          <Text style={[styles.noticeBody, { color: palette.muted }]}>
            {interpretation.reason}
          </Text>
          <Text style={[styles.noticeBody, { color: palette.muted }]}>
            上面的原始报道仍然可读，不会用演示结论替代解读。
          </Text>
        </View>
      ) : expired ? (
        <View
          style={[styles.notice, { backgroundColor: palette.noticeSurface }]}
          testID="news-interpretation-expired">
          <Text style={[styles.noticeTitle, { color: palette.ink }]}>
            证据已过期
          </Text>
          <Text style={[styles.noticeBody, { color: palette.muted }]}>
            {`证据有效期至 ${absolute(interpretation.evidenceValidUntil)}（${
              formatRelativeTime(interpretation.evidenceValidUntil, now) ??
              "时间不可用"
            }）`}
          </Text>
          <Text style={[styles.noticeBody, { color: palette.muted }]}>
            {`结论生成于 ${absolute(interpretation.generatedAt)}，已超出其证据窗口，暂不展示。`}
          </Text>
        </View>
      ) : traceable.length === 0 ? (
        <View
          style={[styles.notice, { backgroundColor: palette.surfaceInset }]}
          testID="news-interpretation-empty">
          <Text style={[styles.noticeTitle, { color: palette.ink }]}>
            暂无可溯源的结论
          </Text>
          <Text style={[styles.noticeBody, { color: palette.muted }]}>
            解读服务在线，但没有一条结论能指回可打开的证据。
          </Text>
        </View>
      ) : (
        traceable.map(({ claim, citations: resolved }) => (
          <View
            key={claim.id}
            style={[styles.claim, { borderLeftColor: palette.accent }]}
            testID={`news-claim-${claim.id}`}>
            <Text style={[styles.claimText, { color: palette.ink }]}>
              {claim.text}
            </Text>
            <View style={styles.chips}>
              {resolved.map((citation) => (
                <Text
                  key={citation.id}
                  style={[
                    styles.chip,
                    {
                      backgroundColor: palette.surfaceInset,
                      borderColor: palette.accent,
                      color: palette.accent,
                    },
                  ]}
                  testID={`news-claim-citation-${claim.id}-${citation.id}`}>
                  {`${citation.marker} ${citation.publisher}`}
                </Text>
              ))}
            </View>
          </View>
        ))
      )}

      {showsConclusions ? (
        <Text
          style={[styles.meta, { color: palette.muted }]}
          testID="news-interpretation-meta">
          {`模型 ${interpretation.model} · 生成于 ${absolute(
            interpretation.generatedAt,
          )} · 证据有效期至 ${absolute(interpretation.evidenceValidUntil)}`}
        </Text>
      ) : null}

      {withheld > 0 ? (
        <Text
          style={[styles.withheld, { color: palette.notice }]}
          testID="news-interpretation-withheld">
          {`${withheld} 条结论因证据无法溯源未展示`}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.md,
  },
  title: { fontSize: 12, fontWeight: "900", letterSpacing: 0.4 },
  notice: { borderRadius: radius.md, gap: spacing.xxs, padding: spacing.sm },
  noticeTitle: { fontSize: 12, fontWeight: "800", lineHeight: 17 },
  noticeBody: { fontSize: 10, lineHeight: 15 },
  claim: { borderLeftWidth: 2, gap: spacing.xs, paddingLeft: spacing.sm },
  claimText: { fontSize: 13, fontWeight: "700", lineHeight: 18 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  chip: {
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    fontSize: 10,
    fontWeight: "800",
    overflow: "hidden",
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  meta: { fontSize: 10, fontVariant: ["tabular-nums"], lineHeight: 14 },
  withheld: { fontSize: 10, fontWeight: "700", lineHeight: 14 },
});
