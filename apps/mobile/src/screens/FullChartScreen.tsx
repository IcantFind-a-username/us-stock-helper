import { useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { PriceChart } from "@/components/chart/PriceChart";
import { IndicatorStrip } from "@/components/stock/IndicatorStrip";
import { ParticipationCard } from "@/components/stock/ParticipationCard";
import { Screen } from "@/components/ui/Screen";
import {
  toDemoChartSnapshot,
  type ChartSnapshot,
  type LiveStockSnapshot,
} from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
import { useAppState } from "@/state/AppStateProvider";
import {
  type MarketDataState,
  useStockSnapshot,
} from "@/state/MarketDataProvider";
import { colors, radius, spacing } from "@/theme/tokens";

function formatUtc(value: string) {
  return value.replace("T", " ").replace(".000Z", " UTC");
}

function ChartPageState({
  market,
  onBack,
}: {
  market: MarketDataState<ChartSnapshot>;
  onBack(): void;
}) {
  const unavailable = market.status === "unavailable";
  return (
    <Screen hideGlobalHeader style={styles.screen}>
      <Pressable
        accessibilityLabel="返回股票详情"
        accessibilityRole="button"
        onPress={onBack}
        style={styles.stateBack}>
        <Text style={styles.backText}>完成</Text>
      </Pressable>
      <View style={styles.stateCard}>
        <Text style={styles.stateTitle}>
          {unavailable
            ? `行情不可用 · ${market.error?.category ?? "offline"}`
            : "正在连接 moomoo 行情…"}
        </Text>
        <Text style={styles.stateBody}>
          {unavailable
            ? "请检查 OpenD、网络或行情权限后重试。不会自动切换为演示数据。"
            : "正在读取实时只读快照。"}
        </Text>
        {unavailable ? (
          <Pressable
            accessibilityLabel="重试行情"
            accessibilityRole="button"
            onPress={market.refresh}
            style={styles.retryButton}>
            <Text style={styles.retryText}>重试行情</Text>
          </Pressable>
        ) : null}
      </View>
    </Screen>
  );
}

export function FullChartScreen() {
  const params = useLocalSearchParams<{ symbol?: string | string[] }>();
  const router = useRouter();
  const { horizon } = useAppState();
  const symbolParam = Array.isArray(params.symbol)
    ? params.symbol[0]
    : params.symbol;
  const symbol = (symbolParam ?? "NVDA").toUpperCase();
  const market = useStockSnapshot(symbol, "5m", 200);
  const stock =
    market.status === "demo"
      ? toDemoChartSnapshot(fixtureRepository.getStock(symbol, horizon))
      : market.data;

  if (!stock) {
    return (
      <ChartPageState
        market={market as MarketDataState<ChartSnapshot>}
        onBack={() => router.back()}
      />
    );
  }

  const liveStock = stock.demoData
    ? null
    : (stock as LiveStockSnapshot);
  const dataStatus =
    market.status === "stale"
      ? "stale"
      : stock.demoData
        ? "demo"
        : "live";

  return (
    <Screen hideGlobalHeader style={styles.screen}>
      {stock.demoData ? (
        <View accessibilityRole="alert" style={styles.demoBanner}>
          <Text style={styles.demoBannerText}>演示数据 · 非实时行情</Text>
        </View>
      ) : null}
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
          <Text style={stock.demoData ? styles.demo : styles.live}>
            {dataStatus === "demo"
              ? "演示快照"
              : `${dataStatus === "stale" ? "缓存数据" : "实时只读"} · 截止 ${formatUtc(stock.source.asOf)}`}
          </Text>
        </View>
        <View style={styles.back} />
      </View>

      {market.status === "stale" ? (
        <View accessibilityRole="alert" style={styles.staleBanner}>
          <Text style={styles.staleText}>
            行情已延迟 · 原始时间{" "}
            {formatUtc(market.lastVerifiedAt ?? stock.source.asOf)}
          </Text>
          <Pressable
            accessibilityLabel="刷新行情"
            accessibilityRole="button"
            onPress={market.refresh}
            style={styles.refreshButton}>
            <Text style={styles.refreshText}>刷新</Text>
          </Pressable>
        </View>
      ) : null}

      <PriceChart dataStatus={dataStatus} stock={stock} />
      <View style={styles.maCard}>
        <Text style={styles.maTitle}>
          MA5{" "}
          {stock.indicators.ma5.value === null
            ? "暂不可用"
            : stock.indicators.ma5.value.toFixed(2)}
        </Text>
        <Text style={styles.maMeta}>
          {stock.indicators.ma5.methodVersion} · 截止{" "}
          {formatUtc(stock.indicators.ma5.asOf)}
        </Text>
      </View>
      <IndicatorStrip
        macd={stock.indicators.macd}
        rsi={stock.indicators.rsi}
      />
      <ParticipationCard
        bars={stock.participationBars}
        holdings={liveStock?.institutionalHoldings ?? []}
      />
      <View style={styles.note}>
        <Text style={styles.noteTitle}>图上保持克制</Text>
        <Text style={styles.noteBody}>
          仅展示已完成 K 线、真实指标和逐 K 线对齐的订单规模活动代理。活动占比不代表真实机构账户身份；延迟持仓披露独立展示。
        </Text>
      </View>
      <Text style={styles.boundary}>
        仅分析与建议 · 不连接券商 · 不会自动下单
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { gap: spacing.md, paddingTop: spacing.xs },
  demoBanner: {
    alignItems: "center",
    backgroundColor: colors.amberSoft,
    borderRadius: radius.md,
    justifyContent: "center",
    minHeight: 44,
  },
  demoBannerText: { color: "#8B5C08", fontSize: 11, fontWeight: "900" },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  back: {
    alignItems: "center",
    justifyContent: "center",
    minHeight: 44,
    minWidth: 44,
  },
  backText: { color: colors.blue, fontSize: 13, fontWeight: "900" },
  titleWrap: { alignItems: "center" },
  title: { color: colors.ink, fontSize: 17, fontWeight: "900" },
  demo: { color: "#8B5C08", fontSize: 9, marginTop: 2 },
  live: { color: colors.blue, fontSize: 9, fontWeight: "700", marginTop: 2 },
  staleBanner: {
    alignItems: "center",
    backgroundColor: colors.amberSoft,
    borderRadius: radius.md,
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 44,
    paddingLeft: spacing.md,
  },
  staleText: { color: "#8B5C08", fontSize: 9, fontWeight: "800" },
  refreshButton: {
    alignItems: "center",
    justifyContent: "center",
    minHeight: 44,
    minWidth: 56,
  },
  refreshText: { color: colors.blue, fontSize: 10, fontWeight: "900" },
  maCard: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    padding: spacing.md,
  },
  maTitle: { color: colors.ink, fontSize: 12, fontWeight: "900" },
  maMeta: { color: colors.muted, fontSize: 9, fontWeight: "600" },
  note: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    gap: 3,
    padding: spacing.md,
  },
  noteTitle: { color: colors.ink, fontSize: 11, fontWeight: "900" },
  noteBody: { color: colors.muted, fontSize: 10, lineHeight: 15 },
  boundary: {
    color: colors.muted,
    fontSize: 9,
    fontWeight: "700",
    textAlign: "center",
  },
  stateBack: {
    alignItems: "flex-start",
    justifyContent: "center",
    minHeight: 44,
  },
  stateCard: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.lg,
  },
  stateTitle: { color: colors.ink, fontSize: 16, fontWeight: "900" },
  stateBody: { color: colors.muted, fontSize: 10, lineHeight: 16 },
  retryButton: {
    alignItems: "center",
    backgroundColor: colors.blue,
    borderRadius: radius.md,
    justifyContent: "center",
    minHeight: 44,
  },
  retryText: { color: colors.card, fontSize: 11, fontWeight: "900" },
});
