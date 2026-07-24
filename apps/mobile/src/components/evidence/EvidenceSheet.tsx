import { StyleSheet, Text, View } from "react-native";

import type { Citation } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

import { CitationRow } from "./CitationRow";

type EvidenceSheetProps = {
  title: string;
  citations: Citation[];
};

export function EvidenceSheet({ title, citations }: EvidenceSheetProps) {
  return (
    <View accessibilityLabel={title} style={styles.sheet}>
      <Text style={styles.marker}>演示</Text>
      <Text style={styles.title}>{title}</Text>
      {citations.length ? (
        citations.map((citation) => <CitationRow citation={citation} key={citation.id} />)
      ) : (
        <Text style={styles.empty}>暂无可用证据</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { backgroundColor: colors.card, borderRadius: radius.lg, padding: spacing.lg },
  marker: { color: colors.amber, fontSize: 11, fontWeight: "800" },
  title: { color: colors.ink, fontSize: 18, fontWeight: "800" },
  empty: { color: colors.muted, fontSize: 14, paddingVertical: spacing.xl },
});
