import { StyleSheet, Text, View } from "react-native";

import type { ConversationTurn } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

export function ConversationTurnCard({ turn }: { turn: ConversationTurn }) {
  if (turn.role === "user") {
    return (
      <View style={styles.userBubble}>
        <Text style={styles.userText}>{turn.text}</Text>
      </View>
    );
  }

  return (
    <View style={styles.assistantCard}>
      <View style={styles.assistantHeader}>
        <Text style={styles.assistantLabel}>ALPHA AGENT</Text>
        <Text style={styles.demo}>确定性演示回复</Text>
      </View>
      {turn.sections?.map((section, index) => (
        <View
          key={`${turn.id}-${section.title}`}
          style={[styles.section, index === 0 && styles.objective]}>
          <Text
            style={[styles.sectionTitle, index === 0 && styles.objectiveTitle]}
            testID="conversation-section-title">
            {section.title}
          </Text>
          <Text style={[styles.sectionBody, index === 0 && styles.objectiveBody]}>
            {section.body}
          </Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  userBubble: {
    alignSelf: "flex-end",
    backgroundColor: colors.blue,
    borderRadius: radius.lg,
    maxWidth: "86%",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  userText: { color: colors.card, fontSize: 11, fontWeight: "800", lineHeight: 16 },
  assistantCard: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    overflow: "hidden",
    padding: spacing.sm,
  },
  assistantHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: spacing.xs,
  },
  assistantLabel: { color: colors.blue, fontSize: 11, fontWeight: "900" },
  demo: { color: colors.amber, fontSize: 11, fontWeight: "900" },
  section: {
    backgroundColor: colors.backgroundRaised,
    borderRadius: radius.md,
    gap: 3,
    padding: spacing.sm,
  },
  objective: { backgroundColor: colors.navy, padding: spacing.md },
  sectionTitle: { color: colors.muted, fontSize: 11, fontWeight: "900" },
  objectiveTitle: { color: colors.blueBright },
  sectionBody: { color: colors.ink, fontSize: 11, lineHeight: 15 },
  objectiveBody: { color: colors.card, fontSize: 13, fontWeight: "900", lineHeight: 18 },
});
