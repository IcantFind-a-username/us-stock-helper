import { memo, useEffect, useMemo, useRef, useState } from "react";
import {
  type GestureResponderEvent,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";

import {
  toDemoChartSnapshot,
  type ChartMacdIndicator,
  type ChartSnapshot,
  type StockSnapshot,
} from "@/domain/models";
import {
  buildChartGeometry,
  findNearestByX,
  focusRatioForX,
  panChartWindow,
  resolveChartWidth,
  zoomChartWindow,
  type ChartOverlaySeries,
  type ChartPanelKey,
  type ChartWindow,
} from "@/domain/chart";
import {
  chartStatusLabel,
  intervalLabel,
  serviceTextLabel,
} from "@/i18n/serverVocabulary";
import { colors, radius, spacing } from "@/theme/tokens";

import { ChartCanvas, type MagicNineMarker } from "./ChartCanvas";
import { chartPalette } from "./chartPalette";
import { ChartLegend } from "./ChartLegend";
import { ChartReadout } from "./ChartReadout";
import { MagicNineMeter } from "./MagicNineMeter";

type PriceChartProps = {
  stock: ChartSnapshot | StockSnapshot;
  compact?: boolean;
  dataStatus?: "demo" | "live" | "stale";
  showForecast?: boolean;
  showMagicNine?: boolean;
  showMovingAverage?: boolean;
  showParticipation?: boolean;
  showMacd?: boolean;
  showRsi?: boolean;
};

/**
 * Reads the periods out of the method version rather than printing constants.
 *
 * "MACD(12,26,9)" is only true while the server computes it that way, so the
 * label comes from the version string it published; a version with no periods
 * in it gets no parenthesis instead of an invented one.
 */
function parameterLabel(methodVersion: string) {
  const periods = methodVersion.replace(/-v\d+$/, "").match(/\d+/g);
  return periods?.length ? `(${periods.join(",")})` : "";
}

function macdPanelLabel(macd: ChartMacdIndicator) {
  const parameters = parameterLabel(macd.methodVersion);
  if (macd.line === null || macd.signal === null) {
    return `MACD${parameters} 暂不可用`;
  }
  return `MACD${parameters} DIF ${macd.line.toFixed(2)} DEA ${macd.signal.toFixed(2)}`;
}

export const PriceChart = memo(function PriceChart({
  stock,
  compact = false,
  dataStatus,
  showForecast = true,
  showMagicNine = true,
  showMovingAverage = true,
  showParticipation = true,
  showMacd = true,
  showRsi = true,
}: PriceChartProps) {
  const { width: viewportWidth } = useWindowDimensions();
  const chartWidth = resolveChartWidth(viewportWidth);
  // The chart is the subject of this screen, so it takes the height a phone
  // can spare rather than sharing it with prose.
  const height = compact ? 380 : 460;
  const snapshot = useMemo(
    () => ("quote" in stock ? stock : toDemoChartSnapshot(stock)),
    [stock],
  );
  const resolvedStatus =
    dataStatus ??
    (snapshot.demoData
      ? "demo"
      : snapshot.source.status === "stale"
        ? "stale"
        : "live");
  const [selectedTimestamp, setSelectedTimestamp] = useState<string | null>(null);
  // null means nobody has touched the chart yet, so it keeps following the
  // newest bar as refreshes arrive. A gesture takes that over.
  const [visibleWindow, setVisibleWindow] = useState<ChartWindow | null>(null);
  const hasForecast = showForecast && snapshot.forecast !== null;

  const panels = useMemo(() => {
    const requested: ChartPanelKey[] = ["volume"];
    if (showMacd) requested.push("macd");
    if (showRsi) requested.push("rsi");
    if (showParticipation) requested.push("participation");
    return requested;
  }, [showMacd, showParticipation, showRsi]);

  const overlays = useMemo<ChartOverlaySeries[]>(() => {
    const ma5 = snapshot.indicators.ma5.series;
    // The line is only ever the server's own series: nothing here reads a
    // close and averages it.
    return showMovingAverage && ma5
      ? [{ key: "ma5", label: "MA5", values: ma5.values }]
      : [];
  }, [showMovingAverage, snapshot.indicators.ma5.series]);

  const geometry = useMemo(
    () =>
      buildChartGeometry({
        candles: snapshot.candles,
        forecast: hasForecast ? snapshot.forecast : null,
        participationBars: snapshot.participationBars,
        decisionCutoff: snapshot.source.decisionCutoff,
        width: chartWidth,
        height,
        panels,
        overlays,
        macdSeries: showMacd ? snapshot.indicators.macd.series : null,
        rsiSeries: showRsi ? snapshot.indicators.rsi.series : null,
        window: visibleWindow,
      }),
    [
      chartWidth,
      hasForecast,
      height,
      overlays,
      panels,
      showMacd,
      showRsi,
      snapshot.candles,
      snapshot.forecast,
      snapshot.indicators.macd.series,
      snapshot.indicators.rsi.series,
      snapshot.participationBars,
      snapshot.source.decisionCutoff,
      visibleWindow,
    ],
  );

  // Gestures need the window, the step and the plot edges as they are right
  // now, but they must not rebuild the gesture objects mid-drag; a ref carries
  // the current geometry across without re-attaching handlers.
  const viewport = useRef({
    window: geometry.window,
    step: geometry.step,
    plotLeft: geometry.plotLeft,
    plotRight: geometry.plotRight,
    // The zoom ceiling is solved from the drawing span, so it moves with the
    // width the chart was actually laid out at.
    width: chartWidth,
  });
  useEffect(() => {
    viewport.current = {
      window: geometry.window,
      step: geometry.step,
      plotLeft: geometry.plotLeft,
      plotRight: geometry.plotRight,
      width: chartWidth,
    };
  });

  const panStart = useRef<{
    window: ChartWindow;
    step: number;
    translationX: number;
  } | null>(null);
  const pinchStart = useRef<{
    window: ChartWindow;
    scale: number;
    focusRatio: number;
  } | null>(null);

  const gesture = useMemo(() => {
    // The chart redraws through React, so the handlers have to reach the JS
    // thread; there is no shared value a worklet could move on its own.
    const pan = Gesture.Pan()
      .withTestId("chart-pan")
      .runOnJS(true)
      .maxPointers(1)
      // A tap stays a tap and a vertical page scroll still wins.
      .activeOffsetX([-8, 8])
      .failOffsetY([-16, 16])
      .onBegin(() => {
        panStart.current = {
          window: viewport.current.window,
          step: viewport.current.step,
          translationX: 0,
        };
      })
      .onStart((event) => {
        // Measure from where the drag was recognised, so crossing the
        // activation threshold does not jump the window a bar or two.
        if (panStart.current) panStart.current.translationX = event.translationX;
      })
      .onUpdate((event) => {
        const start = panStart.current;
        if (!start || !(start.step > 0)) return;
        setVisibleWindow(
          panChartWindow({
            window: start.window,
            total: viewport.current.window.total,
            // Dragging right pulls earlier bars in, so the window walks back.
            barDelta: -(event.translationX - start.translationX) / start.step,
          }),
        );
      });

    const applyPinch = (scale: number) => {
      const start = pinchStart.current;
      if (!start) return;
      setVisibleWindow(
        zoomChartWindow({
          window: start.window,
          total: viewport.current.window.total,
          scale: scale / start.scale,
          focusRatio: start.focusRatio,
          width: viewport.current.width,
        }),
      );
    };
    const pinch = Gesture.Pinch()
      .withTestId("chart-pinch")
      .runOnJS(true)
      .onBegin((event) => {
        pinchStart.current = {
          window: viewport.current.window,
          scale: event.scale > 0 ? event.scale : 1,
          // The anchor is where the fingers landed; letting it follow their
          // drifting midpoint would pan and zoom at the same time.
          focusRatio: focusRatioForX({
            x: event.focalX,
            plotLeft: viewport.current.plotLeft,
            plotRight: viewport.current.plotRight,
          }),
        };
      })
      .onStart((event) => applyPinch(event.scale))
      .onUpdate((event) => applyPinch(event.scale));

    return Gesture.Simultaneous(pinch, pan);
  }, []);

  const magicNineAvailable = snapshot.magicNine.qualityStatus !== "unavailable";
  const markers = useMemo<MagicNineMarker[]>(() => {
    if (!showMagicNine) return [];
    const markerFor = (
      sourceIndex: number,
      key: string,
      testID: string,
      label: string,
      direction: "bullish" | "bearish" | null,
      mode: "badge" | "series" = "badge",
    ) => {
      // The server names the bar by its index in the snapshot's own candle
      // list. If the point-in-time window dropped that bar there is nothing
      // honest to point at, so nothing is drawn.
      const candle = geometry.candles.find(
        (entry) => entry.sourceIndex === sourceIndex,
      );
      return candle
        ? [
            {
              key,
              testID,
              x: candle.x,
              y:
                direction === "bullish"
                  ? Math.min(
                      candle.wickBottom + 11,
                      geometry.panels.price.bottom - 7,
                    )
                  : Math.max(
                      candle.wickTop - 11,
                      geometry.panels.price.top + 7,
                    ),
              label,
              direction,
              mode,
              labelTestID:
                mode === "series" ? "magic-nine-series-label" : undefined,
            },
          ]
        : [];
    };
    if (snapshot.magicNine.series) {
      return snapshot.magicNine.series.flatMap((point, sourceIndex) =>
        point
          ? markerFor(
              sourceIndex,
              `magic-nine-series-${sourceIndex}`,
              "magic-nine-series-marker",
              String(point.count),
              point.direction,
              "series",
            )
          : [],
      );
    }
    const current =
      magicNineAvailable && snapshot.magicNine.confirmedAtIndex !== null
        ? markerFor(
            snapshot.magicNine.confirmedAtIndex,
            "magic-nine-current",
            "magic-nine-marker",
            String(snapshot.magicNine.count),
            snapshot.magicNine.direction === "bullish" ||
              snapshot.magicNine.direction === "bearish"
              ? snapshot.magicNine.direction
              : null,
          )
        : [];
    const completed = snapshot.magicNine.lastCompleted
      ? markerFor(
          snapshot.magicNine.lastCompleted.confirmedAtIndex,
          "magic-nine-completed",
          "magic-nine-completed-marker",
          "9",
          snapshot.magicNine.lastCompleted.direction,
        )
      : [];
    return [...completed, ...current];
  }, [
    geometry.candles,
    geometry.panels.price.top,
    magicNineAvailable,
    showMagicNine,
    snapshot.magicNine.confirmedAtIndex,
    snapshot.magicNine.count,
    snapshot.magicNine.lastCompleted,
    snapshot.magicNine.series,
  ]);

  const missingNotes = useMemo(() => {
    const unpublished: string[] = [];
    const uncovered: string[] = [];
    const classify = (
      label: string,
      enabled: boolean,
      published: boolean,
      drawn: boolean,
    ) => {
      if (!enabled) return;
      if (!published) unpublished.push(label);
      else if (!drawn) uncovered.push(label);
    };
    classify(
      "MA5",
      showMovingAverage,
      snapshot.indicators.ma5.series !== null,
      geometry.overlays.some(({ key }) => key === "ma5"),
    );
    classify(
      "MACD",
      showMacd,
      snapshot.indicators.macd.series !== null,
      geometry.macd?.available === true,
    );
    classify(
      "RSI",
      showRsi,
      snapshot.indicators.rsi.series !== null,
      geometry.rsi?.available === true,
    );
    return [
      ...(unpublished.length
        ? [`${unpublished.join(" / ")} 曲线缺失 · 服务端未提供版本化序列`]
        : []),
      ...(uncovered.length
        ? [`${uncovered.join(" / ")} 曲线缺失 · 服务端序列尚未覆盖已绘制的 K 线`]
        : []),
    ];
  }, [
    geometry.macd?.available,
    geometry.overlays,
    geometry.rsi?.available,
    showMacd,
    showMovingAverage,
    showRsi,
    snapshot.indicators.ma5.series,
    snapshot.indicators.macd.series,
    snapshot.indicators.rsi.series,
  ]);

  const selectedCandle = selectedTimestamp
    ? snapshot.candles.find(({ timestamp }) => timestamp === selectedTimestamp)
    : undefined;
  const selectedParticipation =
    showParticipation && selectedTimestamp
      ? geometry.participation.find(
          ({ timestamp }) => timestamp === selectedTimestamp,
        )
      : undefined;
  const selectedX = selectedTimestamp
    ? (geometry.candles.find(
        ({ timestamp }) => timestamp === selectedTimestamp,
      )?.x ?? null)
    : null;

  const participationSummary = showParticipation
    ? `，${geometry.participation.filter(({ available }) => available).length} 根有订单规模活动占比`
    : "";
  // The count has to be the drawn count, and when bars are held back off screen
  // the reader is told how many and how to reach them.
  const windowSummary =
    geometry.window.total > geometry.candles.length
      ? `，共 ${geometry.window.total} 根，双指缩放或横向拖动查看其余`
      : "";
  const summary = `${snapshot.symbol} 图表摘要，${geometry.candles.length} 根已完成 K 线${windowSummary}，当前 ${snapshot.quote.price.toFixed(2)}，涨跌 ${snapshot.quote.changePercent >= 0 ? "上涨" : "下跌"} ${Math.abs(snapshot.quote.changePercent).toFixed(2)}%${participationSummary}；轻点或长按选择最近的 K 线`;
  const detailLabel = selectedCandle
    ? `${snapshot.symbol} 收盘时间 ${selectedCandle.timestamp}；开 ${selectedCandle.open.toFixed(2)}，高 ${selectedCandle.high.toFixed(2)}，低 ${selectedCandle.low.toFixed(2)}，收 ${selectedCandle.close.toFixed(2)}，成交量 ${selectedCandle.volume}${
        showParticipation
          ? `；${
              selectedParticipation?.available &&
              selectedParticipation.mainShare !== null &&
              selectedParticipation.retailShare !== null &&
              selectedParticipation.coverage !== null &&
              selectedParticipation.source !== null
                ? `主力代理 ${(selectedParticipation.mainShare * 100).toFixed(2)}%，散户代理 ${(selectedParticipation.retailShare * 100).toFixed(2)}%，覆盖率 ${(selectedParticipation.coverage * 100).toFixed(2)}%，来源 ${selectedParticipation.source}`
                : `活动占比缺失，${selectedParticipation?.coverage === null || selectedParticipation === undefined ? "覆盖率不可用" : `覆盖率 ${(selectedParticipation.coverage * 100).toFixed(2)}%`}，${selectedParticipation?.source ? `来源 ${selectedParticipation.source}` : "来源不可用"}，原因 ${selectedParticipation?.missingReason ? serviceTextLabel(selectedParticipation.missingReason) : "活动占比不可用"}`
            }；非真实机构身份`
          : ""
      }`
    : null;

  const selectNearestCandle = (event: GestureResponderEvent) => {
    if (!geometry.candles.length) return;
    const locationX = event.nativeEvent.locationX;
    const targetX = Number.isFinite(locationX) ? locationX : chartWidth;
    const nearest = findNearestByX(geometry.candles, targetX);
    if (nearest) setSelectedTimestamp(nearest.timestamp);
  };

  return (
    <View style={styles.card} testID="stock-chart-card">
      <View style={styles.header}>
        <Text style={styles.eyebrow}>
          {intervalLabel(snapshot.interval)} · {chartStatusLabel(resolvedStatus)}
        </Text>
        {hasForecast ? (
          <Text style={styles.probability}>
            上涨概率 {Math.round(snapshot.forecast!.probability.up * 100)}%
          </Text>
        ) : null}
      </View>

      <View style={styles.toolbar}>
        {showMagicNine ? <MagicNineMeter magicNine={snapshot.magicNine} /> : null}
        <ChartLegend
          overlays={geometry.overlays.map(({ key, label }) => ({ key, label }))}
          showForecast={hasForecast}
          showParticipation={showParticipation}
        />
      </View>

      <GestureDetector gesture={gesture}>
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
          <ChartCanvas
            geometry={geometry}
            height={height}
            macdLabel={macdPanelLabel(snapshot.indicators.macd)}
            markers={markers}
            rsiLabel={
              snapshot.indicators.rsi.value === null
                ? `RSI${parameterLabel(snapshot.indicators.rsi.methodVersion)} 暂不可用`
                : `RSI${parameterLabel(snapshot.indicators.rsi.methodVersion)} ${snapshot.indicators.rsi.value.toFixed(1)}`
            }
            selectedX={selectedX}
            showForecast={hasForecast}
            showParticipation={showParticipation}
            width={chartWidth}
          />
        </Pressable>
      </GestureDetector>

      <ChartReadout
        candle={selectedCandle}
        detailLabel={detailLabel}
        participation={selectedParticipation}
        showParticipation={showParticipation}
      />

      {missingNotes.length ? (
        <View style={styles.missing} testID="chart-series-missing">
          {missingNotes.map((note) => (
            <Text key={note} style={styles.missingText}>
              {note}
            </Text>
          ))}
        </View>
      ) : null}
    </View>
  );
});

const styles = StyleSheet.create({
  card: {
    // One source of truth for the chart's surface, so the palette cannot drift
    // back to a dark card sitting on a light page.
    backgroundColor: chartPalette.surface,
    borderColor: chartPalette.border,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    overflow: "hidden",
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.md,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: spacing.xs,
  },
  eyebrow: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
    letterSpacing: 0.6,
  },
  probability: {
    color: colors.green,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "900",
  },
  toolbar: {
    alignItems: "center",
    columnGap: spacing.md,
    flexDirection: "row",
    flexWrap: "wrap",
    paddingHorizontal: spacing.xs,
    rowGap: spacing.xs,
  },
  chartPress: { justifyContent: "center" },
  chartPressed: { opacity: 0.88 },
  missing: { gap: 2, paddingHorizontal: spacing.xs },
  missingText: { color: colors.muted, fontSize: 12, fontWeight: "700" },
});
