import { useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { PriceChart } from "@/components/chart/PriceChart";
import { IndicatorStrip } from "@/components/stock/IndicatorStrip";
import { ParticipationCard } from "@/components/stock/ParticipationCard";
import { StockHeader } from "@/components/stock/StockHeader";
import { getChartDataStatus } from "@/components/stock/chartDataStatus";
import { HorizonSwitch } from "@/components/ui/HorizonSwitch";
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

type VisibleTool = "ma5" | "magicNine" | "participation" | "forecast";

function formatUtc(value: string) {
  return value.replace("T", " ").replace(".000Z", " UTC");
}

function DisabledAnalysisCard({ title }: { title: string }) {
  return (
    <View style={styles.disabledCard}>
      <Text style={styles.disabledTitle}>{title}</Text>
      <Text style={styles.disabledText}>尚未接入真实分析</Text>
    </View>
  );
}

function StockPageState({
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
        accessibilityLabel="返回自选列表"
        accessibilityRole="button"
        onPress={onBack}
        style={({ pressed }) => [
          styles.stateBack,
          pressed && styles.pressed,
        ]}>
        <Text style={styles.stateBackText}>‹ 返回</Text>
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
            : "正在读取实时只读快照。你可以返回自选列表稍后再试。"}
        </Text>
        {unavailable ? (
          <Pressable
            accessibilityLabel="重试行情"
            accessibilityRole="button"
            onPress={market.refresh}
            style={({ pressed }) => [
              styles.retryButton,
              pressed && styles.pressed,
            ]}>
            <Text style={styles.retryText}>重试行情</Text>
          </Pressable>
        ) : null}
      </View>
    </Screen>
  );
}

export function StockDetailScreen() {
  const params = useLocalSearchParams<{ symbol?: string | string[] }>();
  const router = useRouter();
  const { horizon, setHorizon } = useAppState();
  const symbolParam = Array.isArray(params.symbol)
    ? params.symbol[0]
    : params.symbol;
  const symbol = (symbolParam ?? "NVDA").toUpperCase();
  const market = useStockSnapshot(symbol, "5m", 200);
  const stock =
    market.status === "demo"
      ? toDemoChartSnapshot(fixtureRepository.getStock(symbol, horizon))
      : market.data;
  const [visibleTools, setVisibleTools] = useState<
    Record<VisibleTool, boolean>
  >({
    ma5: true,
    magicNine: true,
    participation: true,
    forecast: true,
  });

  if (!stock) {
    return (
      <StockPageState
        market={market as MarketDataState<ChartSnapshot>}
        onBack={() => router.back()}
      />
    );
  }

  const liveStock = stock.demoData
    ? null
    : (stock as LiveStockSnapshot);
  const dataStatus = getChartDataStatus(market.status, stock.demoData);
  const magicNineAvailable =
    stock.magicNine.qualityStatus !== "unavailable";
  const lastCompletedSetup = stock.magicNine.lastCompleted;
  const magicNineSummary = magicNineAvailable
    ? `九转 ${stock.magicNine.count} · ${
        stock.magicNine.completed ? "序列完成" : "尚未完成"
      }${
        lastCompletedSetup
          ? ` · 最近完成 ${
              lastCompletedSetup.direction === "bullish" ? "看涨" : "看跌"
            }九转 · ${lastCompletedSetup.perfected ? "完美" : "未完美"} · ${
              lastCompletedSetup.barsSince
            } 根前`
          : ""
      }`
    : "九转 暂不可用";
  const snapshotWarnings = liveStock?.warnings ?? [];
  const latestCandle = stock.candles.at(-1);
  const histogram = Array.isArray(stock.indicators.macd.histogram)
    ? (stock.indicators.macd.histogram.at(-1) ?? null)
    : stock.indicators.macd.histogram;
  const toolOptions: { key: VisibleTool; label: string }[] = [
    { key: "ma5", label: "MA5" },
    { key: "magicNine", label: "九转" },
    { key: "participation", label: "参与结构" },
    ...(stock.forecast ? [{ key: "forecast" as const, label: "预测区间" }] : []),
  ];

  return (
    <Screen hideGlobalHeader style={styles.screen}>
      {stock.demoData ? (
        <View accessibilityRole="alert" style={styles.demoBanner}>
          <Text style={styles.demoBannerText}>演示数据 · 非实时行情</Text>
        </View>
      ) : null}
      <StockHeader
        dataStatus={dataStatus}
        onBack={() => router.back()}
        stock={stock}
      />
      {stock.demoData ? (
        <HorizonSwitch
          onChange={setHorizon}
          value={horizon}
        />
      ) : null}

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

      <View style={styles.summary}>
        <Text style={styles.eyebrow}>
          {dataStatus === "demo"
            ? "演示事实摘要"
            : dataStatus === "stale"
              ? "缓存事实摘要"
              : "实时事实摘要"}
        </Text>
        <Text style={styles.summaryTitle}>
          {latestCandle
            ? `最新已完成 K 线 · 收 ${latestCandle.close.toFixed(2)}`
            : "暂无已完成 K 线"}
        </Text>
        <View style={styles.factRow}>
          <Text style={styles.fact}>
            MA5{" "}
            {stock.indicators.ma5.value === null
              ? "暂不可用"
              : stock.indicators.ma5.value.toFixed(2)}
          </Text>
          <Text style={styles.fact}>
            RSI{" "}
            {stock.indicators.rsi.value === null
              ? "暂不可用"
              : stock.indicators.rsi.value.toFixed(1)}
          </Text>
          <Text style={styles.fact}>
            MACD {histogram === null ? "暂不可用" : histogram.toFixed(2)}
          </Text>
        </View>
        <Text style={styles.summaryMeta} testID="stock-summary-meta">
          {magicNineSummary} · 来源{" "}
          {stock.source.source} · 截止 {formatUtc(stock.source.asOf)}
        </Text>
        {snapshotWarnings.length ? (
          <View style={styles.warnings} testID="snapshot-warnings">
            {snapshotWarnings.map((warning) => (
              <Text key={warning} style={styles.warning}>
                · {warning}
              </Text>
            ))}
          </View>
        ) : null}
      </View>

      <View accessibilityLabel="图表工具" style={styles.tools}>
        {toolOptions.map(({ key, label }) => {
          const visible = visibleTools[key];
          return (
            <Pressable
              accessibilityLabel={`${label}，${visible ? "已显示" : "已隐藏"}`}
              accessibilityRole="button"
              accessibilityState={{ selected: visible }}
              key={key}
              onPress={() =>
                setVisibleTools((current) => ({
                  ...current,
                  [key]: !current[key],
                }))
              }
              style={({ pressed }) => [
                styles.tool,
                visible && styles.toolActive,
                pressed && styles.pressed,
              ]}>
              <Text
                style={[styles.toolText, visible && styles.toolTextActive]}>
                {label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <PriceChart
        compact
        dataStatus={dataStatus}
        showForecast={visibleTools.forecast}
        showMagicNine={visibleTools.magicNine}
        showMovingAverage={visibleTools.ma5}
        showParticipation={visibleTools.participation}
        stock={stock}
      />
      {stock.forecast && visibleTools.forecast ? (
        <View style={styles.forecastNotice}>
          <Text style={styles.forecastTitle}>演示概率预测 · 非投资承诺</Text>
          <Text style={styles.forecastBody}>
            {stock.forecast.horizon} · {stock.forecast.modelVersion}
          </Text>
        </View>
      ) : null}

      <IndicatorStrip
        macd={stock.indicators.macd}
        rsi={stock.indicators.rsi}
      />
      {visibleTools.participation ? (
        <ParticipationCard
          bars={stock.participationBars}
          holdings={liveStock?.institutionalHoldings ?? []}
        />
      ) : null}

      {!stock.forecast ? <DisabledAnalysisCard title="预测分析" /> : null}
      <DisabledAnalysisCard title="基本面与形态" />
      <DisabledAnalysisCard title="市场环境" />

      <Pressable
        accessibilityLabel="查看完整图表"
        accessibilityRole="button"
        onPress={() =>
          router.push({
            pathname: "/stocks/[symbol]/chart",
            params: { symbol },
          })
        }
        style={({ pressed }) => [
          styles.secondaryButton,
          pressed && styles.pressed,
        ]}>
        <Text style={styles.secondaryText}>查看大图</Text>
      </Pressable>
      <Pressable
        accessibilityLabel="顾问分析尚未接入真实分析"
        accessibilityRole="button"
        accessibilityState={{ disabled: true }}
        disabled
        style={styles.disabledButton}>
        <Text style={styles.disabledButtonTitle}>顾问分析</Text>
        <Text style={styles.disabledButtonText}>尚未接入真实分析</Text>
      </Pressable>
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
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: spacing.md,
  },
  demoBannerText: { color: "#8B5C08", fontSize: 11, fontWeight: "900" },
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
  summary: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    padding: spacing.md,
  },
  eyebrow: { color: colors.muted, fontSize: 9, fontWeight: "800" },
  summaryTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
    lineHeight: 20,
  },
  factRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  fact: {
    backgroundColor: colors.background,
    borderRadius: radius.pill,
    color: colors.ink,
    fontSize: 9,
    fontWeight: "800",
    overflow: "hidden",
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  summaryMeta: {
    color: colors.muted,
    fontSize: 9,
    fontWeight: "600",
    lineHeight: 14,
  },
  warnings: { gap: 2, marginTop: 2 },
  warning: {
    color: colors.amber,
    fontSize: 9,
    fontWeight: "600",
    lineHeight: 13,
  },
  tools: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  tool: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderRadius: radius.pill,
    justifyContent: "center",
    minHeight: 44,
    paddingHorizontal: 12,
  },
  toolActive: { backgroundColor: colors.navyRaised },
  toolText: { color: colors.muted, fontSize: 9, fontWeight: "800" },
  toolTextActive: { color: colors.card },
  forecastNotice: {
    backgroundColor: colors.blueSoft,
    borderRadius: radius.md,
    gap: 3,
    padding: spacing.sm,
  },
  forecastTitle: { color: colors.blue, fontSize: 10, fontWeight: "900" },
  forecastBody: { color: "#3B5F91", fontSize: 9, lineHeight: 14 },
  disabledCard: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    opacity: 0.72,
    padding: spacing.md,
  },
  disabledTitle: { color: colors.ink, fontSize: 11, fontWeight: "800" },
  disabledText: { color: colors.muted, fontSize: 9, fontWeight: "700" },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 44,
  },
  secondaryText: { color: colors.ink, fontSize: 12, fontWeight: "800" },
  disabledButton: {
    alignItems: "center",
    backgroundColor: colors.blueSoft,
    borderRadius: radius.md,
    gap: 2,
    justifyContent: "center",
    minHeight: 48,
    opacity: 0.72,
  },
  disabledButtonTitle: { color: colors.blue, fontSize: 12, fontWeight: "900" },
  disabledButtonText: { color: colors.muted, fontSize: 9, fontWeight: "700" },
  pressed: { opacity: 0.68 },
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
  stateBackText: { color: colors.blue, fontSize: 12, fontWeight: "900" },
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
