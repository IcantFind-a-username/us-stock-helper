import type { ReactNode } from "react";
import type { StyleProp, ViewStyle } from "react-native";
import { ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { GlobalHeader } from "@/components/ui/GlobalHeader";
import { colors, spacing } from "@/theme/tokens";

type ScreenProps = {
  children: ReactNode;
  title?: string;
  hideGlobalHeader?: boolean;
  onSearch?: () => void;
  onAlerts?: () => void;
  scroll?: boolean;
  style?: StyleProp<ViewStyle>;
};

const noop = () => undefined;

export function Screen({
  children,
  title,
  hideGlobalHeader = false,
  onSearch = noop,
  onAlerts = noop,
  scroll = true,
  style,
}: ScreenProps) {
  const content = <View style={[styles.content, style]}>{children}</View>;

  return (
    <SafeAreaView edges={["top"]} style={styles.screen}>
      {hideGlobalHeader ? null : <GlobalHeader title={title ?? "市场观察"} onAlerts={onAlerts} onSearch={onSearch} />}
      {scroll ? <ScrollView contentContainerStyle={styles.scrollContent}>{content}</ScrollView> : content}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { backgroundColor: colors.background, flex: 1 },
  scrollContent: { paddingBottom: spacing.xl },
  content: { gap: spacing.lg, paddingHorizontal: spacing.lg },
});
