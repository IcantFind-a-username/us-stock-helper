import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { Screen } from "@/components/ui/Screen";
import { describePairingFailure } from "@/domain/pairing";
import { useDeviceSession } from "@/state/DeviceSessionProvider";
import { colors, radius, spacing } from "@/theme/tokens";

const statusCopy = {
  checking: { label: "正在检查配对状态", tone: colors.muted },
  unpaired: { label: "未配对", tone: colors.red },
  pairing: { label: "配对中", tone: colors.amber },
  paired: { label: "已配对", tone: colors.green },
  revoked: { label: "授权已撤销", tone: colors.red },
} as const;

/**
 * The one screen that is allowed to be empty of market content, and the reason
 * it says so out loud. An unpaired device has no data to show and must not look
 * like a device whose data merely failed to load.
 */
export function PairDeviceScreen() {
  const { session, pair } = useDeviceSession();
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);
  const pending = session.status === "pairing";
  const status = statusCopy[session.status];
  const failureCopy = session.failure
    ? describePairingFailure({
        reason: session.failure.reason,
        retryAfterSeconds: session.failure.retryAfterSeconds,
      })
    : null;

  const submit = () => {
    if (pending) return;
    if (code.trim() === "") {
      setCodeError("请输入配对码");
      return;
    }
    setCodeError(null);
    void pair(code);
  };

  return (
    <Screen hideGlobalHeader style={styles.screen}>
      <View>
        <Text style={styles.eyebrow}>设备绑定 · 只读分析</Text>
        <Text style={styles.title}>连接你的服务器</Text>
      </View>

      <View style={styles.statusCard}>
        <Text style={[styles.statusLabel, { color: status.tone }]}>
          {status.label}
        </Text>
        <Text style={styles.statusBody}>
          未配对前不会显示任何行情或结论。这里宁可空着，也不会拿演示数据冒充实盘判断。
        </Text>
      </View>

      {session.status === "paired" ? (
        <View style={styles.pairedCard}>
          <Text style={styles.pairedTitle}>这台设备已经绑定服务器</Text>
          <Text style={styles.pairedBody}>
            {session.expiresAt === null
              ? "服务器没有说明令牌有效期。"
              : `令牌有效期至 ${session.expiresAt}。`}
          </Text>
        </View>
      ) : (
        <View style={styles.form}>
          <Text style={styles.fieldLabel}>配对码</Text>
          <TextInput
            accessibilityLabel="配对码"
            autoCapitalize="characters"
            autoCorrect={false}
            editable={!pending}
            onChangeText={setCode}
            placeholder="在服务器上生成后输入"
            placeholderTextColor={colors.muted}
            style={styles.input}
            value={code}
          />
          {codeError === null ? null : (
            <Text style={styles.fieldError}>{codeError}</Text>
          )}
          <Pressable
            accessibilityLabel="完成配对"
            accessibilityRole="button"
            accessibilityState={{ disabled: pending }}
            disabled={pending}
            onPress={submit}
            style={({ pressed }) => [
              styles.submit,
              pending && styles.submitPending,
              pressed && styles.pressed,
            ]}>
            <Text style={styles.submitText}>完成配对</Text>
          </Pressable>
          <Text style={styles.hint}>
            配对码在服务器终端上生成，只能使用一次，且很快过期。
          </Text>
        </View>
      )}

      {failureCopy === null ? null : (
        <View style={styles.failureCard} testID="pairing-failure">
          <Text style={styles.failureTitle}>{failureCopy.title}</Text>
          <Text style={styles.failureBody}>{failureCopy.body}</Text>
        </View>
      )}

      <View style={styles.boundary}>
        <Text style={styles.boundaryTitle}>这次配对能做什么</Text>
        <Text style={styles.boundaryBody}>
          令牌只用于读取行情与分析结论，存放在系统钥匙串，不会同步到 iCloud。应用不连接券商、不下单、也不保存任何账户凭据。
        </Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { gap: spacing.md, paddingTop: spacing.lg },
  eyebrow: { color: colors.muted, fontSize: 11, fontWeight: "800" },
  title: { color: colors.ink, fontSize: 23, fontWeight: "900", marginTop: spacing.xxs },
  statusCard: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    padding: spacing.md,
  },
  statusLabel: { fontSize: 15, fontWeight: "900" },
  statusBody: { color: colors.muted, fontSize: 11, lineHeight: 15 },
  form: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.md,
  },
  fieldLabel: { color: colors.muted, fontSize: 11, fontWeight: "900" },
  input: {
    backgroundColor: colors.backgroundRaised,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    color: colors.ink,
    fontSize: 14,
    fontWeight: "800",
    minHeight: 44,
    paddingHorizontal: spacing.md,
  },
  fieldError: { color: colors.red, fontSize: 11, fontWeight: "800" },
  submit: {
    alignItems: "center",
    backgroundColor: colors.blue,
    borderRadius: radius.pill,
    justifyContent: "center",
    minHeight: 44,
  },
  submitPending: { backgroundColor: colors.muted },
  submitText: { color: colors.card, fontSize: 12, fontWeight: "900" },
  hint: { color: colors.muted, fontSize: 11, lineHeight: 14 },
  pairedCard: {
    backgroundColor: colors.greenSoft,
    borderRadius: radius.lg,
    gap: spacing.xs,
    padding: spacing.md,
  },
  pairedTitle: { color: colors.ink, fontSize: 12, fontWeight: "900" },
  pairedBody: { color: colors.muted, fontSize: 11, lineHeight: 15 },
  failureCard: {
    backgroundColor: colors.redSoft,
    borderRadius: radius.lg,
    gap: spacing.xs,
    padding: spacing.md,
  },
  failureTitle: { color: colors.red, fontSize: 13, fontWeight: "900" },
  failureBody: { color: colors.ink, fontSize: 11, lineHeight: 15 },
  boundary: {
    backgroundColor: colors.blueSoft,
    borderRadius: radius.md,
    gap: spacing.xs,
    padding: spacing.md,
  },
  boundaryTitle: { color: colors.blue, fontSize: 11, fontWeight: "900" },
  boundaryBody: { color: colors.ink, fontSize: 11, lineHeight: 14 },
  pressed: { opacity: 0.66 },
});
