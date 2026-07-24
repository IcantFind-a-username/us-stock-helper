import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import type { Citation, EvidenceKind } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

const evidenceLabels: Record<EvidenceKind, string> = {
  fact: "事实",
  inference: "推断",
  scenario: "情景",
  rumor: "传闻",
};

type CitationRowProps = {
  citation: Citation;
};

function formatPublishedAt(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

export function CitationRow({ citation }: CitationRowProps) {
  return (
    <Pressable
      accessibilityHint="在浏览器中打开来源"
      accessibilityLabel={`打开来源：${citation.title}`}
      accessibilityRole="link"
      onPress={() => Linking.openURL(citation.url)}
      style={styles.row}>
      <View style={styles.copy}>
        <View style={styles.meta}>
          <Text style={[styles.kind, citation.kind === "rumor" ? styles.rumor : styles.fact]}>{evidenceLabels[citation.kind]}</Text>
          <Text style={styles.publisher}>{citation.publisher}</Text>
        </View>
        <Text numberOfLines={2} style={styles.title}>{citation.title}</Text>
        <Text style={styles.time}>发布时间：{formatPublishedAt(citation.publishedAt)}</Text>
      </View>
      <Text accessibilityElementsHidden style={styles.arrow}>›</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { alignItems: "center", borderBottomColor: colors.line, borderBottomWidth: StyleSheet.hairlineWidth, flexDirection: "row", gap: spacing.sm, paddingVertical: spacing.md },
  copy: { flex: 1 },
  meta: { alignItems: "center", flexDirection: "row", gap: spacing.sm },
  kind: { borderRadius: radius.pill, fontSize: 11, fontWeight: "700", overflow: "hidden", paddingHorizontal: spacing.sm, paddingVertical: 2 },
  fact: { backgroundColor: colors.blueSoft, color: colors.blue },
  rumor: { backgroundColor: colors.amberSoft, color: colors.amber },
  publisher: { color: colors.muted, fontSize: 12 },
  title: { color: colors.ink, fontSize: 14, fontWeight: "600", marginTop: spacing.xs },
  time: { color: colors.muted, fontSize: 12, marginTop: spacing.xs },
  arrow: { color: colors.muted, fontSize: 28 },
});
