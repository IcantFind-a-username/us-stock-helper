import { useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { PriceChart } from "@/components/chart/PriceChart";
import {
  candleCountForInterval,
  ChartIntervalSwitch,
  type ChartDisplayInterval,
} from "@/components/chart/ChartIntervalSwitch";
import { DecisionNewsSection } from "@/components/news/DecisionNewsSection";
import { DecisionCard } from "@/components/stock/DecisionCard";
import { IndicatorFactRow } from "@/components/stock/IndicatorFactRow";
import { InstitutionalHoldingsCard } from "@/components/stock/InstitutionalHoldingsCard";
import { ParticipationCard } from "@/components/stock/ParticipationCard";
import { StockHeader } from "@/components/stock/StockHeader";
import { getChartDataStatus } from "@/components/stock/chartDataStatus";
import { Disclosure } from "@/components/ui/Disclosure";
import { HorizonSwitch } from "@/components/ui/HorizonSwitch";
import { Screen } from "@/components/ui/Screen";
import {
  toDemoChartSnapshot,
  type ChartSnapshot,
  type Decision,
  type LiveStockSnapshot,
} from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
import { describeMarketError } from "@/i18n/marketErrorCopy";
import { serviceTextLabel, snapshotSourceLabel } from "@/i18n/serverVocabulary";
import { useAppState } from "@/state/AppStateProvider";
import {
  type MarketDataState,
  useAdviserDecision,
  useDecision,
  useStockSnapshot,
} from "@/state/MarketDataProvider";
import { colors, radius, spacing } from "@/theme/tokens";

type VisibleTool =
  | "ma5"
  | "magicNine"
  | "macd"
  | "rsi"
  | "participation"
  | "forecast";

function formatUtc(value: string) {
  return value.replace("T", " ").replace(".000Z", " UTC");
}

/**
 * A card the chain cannot fill yet, labelled with the input it is short of.
 *
 * The label used to read "尚未接入真实分析" on every one of these, which stopped
 * being true once the analysis service shipped: the chain does answer, it just
 * has no source for these particular factors and says so in its own
 * `unavailableFactors` list.
 */
function DisabledAnalysisCard({
  title,
  missing,
}: {
  title: string;
  missing: string;
}) {
  return (
    <View style={styles.disabledCard}>
      <Text style={styles.disabledTitle}>{title}</Text>
      <Text style={styles.disabledText}>{missing}</Text>
    </View>
  );
}

function DecisionState({ decision }: { decision: MarketDataState<Decision> }) {
  const unavailable = decision.status === "unavailable";
  const failure = describeMarketError(decision.error?.category ?? "offline");
  return (
    <View style={styles.decisionState} testID="decision-state">
      <Text style={styles.eyebrow}>综合结论</Text>
      <Text style={styles.decisionStateText}>
        {unavailable ? `分析不可用 · ${failure.label}` : "正在读取分析…"}
      </Text>
      {unavailable ? (
        <Text style={styles.decisionStateBody}>{failure.body}</Text>
      ) : null}
      {unavailable ? (
        <Pressable
          accessibilityLabel="重试分析"
          accessibilityRole="button"
          onPress={decision.refresh}
          style={({ pressed }) => [
            styles.decisionRetry,
            pressed && styles.pressed,
          ]}>
          <Text style={styles.decisionRetryText}>重试分析</Text>
        </Pressable>
      ) : null}
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
  // This is the whole page when a symbol will not open, so it is the one place
  // that has room to say what was refused and why. An outdated gateway used to
  // be the only failure spelled out here; every other one arrived as its wire
  // category, which is how a rejected point-in-time series became the word
  // "malformed" and nothing else.
  const failure = describeMarketError(market.error?.category ?? "offline");
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
            ? `行情不可用 · ${failure.label}`
            : "正在连接 moomoo 行情…"}
        </Text>
        <Text style={styles.stateBody} testID="stock-state-body">
          {unavailable
            ? failure.body
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
  const [chartInterval, setChartInterval] = useState<ChartDisplayInterval>("day");
  const market = useStockSnapshot(
    symbol,
    chartInterval,
    candleCountForInterval(chartInterval),
  );
  const decision = useDecision(symbol, horizon);
  const adviserDecision = useAdviserDecision(symbol, horizon);
  const displayedDecision = adviserDecision.data ?? decision.data;
  const stock =
    market.status === "demo"
      ? toDemoChartSnapshot(fixtureRepository.getStock(symbol, horizon))
      : market.data;
  const [visibleTools, setVisibleTools] = useState<
    Record<VisibleTool, boolean>
  >({
    ma5: true,
    magicNine: true,
    macd: true,
    // A phone can hold one indicator subchart under the price panel without
    // squeezing it; the second one is opened on request.
    rsi: false,
    participation: true,
    forecast: true,
  });

  if (!stock) {
    // Quotes and analysis come from independent services, and this screen is
    // the only route to any news. Returning here on a market failure would
    // throw away a live analysis and empty the app over a moomoo hiccup, so
    // the quote surface reports its own outage and the rest still renders.
    return (
      <View style={styles.screen} testID="stock-detail">
        <StockPageState
          market={market as MarketDataState<ChartSnapshot>}
          onBack={() => router.back()}
        />
        {displayedDecision ? (
          <>
            <DecisionCard decision={displayedDecision} />
            <DecisionNewsSection
              decision={displayedDecision}
              errorCategory={null}
              symbol={symbol}
            />
          </>
        ) : null}
      </View>
    );
  }

  const liveStock = stock.demoData
    ? null
    : (stock as LiveStockSnapshot);
  const dataStatus = getChartDataStatus(market.status, stock.demoData);
  const magicNineAvailable =
    stock.magicNine.qualityStatus !== "unavailable";
  const lastCompletedSetup = stock.magicNine.lastCompleted;
  // The finished run is carried separately precisely because the current count
  // stops describing it, so it stays visible even when the count is missing.
  const lastCompletedSummary = lastCompletedSetup
    ? ` · 最近完成 ${
        lastCompletedSetup.direction === "bullish" ? "看涨" : "看跌"
      }九转 · ${lastCompletedSetup.perfected ? "完美" : "未完美"} · ${
        lastCompletedSetup.barsSince
      } 根前`
    : "";
  const magicNineSummary = magicNineAvailable
    ? `九转 ${stock.magicNine.count} · ${
        stock.magicNine.completed ? "序列完成" : "尚未完成"
      }${lastCompletedSummary}`
    : `九转 暂不可用${lastCompletedSummary}`;
  const snapshotWarnings = liveStock?.warnings ?? [];
  const realizedVolatility = liveStock?.indicators.volatility.value ?? null;
  const latestCandle = stock.candles.at(-1);
  const toolOptions: { key: VisibleTool; label: string }[] = [
    { key: "ma5", label: "MA5" },
    { key: "magicNine", label: "九转" },
    { key: "macd", label: "MACD" },
    { key: "rsi", label: "RSI" },
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

      {stock.demoData ? null : (
        <ChartIntervalSwitch
          onChange={setChartInterval}
          value={chartInterval}
        />
      )}

      <PriceChart
        compact
        dataStatus={dataStatus}
        showForecast={visibleTools.forecast}
        showMacd={visibleTools.macd}
        showMagicNine={visibleTools.magicNine}
        showMovingAverage={visibleTools.ma5}
        showParticipation={visibleTools.participation}
        showRsi={visibleTools.rsi}
        stock={stock}
      />

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

      <Disclosure title="图表口径与免责">
        <Text style={styles.disclosureText}>
          横轴按 K 线序号排列，休市时段不占宽度；时间标签是该根 K 线的真实收盘时间（UTC）。
        </Text>
        <Text style={styles.disclosureText}>
          图上只画服务端发布的版本化指标序列。手机端不会用收盘价推算任何指标，序列缺失时直接标注缺失。
        </Text>
        <Text style={styles.disclosureText}>
          订单规模活动代理 · 非真实机构身份 · 每根活动柱与已完成 K
          线一一对应；延迟持仓披露独立展示。
        </Text>
        {stock.forecast && visibleTools.forecast ? (
          <Text style={styles.disclosureText}>
            演示概率预测 · 非投资承诺 · {stock.forecast.horizon} ·{" "}
            {stock.forecast.modelVersion}
          </Text>
        ) : null}
      </Disclosure>

      <View style={styles.summary} testID="stock-fact-summary">
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
        <IndicatorFactRow
          ma5={stock.indicators.ma5}
          macd={stock.indicators.macd}
          realizedVolatility={realizedVolatility}
          rsi={stock.indicators.rsi}
        />
        <Text style={styles.summaryMeta} testID="stock-summary-meta">
          {magicNineSummary} · 来源{" "}
          {snapshotSourceLabel(stock.source.source)} · 截止{" "}
          {formatUtc(stock.source.asOf)}
        </Text>
        {snapshotWarnings.length ? (
          <View style={styles.warnings} testID="snapshot-warnings">
            {snapshotWarnings.map((warning) => (
              <Text key={warning} style={styles.warning}>
                · {serviceTextLabel(warning)}
              </Text>
            ))}
          </View>
        ) : null}
      </View>

      {visibleTools.participation ? (
        <ParticipationCard bars={stock.participationBars} />
      ) : null}
      <InstitutionalHoldingsCard
        holdings={liveStock?.institutionalHoldings ?? []}
      />

      {stock.demoData ? (
        stock.forecast ? null : (
          <DisabledAnalysisCard
            missing="演示快照没有附带预测区间。"
            title="预测分析"
          />
        )
      ) : displayedDecision ? (
        <DecisionCard decision={displayedDecision} />
      ) : (
        <DecisionState decision={decision} />
      )}
      {/* The news surface hangs off the decision because the decision is what
          carries reports: the analysis service answers per symbol and returns
          the evidence it stood on, and there is no symbol-free news route a
          separate tab could have read. Demo mode has no decision at all, so it
          gets no news section rather than a fixture-filled one. */}
      {stock.demoData ? null : (
        <DecisionNewsSection
          decision={displayedDecision}
          errorCategory={
            decision.status === "unavailable"
              ? decision.error?.category ?? "offline"
              : null
          }
          symbol={symbol}
        />
      )}
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
      {stock.demoData ? null : (
        <Pressable
          accessibilityLabel={`为 ${symbol} 生成一次 Claude 新闻解读`}
          accessibilityRole="button"
          accessibilityState={{
            disabled: adviserDecision.status === "loading",
          }}
          disabled={adviserDecision.status === "loading"}
          onPress={adviserDecision.request}
          style={({ pressed }) => [
            styles.adviserButton,
            adviserDecision.status === "loading" &&
              styles.adviserButtonLoading,
            pressed && styles.pressed,
          ]}>
          <Text style={styles.adviserButtonTitle}>
            {adviserDecision.status === "loading"
              ? "Claude 正在解读…"
              : adviserDecision.status === "live"
                ? "重新生成一次 Claude 新闻解读"
                : "生成一次 Claude 新闻解读"}
          </Text>
          <Text style={styles.adviserButtonText}>
            仅当前 {symbol} · 每次点击只调用 1 次模型 · 不会批量分析自选股
          </Text>
          {adviserDecision.error ? (
            <Text style={styles.adviserButtonError}>
              本次未生成：{adviserDecision.error.message}
            </Text>
          ) : null}
        </Pressable>
      )}
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
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: spacing.md,
  },
  demoBannerText: { color: "#8B5C08", fontSize: 13, fontWeight: "900" },
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
  summary: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    padding: spacing.md,
  },
  eyebrow: { color: colors.muted, fontSize: 12, fontWeight: "800" },
  summaryTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
    lineHeight: 20,
  },
  disclosureText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
    lineHeight: 18,
  },
  summaryMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "600",
    lineHeight: 18,
  },
  warnings: { gap: 2, marginTop: 2 },
  warning: {
    color: colors.amber,
    fontSize: 12,
    fontWeight: "600",
    lineHeight: 18,
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
  toolText: { color: colors.muted, fontSize: 12, fontWeight: "800" },
  toolTextActive: { color: colors.card },
  disabledCard: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    opacity: 0.72,
    padding: spacing.md,
  },
  disabledTitle: { color: colors.ink, fontSize: 13, fontWeight: "800" },
  disabledText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 18,
  },
  decisionState: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: 1,
    gap: spacing.xs,
    padding: spacing.md,
  },
  decisionStateText: { color: colors.muted, fontSize: 12, fontWeight: "800" },
  decisionStateBody: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  decisionRetry: {
    alignItems: "flex-start",
    justifyContent: "center",
    minHeight: 44,
  },
  decisionRetryText: { color: colors.blue, fontSize: 12, fontWeight: "900" },
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
  adviserButton: {
    alignItems: "center",
    backgroundColor: colors.blueSoft,
    borderRadius: radius.md,
    gap: 2,
    justifyContent: "center",
    minHeight: 48,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  adviserButtonLoading: { opacity: 0.72 },
  adviserButtonTitle: { color: colors.blue, fontSize: 13, fontWeight: "900" },
  adviserButtonText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    textAlign: "center",
  },
  adviserButtonError: {
    color: colors.red,
    fontSize: 12,
    fontWeight: "700",
    textAlign: "center",
  },
  pressed: { opacity: 0.68 },
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
