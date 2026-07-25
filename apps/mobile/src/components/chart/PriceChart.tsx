import { memo, useMemo, useState } from "react";
import {
  type GestureResponderEvent,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import Svg, {
  G,
  Line,
  Path,
  Rect,
  Text as SvgText,
} from "react-native-svg";

import {
  toDemoChartSnapshot,
  type ChartSnapshot,
  type StockSnapshot,
} from "@/domain/models";
import { buildChartGeometry, resolveChartWidth } from "@/domain/chart";
import { colors, radius, spacing } from "@/theme/tokens";

import { ChartLegend } from "./ChartLegend";

type PriceChartProps = {
  stock: ChartSnapshot | StockSnapshot;
  compact?: boolean;
  showForecast?: boolean;
  showMagicNine?: boolean;
  showMovingAverage?: boolean;
};

export const PriceChart = memo(function PriceChart({
  stock,
  compact = false,
  showForecast = true,
  showMagicNine = true,
  showMovingAverage = true,
}: PriceChartProps) {
  const { width: viewportWidth } = useWindowDimensions();
  const chartWidth = resolveChartWidth(viewportWidth);
  const height = compact ? 235 : 310;
  const snapshot = useMemo(
    () => ("quote" in stock ? stock : toDemoChartSnapshot(stock)),
    [stock],
  );
  const [selectedTimestamp, setSelectedTimestamp] = useState<string | null>(null);
  const chartForecast = useMemo(
    () =>
      snapshot.forecast && !showForecast
        ? { ...snapshot.forecast, points: [] }
        : snapshot.forecast,
    [showForecast, snapshot.forecast],
  );
  const geometry = useMemo(
    () =>
      buildChartGeometry(
        snapshot.candles,
        chartForecast,
        snapshot.participationBars,
        chartWidth,
        height,
      ),
    [
      chartForecast,
      chartWidth,
      height,
      snapshot.candles,
      snapshot.participationBars,
    ],
  );
  const hasForecast = showForecast && snapshot.forecast !== null;
  const lastCandle = geometry.candles.at(-1);
  const selectedCandle = selectedTimestamp
    ? snapshot.candles.find(({ timestamp }) => timestamp === selectedTimestamp)
    : undefined;
  const selectedParticipationGeometry = selectedTimestamp
    ? geometry.participation.find(({ timestamp }) => timestamp === selectedTimestamp)
    : undefined;
  const rawSelectedParticipation = selectedTimestamp
    ? snapshot.participationBars.find(({ closedAt }) => closedAt === selectedTimestamp)
    : undefined;
  const selectedParticipation =
    selectedParticipationGeometry?.available ||
    rawSelectedParticipation?.qualityStatus === "unavailable"
      ? rawSelectedParticipation
      : undefined;
  const summary = `${snapshot.symbol} 图表摘要，${geometry.candles.length} 根已完成 K 线，当前 ${snapshot.quote.price.toFixed(2)}，涨跌 ${snapshot.quote.changePercent >= 0 ? "上涨" : "下跌"} ${Math.abs(snapshot.quote.changePercent).toFixed(2)}%，${geometry.participation.filter(({ available }) => available).length} 根有订单规模活动占比；轻点或长按选择最近的 K 线`;
  const detailLabel = selectedCandle
    ? `${snapshot.symbol} 收盘时间 ${selectedCandle.timestamp}；开 ${selectedCandle.open.toFixed(2)}，高 ${selectedCandle.high.toFixed(2)}，低 ${selectedCandle.low.toFixed(2)}，收 ${selectedCandle.close.toFixed(2)}，成交量 ${selectedCandle.volume}；${
        selectedParticipation?.qualityStatus === "live" &&
        selectedParticipation.mainShare !== null &&
        selectedParticipation.retailShare !== null
          ? `主力代理 ${(selectedParticipation.mainShare * 100).toFixed(2)}%，散户代理 ${(selectedParticipation.retailShare * 100).toFixed(2)}%，覆盖率 ${(selectedParticipation.coverage * 100).toFixed(2)}%，来源 ${selectedParticipation.source}`
          : `活动占比缺失，覆盖率 ${((selectedParticipation?.coverage ?? 0) * 100).toFixed(2)}%，来源 ${selectedParticipation?.source ?? snapshot.source.source}，原因 ${selectedParticipation?.missingReason ?? "决策截止时不可用"}`
      }；非真实机构身份`
    : null;

  const selectNearestCandle = (event: GestureResponderEvent) => {
    if (!geometry.candles.length) return;
    const locationX = event.nativeEvent.locationX;
    const targetX = Number.isFinite(locationX) ? locationX : chartWidth;
    const nearest = geometry.candles.reduce((best, candle) =>
      Math.abs(candle.x - targetX) < Math.abs(best.x - targetX) ? candle : best,
    );
    setSelectedTimestamp(nearest.timestamp);
  };

  return (
    <View
      style={[styles.card, compact ? styles.compactCard : null]}
      testID="stock-chart-card">
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>
            {snapshot.interval} ·{" "}
            {snapshot.demoData
              ? "DEMO"
              : snapshot.source.status.toUpperCase()}
          </Text>
          <Text style={styles.title}>
            {hasForecast ? "价格 · 成交量 · 概率预测" : "价格 · 成交量"}
          </Text>
        </View>
        {hasForecast ? (
          <View style={styles.probability}>
            <Text style={styles.probabilityValue}>
              {Math.round(snapshot.forecast!.probability.up * 100)}%
            </Text>
            <Text style={styles.probabilityLabel}>上涨概率</Text>
          </View>
        ) : null}
      </View>

      <ChartLegend
        showForecast={hasForecast}
        showMovingAverage={showMovingAverage}
      />

      <Pressable
        accessibilityLabel={summary}
        accessibilityRole="button"
        onLongPress={selectNearestCandle}
        onPress={selectNearestCandle}
        style={({ pressed }) => [
          styles.chartPress,
          { minHeight: height },
          pressed && styles.chartPressed,
        ]}>
        <Svg
          accessibilityElementsHidden
          accessible={false}
          height={height}
          importantForAccessibility="no-hide-descendants"
          viewBox={`0 0 ${chartWidth} ${height}`}
          width="100%">
          {geometry.priceTicks.map((tick) => (
            <G key={tick.label}>
              <Line
                stroke={colors.navyLine}
                strokeDasharray="3 5"
                strokeWidth={0.7}
                x1={8}
                x2={chartWidth - 38}
                y1={tick.y}
                y2={tick.y}
              />
              <SvgText
                fill={colors.navyMuted}
                fontSize={9}
                textAnchor="end"
                x={chartWidth - 4}
                y={tick.y + 3}>
                {tick.label}
              </SvgText>
            </G>
          ))}

          {hasForecast && geometry.band80 ? (
            <Path d={geometry.band80} fill={colors.blueBright} fillOpacity={0.1} />
          ) : null}
          {hasForecast && geometry.band50 ? (
            <Path d={geometry.band50} fill={colors.blue} fillOpacity={0.18} />
          ) : null}
          {hasForecast && geometry.medianPath ? (
            <Path
              d={geometry.medianPath}
              fill="none"
              stroke={colors.purple}
              strokeDasharray="5 4"
              strokeWidth={1.6}
            />
          ) : null}
          {showMovingAverage && geometry.ma5Path ? (
            <Path
              d={geometry.ma5Path}
              fill="none"
              stroke={colors.amber}
              strokeWidth={1.35}
            />
          ) : null}

          {hasForecast ? (
            <>
              <Line
                stroke={colors.blueBright}
                strokeDasharray="4 4"
                strokeOpacity={0.7}
                x1={geometry.boundaryX}
                x2={geometry.boundaryX}
                y1={10}
                y2={geometry.priceBottom}
              />
              <SvgText
                fill={colors.navyMuted}
                fontSize={8}
                textAnchor="middle"
                x={geometry.boundaryX}
                y={geometry.priceBottom + 11}>
                现在 / 预测起点
              </SvgText>
            </>
          ) : null}

          {geometry.candles.map((candle) => {
            const candleColor =
              candle.direction === "up" ? colors.green : colors.red;
            return (
              <G key={candle.timestamp}>
                <Line
                  stroke={candleColor}
                  strokeWidth={1}
                  x1={candle.x}
                  x2={candle.x}
                  y1={candle.wickTop}
                  y2={candle.wickBottom}
                />
                <Rect
                  fill={candleColor}
                  height={candle.bodyHeight}
                  rx={0.6}
                  width={candle.bodyWidth}
                  x={candle.x - candle.bodyWidth / 2}
                  y={candle.bodyTop}
                />
                <Rect
                  fill={candleColor}
                  fillOpacity={0.45}
                  height={candle.volumeHeight}
                  width={candle.bodyWidth}
                  x={candle.volumeX}
                  y={candle.volumeY}
                />
              </G>
            );
          })}

          {geometry.participation.map((bar) =>
            bar.available ? (
              <G key={bar.timestamp} testID="participation-available">
                <Rect
                  fill={colors.blue}
                  height={bar.mainHeight}
                  testID="participation-main"
                  width={bar.width}
                  x={bar.x - bar.width / 2}
                  y={bar.top}
                />
                <Rect
                  fill={colors.navyMuted}
                  height={bar.retailHeight}
                  testID="participation-retail"
                  width={bar.width}
                  x={bar.x - bar.width / 2}
                  y={bar.top + bar.mainHeight}
                />
              </G>
            ) : (
              <Rect
                fill="none"
                height={bar.height}
                key={bar.timestamp}
                stroke={colors.navyMuted}
                strokeDasharray="2 2"
                strokeWidth={0.9}
                testID="participation-missing"
                width={bar.width}
                x={bar.x - bar.width / 2}
                y={bar.top}
              />
            ),
          )}

          {showMagicNine && lastCandle ? (
            <G>
              <Rect
                fill={colors.amber}
                height={17}
                rx={8.5}
                width={17}
                x={lastCandle.x - 8.5}
                y={Math.max(lastCandle.wickTop - 24, 2)}
              />
              <SvgText
                fill={colors.navy}
                fontSize={9}
                fontWeight="800"
                textAnchor="middle"
                x={lastCandle.x}
                y={Math.max(lastCandle.wickTop - 12, 14)}>
                {snapshot.magicNine.count}
              </SvgText>
            </G>
          ) : null}

          <Line
            stroke={colors.navyLine}
            strokeWidth={0.8}
            x1={8}
            x2={chartWidth - 38}
            y1={geometry.volumeTop}
            y2={geometry.volumeTop}
          />
        </Svg>
      </Pressable>

      <View
        accessibilityLabel={detailLabel ?? undefined}
        accessibilityLiveRegion="polite"
        accessible={detailLabel !== null}
        style={styles.detail}>
        {selectedCandle && detailLabel ? (
          <>
            <Text style={styles.detailPrimary}>
              {selectedCandle.timestamp} · O {selectedCandle.open.toFixed(2)} · H{" "}
              {selectedCandle.high.toFixed(2)} · L {selectedCandle.low.toFixed(2)} · C{" "}
              {selectedCandle.close.toFixed(2)} · V {selectedCandle.volume}
            </Text>
            <Text style={styles.detailSecondary}>
              {selectedParticipation?.qualityStatus === "live" &&
              selectedParticipation.mainShare !== null &&
              selectedParticipation.retailShare !== null
                ? `主力代理 ${(selectedParticipation.mainShare * 100).toFixed(2)}% · 散户代理 ${(selectedParticipation.retailShare * 100).toFixed(2)}% · 覆盖率 ${(selectedParticipation.coverage * 100).toFixed(2)}% · ${selectedParticipation.source}`
                : `活动占比缺失 · 覆盖率 ${((selectedParticipation?.coverage ?? 0) * 100).toFixed(2)}% · ${selectedParticipation?.source ?? snapshot.source.source} · ${selectedParticipation?.missingReason ?? "决策截止时不可用"}`}
            </Text>
            <Text style={styles.identity}>订单规模活动代理 · 非真实机构身份</Text>
          </>
        ) : (
          <>
            <Text style={styles.detailPrimary}>轻点或长按图表查看精确 K 线数据</Text>
            <Text style={styles.detailSecondary}>将显示 OHLCV、活动占比、覆盖率与来源</Text>
            <Text style={styles.identity}>订单规模活动代理 · 非真实机构身份</Text>
          </>
        )}
      </View>

      {showMagicNine || hasForecast ? (
        <View style={styles.footer}>
          {showMagicNine ? (
            <Text style={styles.nine}>
              {`九转 ${snapshot.magicNine.count} · ${
                snapshot.magicNine.completed ? "序列完成" : "尚未完成"
              }`}
            </Text>
          ) : (
            <View />
          )}
          {hasForecast ? (
            <Text style={styles.calibration}>
              50% / 80% 区间 · 校准误差{" "}
              {(snapshot.forecast!.calibrationError * 100).toFixed(1)}%
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
});

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.navy,
    borderColor: colors.navyLine,
    borderRadius: radius.lg,
    borderWidth: 1,
    gap: spacing.sm,
    overflow: "hidden",
    padding: spacing.md,
  },
  compactCard: {
    paddingBottom: spacing.sm,
  },
  header: {
    alignItems: "flex-start",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  eyebrow: {
    color: colors.navyEyebrow,
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 0.6,
  },
  title: {
    color: colors.card,
    fontSize: 14,
    fontWeight: "800",
    marginTop: 2,
  },
  probability: {
    alignItems: "flex-end",
  },
  probabilityValue: {
    color: colors.green,
    fontSize: 17,
    fontVariant: ["tabular-nums"],
    fontWeight: "900",
  },
  probabilityLabel: {
    color: colors.navyMuted,
    fontSize: 9,
    fontWeight: "700",
  },
  footer: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  nine: {
    color: colors.amber,
    fontSize: 10,
    fontWeight: "800",
  },
  calibration: {
    color: colors.navyMuted,
    fontSize: 9,
    fontWeight: "600",
  },
  chartPress: {
    justifyContent: "center",
  },
  chartPressed: {
    opacity: 0.88,
  },
  detail: {
    backgroundColor: colors.navyRaised,
    borderColor: colors.navyLine,
    borderRadius: radius.sm,
    borderWidth: 1,
    gap: spacing.xs,
    justifyContent: "center",
    minHeight: 86,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
  },
  detailPrimary: {
    color: colors.card,
    fontSize: 10,
    fontVariant: ["tabular-nums"],
    fontWeight: "700",
    lineHeight: 15,
  },
  detailSecondary: {
    color: colors.navyMuted,
    fontSize: 9,
    fontVariant: ["tabular-nums"],
    fontWeight: "600",
    lineHeight: 14,
  },
  identity: {
    color: colors.navyEyebrow,
    fontSize: 9,
    fontWeight: "700",
    lineHeight: 13,
  },
});
