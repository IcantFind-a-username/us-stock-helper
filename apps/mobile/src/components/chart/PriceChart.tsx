import { memo, useMemo } from "react";
import { StyleSheet, Text, useWindowDimensions, View } from "react-native";
import Svg, {
  G,
  Line,
  Path,
  Rect,
  Text as SvgText,
} from "react-native-svg";

import type { StockSnapshot } from "@/domain/models";
import { buildChartGeometry, resolveChartWidth } from "@/domain/chart";
import { colors, radius, spacing } from "@/theme/tokens";

import { ChartLegend } from "./ChartLegend";

type PriceChartProps = {
  stock: StockSnapshot;
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
  const chartForecast = useMemo(
    () =>
      showForecast
        ? stock.forecast
        : { ...stock.forecast, points: [] },
    [showForecast, stock.forecast],
  );
  const geometry = useMemo(
    () => buildChartGeometry(stock.candles, chartForecast, chartWidth, height),
    [chartForecast, chartWidth, height, stock.candles],
  );
  const lastCandle = geometry.candles.at(-1);
  const summary = `${stock.symbol} 蜡烛图，当前 ${stock.price.toFixed(2)}，涨跌 ${stock.changePercent > 0 ? "上涨" : "下跌"} ${Math.abs(stock.changePercent).toFixed(2)}%，预测上涨概率 ${Math.round(stock.forecast.probability.up * 100)}%，九转序号 ${stock.magicNine.count}`;

  return (
    <View
      accessibilityLabel={summary}
      style={[styles.card, compact ? styles.compactCard : null]}
      testID="stock-chart-card">
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>{stock.indicators.rsi.interval} · DEMO</Text>
          <Text style={styles.title}>价格 · 成交量 · 概率预测</Text>
        </View>
        {showForecast ? (
          <View style={styles.probability}>
            <Text style={styles.probabilityValue}>
              {Math.round(stock.forecast.probability.up * 100)}%
            </Text>
            <Text style={styles.probabilityLabel}>上涨概率</Text>
          </View>
        ) : null}
      </View>

      <ChartLegend
        showForecast={showForecast}
        showMovingAverage={showMovingAverage}
      />

      <Svg
        aria-hidden
        height={height}
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

        {showForecast && geometry.band80 ? (
          <Path d={geometry.band80} fill={colors.blueBright} fillOpacity={0.1} />
        ) : null}
        {showForecast && geometry.band50 ? (
          <Path d={geometry.band50} fill={colors.blue} fillOpacity={0.18} />
        ) : null}
        {showForecast && geometry.medianPath ? (
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

        {showForecast ? (
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
              y={height - 3}>
              现在 / 预测起点
            </SvgText>
          </>
        ) : null}

        {geometry.candles.map((candle, index) => {
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
              {stock.magicNine.count}
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

      {showMagicNine || showForecast ? (
        <View style={styles.footer}>
          {showMagicNine ? (
            <Text style={styles.nine}>
              {`九转 ${stock.magicNine.count} · ${
                stock.magicNine.complete ? "序列完成" : "尚未完成"
              }`}
            </Text>
          ) : <View />}
          {showForecast ? (
            <Text style={styles.calibration}>
              50% / 80% 区间 · 校准误差{" "}
              {(stock.forecast.calibrationError * 100).toFixed(1)}%
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
});
