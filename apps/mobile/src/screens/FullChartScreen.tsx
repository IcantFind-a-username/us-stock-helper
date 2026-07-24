import { useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { PriceChart } from "@/components/chart/PriceChart";
import { IndicatorStrip } from "@/components/stock/IndicatorStrip";
import { Screen } from "@/components/ui/Screen";
import { fixtureRepository } from "@/fixtures/repository";
import { useAppState } from "@/state/AppStateProvider";
import { colors, radius, spacing } from "@/theme/tokens";

export function FullChartScreen() {
  const params = useLocalSearchParams<{ symbol?: string | string[] }>();
  const router = useRouter();
  const { horizon } = useAppState();
  const symbolParam = Array.isArray(params.symbol) ? params.symbol[0] : params.symbol;
  const symbol = (symbolParam ?? "NVDA").toUpperCase();
  const stock = fixtureRepository.getStock(symbol, horizon);

  return (
    <Screen hideGlobalHeader style={styles.screen}>
      <View style={styles.header}>
        <Pressable
          accessibilityLabel="返回股票详情"
          accessibilityRole="button"
          onPress={() => router.back()}
          style={styles.back}>
          <Text style={styles.backText}>完成</Text>
        </Pressable>
        <View style={styles.titleWrap}>
          <Text style={styles.title}>{symbol} 专业图表</Text>
          <Text style={styles.demo}>演示数据 · 非实时行情</Text>
        </View>
        <View style={styles.back} />
      </View>
      <PriceChart stock={stock} />
      <IndicatorStrip macd={stock.indicators.macd} rsi={stock.indicators.rsi} />
      <View style={styles.note}>
        <Text style={styles.noteTitle}>图上保持克制</Text>
        <Text style={styles.noteBody}>
          数字为九转序号；预测只从“现在”之后开始。新闻、地缘和形态长文留在证据页，不遮挡蜡烛与刻度。
        </Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { gap: spacing.md, paddingTop: spacing.xs },
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  back: { alignItems: "center", justifyContent: "center", minHeight: 44, minWidth: 44 },
  backText: { color: colors.blue, fontSize: 13, fontWeight: "900" },
  titleWrap: { alignItems: "center" },
  title: { color: colors.ink, fontSize: 17, fontWeight: "900" },
  demo: { color: colors.muted, fontSize: 9, marginTop: 2 },
  note: { backgroundColor: colors.card, borderRadius: radius.md, gap: 3, padding: spacing.md },
  noteTitle: { color: colors.ink, fontSize: 11, fontWeight: "900" },
  noteBody: { color: colors.muted, fontSize: 10, lineHeight: 15 },
});
