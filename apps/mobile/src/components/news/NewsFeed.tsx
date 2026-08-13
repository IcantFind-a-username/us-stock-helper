import { StyleSheet, Text, View } from "react-native";

import type { NewsFeedSection, NewsStory } from "@/domain/news";
import { radius, spacing } from "@/theme/tokens";

import { NewsStoryRow } from "./NewsStoryRow";
import type { NewsPalette } from "./newsPalette";

type NewsFeedProps = {
  feed: NewsFeedSection;
  /** Already ordered and numbered by the panel, so both sections agree. */
  stories: NewsStory[];
  markers: Map<string, string>;
  citedStoryIds: Set<string>;
  now: Date;
  palette: NewsPalette;
};

export function NewsFeed({
  feed,
  stories,
  markers,
  citedStoryIds,
  now,
  palette,
}: NewsFeedProps) {
  return (
    <View
      style={[
        styles.card,
        { backgroundColor: palette.surface, borderColor: palette.line },
      ]}
      testID="news-feed">
      <Text style={[styles.title, { color: palette.ink }]}>原始报道</Text>

      {feed.status === "not-connected" ? (
        <View
          style={[styles.notice, { backgroundColor: palette.noticeSurface }]}
          testID="news-feed-not-connected">
          <Text style={[styles.noticeTitle, { color: palette.ink }]}>
            新闻源尚未接入
          </Text>
          <Text style={[styles.noticeBody, { color: palette.muted }]}>
            {feed.reason}
          </Text>
          <Text style={[styles.noticeBody, { color: palette.muted }]}>
            接入前这里不会填充演示报道。
          </Text>
        </View>
      ) : stories.length === 0 ? (
        <View
          style={[styles.notice, { backgroundColor: palette.surfaceInset }]}
          testID="news-feed-empty">
          <Text style={[styles.noticeTitle, { color: palette.ink }]}>
            新闻源已接入 · 该时段没有可核实的报道
          </Text>
          <Text style={[styles.noticeBody, { color: palette.muted }]}>
            没有报道与没有接入是两件事，这里说的是前者。
          </Text>
        </View>
      ) : (
        stories.map((story) => (
          <NewsStoryRow
            cited={citedStoryIds.has(story.id)}
            key={story.id}
            marker={markers.get(story.id) ?? ""}
            now={now}
            palette={palette}
            story={story}
          />
        ))
      )}

      {feed.status === "connected" && feed.hiddenStoryCount > 0 ? (
        <Text
          style={[styles.hidden, { color: palette.notice }]}
          testID="news-feed-hidden">
          {`${feed.hiddenStoryCount} 条无原始链接的报道未展示 · 无法核实的信息不予呈现`}
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
  hidden: { fontSize: 10, fontWeight: "700", lineHeight: 14 },
});
