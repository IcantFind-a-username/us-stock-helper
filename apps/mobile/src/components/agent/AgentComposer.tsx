import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing } from "@/theme/tokens";

const promptChips = [
  "为什么短线不追高？",
  "最强反证是什么？",
  "做空风险有哪些？",
] as const;

export function AgentComposer({ onSubmit }: { onSubmit(prompt: string): void }) {
  const [value, setValue] = useState("");

  const submit = (prompt = value) => {
    const normalized = prompt.trim();
    if (normalized === "") return;
    onSubmit(normalized);
    setValue("");
  };

  return (
    <View style={styles.wrap}>
      <View style={styles.chips}>
        {promptChips.map((prompt) => (
          <Pressable
            accessibilityLabel={prompt}
            accessibilityRole="button"
            key={prompt}
            onPress={() => submit(prompt)}
            style={({ pressed }) => [styles.chip, pressed && styles.pressed]}>
            <Text style={styles.chipText}>{prompt}</Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.composer}>
        <TextInput
          accessibilityLabel="向 Agent 提问"
          onChangeText={setValue}
          onSubmitEditing={() => submit()}
          placeholder="围绕证据、反证和风险提问"
          placeholderTextColor={colors.muted}
          returnKeyType="send"
          style={styles.input}
          value={value}
        />
        <Pressable
          accessibilityLabel="发送 Agent 问题"
          accessibilityRole="button"
          onPress={() => submit()}
          style={({ pressed }) => [styles.send, pressed && styles.pressed]}>
          <Text style={styles.sendText}>发送</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  chip: {
    alignItems: "center",
    backgroundColor: colors.blueSoft,
    borderRadius: radius.pill,
    justifyContent: "center",
    minHeight: 44,
    paddingHorizontal: spacing.md,
  },
  chipText: { color: colors.blue, fontSize: 9, fontWeight: "900" },
  composer: { alignItems: "center", flexDirection: "row", gap: spacing.sm },
  input: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    color: colors.ink,
    flex: 1,
    fontSize: 11,
    minHeight: 48,
    paddingHorizontal: spacing.md,
  },
  send: {
    alignItems: "center",
    backgroundColor: colors.navy,
    borderRadius: radius.md,
    justifyContent: "center",
    minHeight: 48,
    paddingHorizontal: spacing.md,
  },
  sendText: { color: colors.card, fontSize: 10, fontWeight: "900" },
  pressed: { opacity: 0.66 },
});
