import { useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { PriceChart } from "@/components/chart/PriceChart";
import {
  candleCountForInterval,
  ChartIntervalSwitch,
  type ChartDisplayInterval,
} from "@/components/chart/ChartIntervalSwitch";
import { getChartDataStatus } from "@/components/stock/chartDataStatus";
import { IndicatorFactRow } from "@/components/stock/IndicatorFactRow";
import {
  adaptDemoHoldingsSection,
  InstitutionalHoldingsCard,
} from "@/components/stock/InstitutionalHoldingsCard";
import { ParticipationCard } from "@/components/stock/ParticipationCard";
import { Disclosure } from "@/components/ui/Disclosure";
import { Screen } from "@/components/ui/Screen";
import {
  toDemoChartSnapshot,
  type ChartSnapshot,
  type LiveStockSnapshot,
} from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
import { describeMarketError } from "@/i18n/marketErrorCopy";
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
  // The same explanation the stock page gives, because it is the same failure:
  // a reader who reached the big chart is owed no less than one who did not.
  const failure = describeMarketError(market.error?.category ?? "offline");
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
            ? `行情不可用 · ${failure.label}`
            : "正在连接 moomoo 行情…"}
        </Text>
        <Text style={styles.stateBody} testID="chart-state-body">
          {unavailable ? failure.body : "正在读取实时只读快照。"}
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
  const [chartInterval, setChartInterval] = useState<ChartDisplayInterval>("day");
  const market = useStockSnapshot(
    symbol,
    chartInterval,
    candleCountForInterval(chartInterval),
  );
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
  const dataStatus = getChartDataStatus(market.status, stock.demoData);
  const holdingsSection = stock.demoData
    ? adaptDemoHoldingsSection(stock.institutionalHoldings ?? [])
    : liveStock!.sections.holdings;

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
              : `${dataStatus === "stale" ? "缓存数据" : stock.quote ? "实时只读" : "已完成K线"} · 截止 ${formatUtc(stock.source.asOf)}`}
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
            accessibilityLabel={
              market.refreshing ? "正在刷新行情" : "刷新行情"
            }
            accessibilityRole="button"
            accessibilityState={{ disabled: market.refreshing }}
            disabled={market.refreshing}
            onPress={market.refresh}
            style={styles.refreshButton}>
            <Text style={styles.refreshText}>
              {market.refreshing ? "刷新中…" : "刷新"}
            </Text>
          </Pressable>
        </View>
      ) : null}

      {stock.demoData ? null : (
        <ChartIntervalSwitch
          onChange={setChartInterval}
          value={chartInterval}
        />
      )}

      <PriceChart dataStatus={dataStatus} stock={stock} />
      <View style={styles.factCard}>
        <IndicatorFactRow
          ma5={stock.indicators.ma5}
          macd={stock.indicators.macd}
          realizedVolatility={liveStock?.indicators.volatility.value}
          rsi={stock.indicators.rsi}
        />
        <Text style={styles.factMeta}>
          {stock.indicators.ma5.methodVersion} · 截止{" "}
          {formatUtc(stock.indicators.ma5.asOf)}
        </Text>
      </View>
      <Disclosure title="图表口径与免责">
        <Text style={styles.noteBody}>
          横轴按 K 线序号排列，休市时段不占宽度；时间标签是该根 K 线的真实收盘时间（UTC）。
        </Text>
        <Text style={styles.noteBody}>
          仅展示已完成 K 线与服务端发布的版本化指标序列，手机端不推算任何指标。活动占比不代表真实机构账户身份；延迟持仓披露独立展示。
        </Text>
      </Disclosure>
      <ParticipationCard bars={stock.participationBars} />
      <InstitutionalHoldingsCard section={holdingsSection} />
      <Text style={styles.boundary}>
        仅供分析与建议 · 不连接券商 · 不会自动下单
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
  demoBannerText: { color: "#8B5C08", fontSize: 13, fontWeight: "900" },
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
  demo: { color: "#8B5C08", fontSize: 12, marginTop: 2 },
  live: { color: colors.blue, fontSize: 12, fontWeight: "700", marginTop: 2 },
  staleBanner: {
    alignItems: "center",
    backgroundColor: colors.amberSoft,
    borderRadius: radius.md,
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 44,
    paddingLeft: spacing.md,
  },
  staleText: { color: "#8B5C08", fontSize: 12, fontWeight: "800" },
  refreshButton: {
    alignItems: "center",
    justifyContent: "center",
    minHeight: 44,
    minWidth: 56,
  },
  refreshText: { color: colors.blue, fontSize: 12, fontWeight: "900" },
  factCard: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    padding: spacing.md,
  },
  factMeta: { color: colors.muted, fontSize: 12, fontWeight: "600" },
  noteBody: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  boundary: {
    color: colors.muted,
    fontSize: 12,
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
  stateBody: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  retryButton: {
    alignItems: "center",
    backgroundColor: colors.blue,
    borderRadius: radius.md,
    justifyContent: "center",
    minHeight: 44,
  },
  retryText: { color: colors.card, fontSize: 12, fontWeight: "900" },
});
