import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { CitationRow } from "@/components/evidence/CitationRow";
import type { Citation } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

export type DetailSection = { label: string; body: string };

type DashboardDetailSheetProps = {
  visible: boolean;
  title: string;
  sections: DetailSection[];
  citations: Citation[];
  onClose(): void;
};

export function DashboardDetailSheet({
  visible,
  title,
  sections,
  citations,
  onClose,
}: DashboardDetailSheetProps) {
  if (!visible) return null;

  return (
    <Modal
      animationType="slide"
      onRequestClose={onClose}
      presentationStyle="pageSheet"
      visible>
      <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
        <View style={styles.header}>
          <Text style={styles.title}>{title}</Text>
          <Pressable
            accessibilityLabel={`关闭${title}`}
            accessibilityRole="button"
            onPress={onClose}
            style={styles.close}>
            <Text style={styles.closeText}>完成</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={styles.content}>
          <Text style={styles.demo}>演示数据 · 非实时行情</Text>
          {sections.map((section) => (
            <View key={section.label} style={styles.section}>
              <Text style={styles.label}>{section.label}</Text>
              <Text style={styles.body}>{section.body}</Text>
            </View>
          ))}
          <Text style={styles.citationHeading}>引用</Text>
          {citations.length ? (
            citations.map((citation) => <CitationRow citation={citation} key={citation.id} />)
          ) : (
            <Text style={styles.empty}>暂无可用引用</Text>
          )}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.backgroundRaised, flex: 1 },
  header: {
    alignItems: "center",
    borderBottomColor: colors.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
  },
  title: { color: colors.ink, flex: 1, fontSize: 18, fontWeight: "800" },
  close: { alignItems: "center", justifyContent: "center", minHeight: 44, paddingLeft: spacing.lg },
  closeText: { color: colors.blue, fontSize: 15, fontWeight: "800" },
  content: { gap: spacing.md, padding: spacing.lg, paddingBottom: spacing.xl },
  demo: { alignSelf: "flex-start", color: colors.amber, fontSize: 11, fontWeight: "800" },
  section: { backgroundColor: colors.card, borderRadius: radius.md, padding: spacing.md },
  label: { color: colors.ink, fontSize: 13, fontWeight: "800" },
  body: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: spacing.xs },
  citationHeading: { color: colors.ink, fontSize: 15, fontWeight: "800", marginTop: spacing.sm },
  empty: { color: colors.muted, fontSize: 13 },
});
