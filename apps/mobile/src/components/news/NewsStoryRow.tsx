import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import {
  formatAbsoluteUtc,
  formatRelativeTime,
  type NewsClaimStatus,
  type NewsStory,
} from "@/domain/news";
import { radius, spacing } from "@/theme/tokens";

import type { NewsPalette } from "./newsPalette";

const claimStatusLabels: Record<NewsClaimStatus, string> = {
  verified: "已证实",
  reported: "有报道",
  rumor: "传闻",
};

type NewsStoryRowProps = {
  story: NewsStory;
  marker: string;
  cited: boolean;
  now: Date;
  palette: NewsPalette;
};

function absolute(value: string) {
  return formatAbsoluteUtc(value) ?? "时间不可用";
}

export function NewsStoryRow({
  story,
  marker,
  cited,
  now,
  palette,
}: NewsStoryRowProps) {
  const relative = formatRelativeTime(story.availableAt, now);
  const chip = palette.claimStatus[story.claimStatus];
  return (
    <View
      style={[
        styles.row,
        {
          backgroundColor: palette.surfaceInset,
          borderColor: cited ? palette.accent : palette.line,
        },
      ]}
      testID={`news-story-row-${story.id}`}>
      <View style={styles.header}>
        <Text
          style={[styles.marker, { borderColor: palette.accent, color: palette.accent }]}
          testID={`news-story-marker-${story.id}`}>
          {marker}
        </Text>
        <Text
          style={[styles.status, { backgroundColor: chip.background, color: chip.text }]}>
          {claimStatusLabels[story.claimStatus]}
        </Text>
        {story.sourceCount > 1 ? (
          <Text
            style={[
              styles.sourceCount,
              { borderColor: palette.line, color: palette.ink },
            ]}
            testID={`news-story-source-count-${story.id}`}>
            {`${story.sourceCount} 家来源`}
          </Text>
        ) : null}
        <View style={styles.spacer} />
        <Text
          style={[styles.relative, { color: palette.muted }]}
          testID={`news-story-relative-${story.id}`}>
          {/* A story whose elapsed time cannot be computed says so; the
              absolute timestamp below still lets the reader judge it. */}
          {relative ?? "相对时间不可用"}
        </Text>
      </View>

      <Text
        style={[styles.headline, { color: palette.ink }]}
        testID={`news-story-headline-${story.id}`}>
        {story.headline}
      </Text>

      {cited ? (
        <Text
          style={[styles.cited, { color: palette.accent }]}
          testID={`news-story-cited-${story.id}`}>
          {`解读引用 ${marker}`}
        </Text>
      ) : null}

      <Text
        style={[styles.absolute, { color: palette.muted }]}
        testID={`news-story-absolute-${story.id}`}>
        {`发布 ${absolute(story.availableAt)} · 接收 ${absolute(story.receivedAt)}`}
      </Text>

      {story.sources.map((source) => (
        <Pressable
          accessibilityHint="在浏览器中打开原始报道"
          accessibilityLabel={`打开来源：${source.publisher}`}
          accessibilityRole="link"
          key={source.url}
          onPress={() => {
            void Linking.openURL(source.url);
          }}
          style={({ pressed }) => [styles.source, pressed && styles.pressed]}>
          <Text style={[styles.sourceText, { color: palette.accent }]}>
            {`${source.publisher} · 可靠度 ${(source.reliability * 100).toFixed(0)}%`}
          </Text>
          <Text style={[styles.sourceArrow, { color: palette.muted }]}>↗</Text>
        </Pressable>
      ))}

      {story.omittedSourceCount > 0 ? (
        <Text
          style={[styles.omitted, { color: palette.notice }]}
          testID={`news-story-omitted-${story.id}`}>
          {`${story.omittedSourceCount} 条无原始链接的来源未展示`}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    borderRadius: radius.md,
    borderWidth: 1,
    gap: spacing.xs,
    padding: spacing.sm,
  },
  header: { alignItems: "center", flexDirection: "row", gap: spacing.xs },
  marker: {
    borderRadius: radius.pill,
    borderWidth: 1,
    fontSize: 11,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  status: {
    borderRadius: radius.pill,
    fontSize: 11,
    fontWeight: "800",
    overflow: "hidden",
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  sourceCount: {
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    fontSize: 11,
    fontWeight: "800",
    overflow: "hidden",
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  spacer: { flex: 1 },
  relative: { fontSize: 11, fontWeight: "800" },
  headline: { fontSize: 14, fontWeight: "800", lineHeight: 19 },
  cited: { fontSize: 11, fontWeight: "800" },
  absolute: { fontSize: 11, fontVariant: ["tabular-nums"], lineHeight: 14 },
  source: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.xs,
    justifyContent: "space-between",
    minHeight: 44,
  },
  sourceText: { flexShrink: 1, fontSize: 12, fontWeight: "700" },
  sourceArrow: { fontSize: 14, fontWeight: "800" },
  omitted: { fontSize: 11, fontWeight: "700", lineHeight: 14 },
  pressed: { opacity: 0.68 },
});
