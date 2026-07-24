import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { JournalEntry, PlanSide } from "@/domain/models";
import { validateJournalDraft, type JournalDraftErrors } from "@/domain/journal";
import { colors, radius, spacing } from "@/theme/tokens";

export type JournalEntryValue = Pick<
  JournalEntry,
  "symbol" | "side" | "quantity" | "executionPrice" | "pnl" | "pnlState" | "decision" | "notes"
>;

type JournalEntryFormProps = {
  onCancel(): void;
  onSave(value: JournalEntryValue): void;
};

export function JournalEntryForm({ onCancel, onSave }: JournalEntryFormProps) {
  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<PlanSide>("long");
  const [quantity, setQuantity] = useState("");
  const [executionPrice, setExecutionPrice] = useState("");
  const [pnl, setPnl] = useState("");
  const [pnlState, setPnlState] = useState<JournalEntry["pnlState"]>("realized");
  const [decision, setDecision] = useState<JournalEntry["decision"]>("followed");
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<JournalDraftErrors>({});

  const submit = () => {
    const nextErrors = validateJournalDraft({ symbol, quantity, executionPrice, pnl });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    onSave({
      symbol: symbol.trim().toUpperCase(),
      side,
      quantity: Number(quantity),
      executionPrice: Number(executionPrice),
      pnl: Number(pnl),
      pnlState,
      decision,
      notes: notes.trim(),
    });
  };

  return (
    <View style={styles.card}>
      <View style={styles.heading}>
        <View>
          <Text style={styles.eyebrow}>本地记录 · 不进入市场评分</Text>
          <Text style={styles.title}>记录执行事实</Text>
        </View>
        <Pressable
          accessibilityLabel="取消记录执行"
          accessibilityRole="button"
          onPress={onCancel}
          style={({ pressed }) => [styles.cancel, pressed && styles.pressed]}>
          <Text style={styles.cancelText}>取消</Text>
        </Pressable>
      </View>

      <LabeledInput
        error={errors.symbol}
        label="股票代码"
        onChangeText={setSymbol}
        placeholder="NVDA"
        value={symbol}
      />

      <Segment<PlanSide>
        label="方向"
        onChange={setSide}
        options={[
          ["long", "做多"],
          ["short", "做空"],
        ]}
        value={side}
      />

      <View style={styles.inputRow}>
        <LabeledInput
          error={errors.quantity}
          keyboardType="decimal-pad"
          label="成交数量"
          onChangeText={setQuantity}
          placeholder="10"
          value={quantity}
        />
        <LabeledInput
          error={errors.executionPrice}
          keyboardType="decimal-pad"
          label="成交价格"
          onChangeText={setExecutionPrice}
          placeholder="140.25"
          value={executionPrice}
        />
      </View>

      <LabeledInput
        error={errors.pnl}
        keyboardType="numbers-and-punctuation"
        label="本笔盈亏"
        onChangeText={setPnl}
        placeholder="可输入负数"
        value={pnl}
      />

      <Segment<JournalEntry["pnlState"]>
        label="盈亏状态"
        onChange={setPnlState}
        options={[
          ["realized", "已实现"],
          ["unrealized", "未实现"],
        ]}
        value={pnlState}
      />
      <Segment<JournalEntry["decision"]>
        label="执行选择"
        onChange={setDecision}
        options={[
          ["followed", "遵循方案"],
          ["overridden", "主动覆盖"],
        ]}
        value={decision}
      />

      <LabeledInput
        label="复盘备注"
        multiline
        onChangeText={setNotes}
        placeholder="记录原因、偏差和教训；不能改变客观结论"
        value={notes}
      />

      <Pressable
        accessibilityLabel="保存执行记录"
        accessibilityRole="button"
        onPress={submit}
        style={({ pressed }) => [styles.save, pressed && styles.pressed]}>
        <Text style={styles.saveText}>保存执行记录</Text>
      </Pressable>
    </View>
  );
}

type LabeledInputProps = {
  error?: string | undefined;
  keyboardType?: "default" | "decimal-pad" | "numbers-and-punctuation";
  label: string;
  multiline?: boolean;
  onChangeText(value: string): void;
  placeholder: string;
  value: string;
};

function LabeledInput({
  error,
  keyboardType = "default",
  label,
  multiline = false,
  onChangeText,
  placeholder,
  value,
}: LabeledInputProps) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        keyboardType={keyboardType}
        multiline={multiline}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        style={[styles.input, multiline && styles.notes]}
        value={value}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

type SegmentProps<T extends string> = {
  label: string;
  onChange(value: T): void;
  options: readonly (readonly [T, string])[];
  value: T;
};

function Segment<T extends string>({ label, onChange, options, value }: SegmentProps<T>) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.segment}>
        {options.map(([key, copy]) => {
          const selected = key === value;
          return (
            <Pressable
              accessibilityLabel={copy}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              key={key}
              onPress={() => onChange(key)}
              style={({ pressed }) => [
                styles.segmentButton,
                selected && styles.segmentSelected,
                pressed && styles.pressed,
              ]}>
              <Text style={[styles.segmentText, selected && styles.segmentTextSelected]}>
                {copy}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.md,
  },
  heading: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  eyebrow: { color: colors.blue, fontSize: 8, fontWeight: "900" },
  title: { color: colors.ink, fontSize: 15, fontWeight: "900", marginTop: 2 },
  cancel: { alignItems: "center", justifyContent: "center", minHeight: 44, paddingHorizontal: spacing.md },
  cancelText: { color: colors.muted, fontSize: 10, fontWeight: "900" },
  inputRow: { flexDirection: "row", gap: spacing.sm },
  field: { flex: 1, gap: 4 },
  label: { color: colors.muted, fontSize: 8, fontWeight: "900" },
  input: {
    backgroundColor: colors.backgroundRaised,
    borderColor: colors.line,
    borderRadius: radius.sm,
    borderWidth: StyleSheet.hairlineWidth,
    color: colors.ink,
    fontSize: 12,
    minHeight: 44,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  notes: { minHeight: 72, textAlignVertical: "top" },
  error: { color: colors.red, fontSize: 8, fontWeight: "800" },
  segment: { flexDirection: "row", gap: spacing.xs },
  segmentButton: {
    alignItems: "center",
    backgroundColor: colors.backgroundRaised,
    borderColor: colors.line,
    borderRadius: radius.sm,
    borderWidth: StyleSheet.hairlineWidth,
    flex: 1,
    justifyContent: "center",
    minHeight: 44,
  },
  segmentSelected: { backgroundColor: colors.blue, borderColor: colors.blue },
  segmentText: { color: colors.muted, fontSize: 9, fontWeight: "900" },
  segmentTextSelected: { color: colors.card },
  save: {
    alignItems: "center",
    backgroundColor: colors.navy,
    borderRadius: radius.md,
    justifyContent: "center",
    minHeight: 48,
  },
  saveText: { color: colors.card, fontSize: 11, fontWeight: "900" },
  pressed: { opacity: 0.66 },
});
