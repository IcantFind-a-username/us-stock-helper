import { SymbolView } from "expo-symbols";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { fixtureRepository } from "@/fixtures/repository";
import { colors, spacing } from "@/theme/tokens";

const fixtureSymbols = Array.from(
  new Set(
    (["short", "swing", "long"] as const).flatMap((horizon) => {
      const snapshot = fixtureRepository.getDashboard(horizon);
      return [...snapshot.watchlist.map((quote) => quote.symbol), ...snapshot.candidates.map((candidate) => candidate.symbol)];
    }),
  ),
);

type IoniconName = "search-outline" | "notifications-outline";

function Ionicons({ name }: { name: IoniconName }) {
  return <SymbolView name={name === "search-outline" ? "magnifyingglass" : "bell"} size={24} tintColor={colors.ink} />;
}

type GlobalHeaderProps = {
  title?: string;
  onSearch: () => void;
  onAlerts: () => void;
};

export function GlobalHeader({ title = "市场观察", onSearch, onAlerts }: GlobalHeaderProps) {
  return (
    <View style={styles.header}>
      <Text style={styles.title}>{title}</Text>
      <View style={styles.actions}>
        <Pressable
          accessibilityHint={`搜索 ${fixtureSymbols.length} 个演示股票`}
          accessibilityLabel="搜索股票"
          accessibilityRole="button"
          onPress={onSearch}
          style={styles.button}>
          <Ionicons name="search-outline" />
        </Pressable>
        <Pressable accessibilityLabel="查看提醒" accessibilityRole="button" onPress={onAlerts} style={styles.button}>
          <Ionicons name="notifications-outline" />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between", minHeight: 52 },
  title: { color: colors.ink, fontSize: 22, fontWeight: "800" },
  actions: { flexDirection: "row", gap: spacing.sm },
  button: { alignItems: "center", height: 44, justifyContent: "center", width: 44 },
});
