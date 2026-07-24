import { useMemo, useState } from "react";
import {
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, radius, spacing } from "@/theme/tokens";

export type StockSearchOption = {
  symbol: string;
  company: string;
  price: number;
  changePercent: number;
};

type StockSearchSheetProps = {
  visible: boolean;
  options: StockSearchOption[];
  onClose(): void;
  onSelect(symbol: string): void;
};

export function StockSearchSheet({
  visible,
  options,
  onClose,
  onSelect,
}: StockSearchSheetProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return options;
    return options.filter(
      ({ company, symbol }) =>
        symbol.toLowerCase().includes(normalized) ||
        company.toLowerCase().includes(normalized),
    );
  }, [options, query]);

  if (!visible) return null;

  const closeSheet = () => {
    setQuery("");
    onClose();
  };

  return (
    <Modal
      animationType="slide"
      onRequestClose={closeSheet}
      presentationStyle="pageSheet"
      visible>
      <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>本地关注列表 · 演示</Text>
            <Text style={styles.title}>搜索关注标的</Text>
          </View>
          <Pressable
            accessibilityLabel="关闭股票搜索"
            accessibilityRole="button"
            onPress={closeSheet}
            style={({ pressed }) => [styles.close, pressed && styles.pressed]}>
            <Text style={styles.closeText}>完成</Text>
          </Pressable>
        </View>
        <TextInput
          accessibilityLabel="搜索股票代码或名称"
          autoCapitalize="characters"
          autoCorrect={false}
          onChangeText={setQuery}
          placeholder="代码或公司，例如 TSLA"
          placeholderTextColor={colors.muted}
          style={styles.input}
          value={query}
        />
        <View style={styles.results}>
          {filtered.map((option) => (
            <Pressable
              accessibilityLabel={`打开 ${option.symbol} ${option.company}`}
              accessibilityRole="button"
              key={option.symbol}
              onPress={() => {
                setQuery("");
                onSelect(option.symbol);
              }}
              style={({ pressed }) => [styles.result, pressed && styles.pressed]}>
              <View style={styles.monogram}>
                <Text style={styles.monogramText}>{option.symbol.slice(0, 2)}</Text>
              </View>
              <View style={styles.copy}>
                <Text style={styles.symbol}>{option.symbol}</Text>
                <Text style={styles.company}>{option.company}</Text>
              </View>
              <View style={styles.quote}>
                <Text style={styles.price}>${option.price.toFixed(2)}</Text>
                <Text
                  style={[
                    styles.change,
                    option.changePercent >= 0 ? styles.positive : styles.negative,
                  ]}>
                  {option.changePercent >= 0 ? "+" : ""}
                  {option.changePercent.toFixed(2)}%
                </Text>
              </View>
            </Pressable>
          ))}
          {filtered.length === 0 ? (
            <View style={styles.empty}>
              <Text style={styles.emptyTitle}>没有匹配的演示标的</Text>
              <Text style={styles.emptyBody}>真实搜索将在 moomoo 只读网关接通后提供。</Text>
            </View>
          ) : null}
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: colors.background,
    flex: 1,
    paddingHorizontal: spacing.lg,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: spacing.sm,
  },
  eyebrow: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: "800",
  },
  title: {
    color: colors.ink,
    fontSize: 20,
    fontWeight: "900",
    marginTop: spacing.xxs,
  },
  close: {
    alignItems: "center",
    justifyContent: "center",
    minHeight: 44,
    minWidth: 44,
  },
  closeText: {
    color: colors.blue,
    fontSize: 14,
    fontWeight: "900",
  },
  input: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    color: colors.ink,
    fontSize: 15,
    minHeight: 48,
    paddingHorizontal: spacing.md,
  },
  results: {
    gap: spacing.sm,
    paddingTop: spacing.md,
  },
  result: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    minHeight: 64,
    paddingHorizontal: spacing.md,
  },
  monogram: {
    alignItems: "center",
    backgroundColor: colors.blueSoft,
    borderRadius: radius.sm,
    height: 36,
    justifyContent: "center",
    width: 36,
  },
  monogramText: {
    color: colors.blue,
    fontSize: 11,
    fontWeight: "900",
  },
  copy: {
    flex: 1,
    marginLeft: spacing.sm,
  },
  symbol: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  company: {
    color: colors.muted,
    fontSize: 10,
    marginTop: spacing.xxs,
  },
  quote: {
    alignItems: "flex-end",
  },
  price: {
    color: colors.ink,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
  },
  change: {
    fontSize: 10,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
    marginTop: spacing.xxs,
  },
  positive: { color: colors.green },
  negative: { color: colors.red },
  empty: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderRadius: radius.md,
    padding: spacing.xl,
  },
  emptyTitle: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
  },
  emptyBody: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 17,
    marginTop: spacing.xs,
    textAlign: "center",
  },
  pressed: { opacity: 0.66 },
});
