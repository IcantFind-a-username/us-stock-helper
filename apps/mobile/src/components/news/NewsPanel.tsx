import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";

import {
  evidenceMarker,
  formatAbsoluteUtc,
  isEvidenceExpired,
  orderStoriesByRecency,
  type NewsBriefing,
} from "@/domain/news";
import { useNow } from "@/hooks/use-now";
import { spacing } from "@/theme/tokens";

import { NewsFeed } from "./NewsFeed";
import { NewsInterpretationCard } from "./NewsInterpretationCard";
import { useNewsPalette } from "./newsPalette";

/**
 * The news surface: what was reported, and what the model made of it.
 *
 * Ordering and numbering live here rather than in either section, because the
 * numbers are the link between them — a conclusion labelled ① and a report row
 * labelled ② would be worse than no labels at all.
 */
export function NewsPanel({ briefing }: { briefing: NewsBriefing }) {
  const palette = useNewsPalette();
  const now = useNow();
  const { feed, interpretation } = briefing;

  const stories = useMemo(
    () => (feed.status === "connected" ? orderStoriesByRecency(feed.stories) : []),
    [feed],
  );
  const markers = useMemo(
    () =>
      new Map(stories.map((story, index) => [story.id, evidenceMarker(index)])),
    [stories],
  );
  const expired = isEvidenceExpired(interpretation, now);
  const citedStoryIds = useMemo(
    () =>
      new Set(
        interpretation.status === "available" && !expired
          ? interpretation.claims.flatMap((claim) => claim.evidenceIds)
          : [],
      ),
    [expired, interpretation],
  );

  return (
    <View style={styles.panel} testID="news-panel">
      <Text style={[styles.title, { color: palette.ink }]}>
        {`新闻与解读 · ${briefing.symbol}`}
      </Text>
      <Text
        style={[styles.asOf, { color: palette.muted }]}
        testID="news-panel-asof">
        {`快照截止 ${formatAbsoluteUtc(briefing.asOf) ?? "时间不可用"}`}
      </Text>
      <NewsFeed
        citedStoryIds={citedStoryIds}
        feed={feed}
        markers={markers}
        now={now}
        palette={palette}
        stories={stories}
      />
      <NewsInterpretationCard
        interpretation={interpretation}
        markers={markers}
        now={now}
        palette={palette}
        stories={stories}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { gap: spacing.sm },
  title: { fontSize: 15, fontWeight: "900" },
  asOf: { fontSize: 10, fontVariant: ["tabular-nums"], fontWeight: "600" },
});
