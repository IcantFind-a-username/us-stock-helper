import Svg, {
  G,
  Line,
  Path,
  Rect,
  Text as SvgText,
} from "react-native-svg";

import type { ChartGeometry } from "@/domain/chart";

import { chartPalette, overlayColor } from "./chartPalette";

export type MagicNineMarker = {
  key: string;
  testID: string;
  x: number;
  y: number;
  label: string;
};

type ChartCanvasProps = {
  geometry: ChartGeometry;
  width: number;
  height: number;
  showForecast: boolean;
  showParticipation: boolean;
  macdLabel: string;
  rsiLabel: string;
  markers: MagicNineMarker[];
  selectedX: number | null;
};

/**
 * Every panel shares one ordinal x axis, so a bar, its volume, its MACD column
 * and its participation lean all sit on the same vertical line.
 */
export function ChartCanvas({
  geometry,
  width,
  height,
  showForecast,
  showParticipation,
  macdLabel,
  rsiLabel,
  markers,
  selectedX,
}: ChartCanvasProps) {
  const { panels } = geometry;
  const gridRight = geometry.plotRight;
  const separators = [panels.volume, panels.macd, panels.rsi, panels.participation]
    .filter((panel): panel is NonNullable<typeof panel> => panel !== null)
    .map((panel) => panel.top);

  return (
    <Svg
      accessibilityElementsHidden
      accessible={false}
      height={height}
      importantForAccessibility="no-hide-descendants"
      viewBox={`0 0 ${width} ${height}`}
      width="100%">
      {geometry.priceTicks.map((tick) => (
        <G key={tick.label}>
          <Line
            stroke={chartPalette.grid}
            strokeDasharray="3 5"
            strokeWidth={0.7}
            x1={geometry.plotLeft}
            x2={gridRight}
            y1={tick.y}
            y2={tick.y}
          />
          <SvgText
            fill={chartPalette.axis}
            fontSize={9}
            textAnchor="end"
            x={width - 4}
            y={tick.y + 3}>
            {tick.label}
          </SvgText>
        </G>
      ))}

      {separators.map((top) => (
        <Line
          key={`separator-${top}`}
          stroke={chartPalette.grid}
          strokeWidth={0.8}
          x1={geometry.plotLeft}
          x2={gridRight}
          y1={top}
          y2={top}
        />
      ))}

      {/* A closed session is a boundary between bars, not a gap in the axis. */}
      {geometry.sessionBreaks.map((sessionBreak) => (
        <G key={`break-${sessionBreak.timestamp}`}>
          <Line
            stroke={chartPalette.grid}
            strokeWidth={0.9}
            x1={sessionBreak.x}
            x2={sessionBreak.x}
            y1={panels.price.top}
            y2={panels.axisY}
          />
          <SvgText
            fill={chartPalette.axis}
            fontSize={8}
            x={sessionBreak.x + 3}
            y={panels.price.top + 9}>
            {sessionBreak.label}
          </SvgText>
        </G>
      ))}

      {showForecast && geometry.band80 ? (
        <Path
          d={geometry.band80}
          fill={chartPalette.forecastWideBand}
          fillOpacity={0.16}
        />
      ) : null}
      {showForecast && geometry.band50 ? (
        <Path
          d={geometry.band50}
          fill={chartPalette.forecastBand}
          fillOpacity={0.2}
        />
      ) : null}
      {showForecast && geometry.medianPath ? (
        <Path
          d={geometry.medianPath}
          fill="none"
          stroke={chartPalette.forecastMedian}
          strokeDasharray="5 4"
          strokeWidth={1.6}
        />
      ) : null}
      {showForecast && geometry.forecastPoints.length ? (
        <Line
          stroke={chartPalette.forecastBand}
          strokeDasharray="4 4"
          strokeOpacity={0.7}
          x1={geometry.boundaryX}
          x2={geometry.boundaryX}
          y1={panels.price.top}
          y2={panels.price.bottom}
        />
      ) : null}

      {geometry.overlays.map((overlay) => (
        <Path
          d={overlay.path}
          fill="none"
          key={overlay.key}
          stroke={overlayColor(overlay.key)}
          strokeWidth={1.4}
          testID={`chart-overlay-${overlay.key}`}
        />
      ))}

      {geometry.candles.map((candle) => {
        const candleColor =
          candle.direction === "up" ? chartPalette.up : chartPalette.down;
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
            {panels.volume ? (
              <Rect
                fill={candleColor}
                fillOpacity={0.4}
                height={candle.volumeHeight}
                width={candle.bodyWidth}
                x={candle.volumeX}
                y={candle.volumeY}
              />
            ) : null}
          </G>
        );
      })}

      {geometry.macd ? (
        <G testID="macd-panel">
          <Line
            stroke={chartPalette.grid}
            strokeWidth={0.7}
            x1={geometry.plotLeft}
            x2={gridRight}
            y1={geometry.macd.zeroY}
            y2={geometry.macd.zeroY}
          />
          {geometry.macd.bars.map((bar, index) => (
            <Rect
              fill={bar.positive ? chartPalette.up : chartPalette.down}
              height={bar.height}
              key={`macd-${index}`}
              testID="macd-histogram-bar"
              width={bar.width}
              x={bar.x - bar.width / 2}
              y={bar.y}
            />
          ))}
          {geometry.macd.linePath ? (
            <Path
              d={geometry.macd.linePath}
              fill="none"
              stroke={chartPalette.macdLine}
              strokeWidth={1.2}
              testID="macd-dif-line"
            />
          ) : null}
          {geometry.macd.signalPath ? (
            <Path
              d={geometry.macd.signalPath}
              fill="none"
              stroke={chartPalette.macdSignal}
              strokeWidth={1.2}
              testID="macd-dea-line"
            />
          ) : null}
          <SvgText
            fill={chartPalette.panelLabel}
            fontSize={8}
            x={geometry.plotLeft + 2}
            y={geometry.macd.top + 9}>
            {macdLabel}
          </SvgText>
        </G>
      ) : null}

      {geometry.rsi ? (
        <G testID="rsi-panel">
          {geometry.rsi.references.map((reference) => (
            <G key={`rsi-${reference.value}`}>
              <Line
                stroke={chartPalette.grid}
                strokeDasharray={reference.value === 50 ? "2 4" : "4 4"}
                strokeWidth={0.7}
                x1={geometry.plotLeft}
                x2={gridRight}
                y1={reference.y}
                y2={reference.y}
              />
              {reference.value === 50 ? null : (
                <SvgText
                  fill={chartPalette.axis}
                  fontSize={8}
                  textAnchor="end"
                  x={width - 4}
                  y={reference.y + 3}>
                  {String(reference.value)}
                </SvgText>
              )}
            </G>
          ))}
          {geometry.rsi.path ? (
            <Path
              d={geometry.rsi.path}
              fill="none"
              stroke={chartPalette.rsiLine}
              strokeWidth={1.3}
              testID="rsi-line"
            />
          ) : null}
          <SvgText
            fill={chartPalette.panelLabel}
            fontSize={8}
            x={geometry.plotLeft + 2}
            y={geometry.rsi.top + 9}>
            {rsiLabel}
          </SvgText>
        </G>
      ) : null}

      {showParticipation && panels.participation ? (
        <G>
          <Line
            stroke={chartPalette.grid}
            strokeWidth={0.8}
            testID="participation-even-line"
            x1={geometry.plotLeft}
            x2={gridRight}
            y1={panels.participation.top + (panels.participation.bottom - panels.participation.top) / 2}
            y2={panels.participation.top + (panels.participation.bottom - panels.participation.top) / 2}
          />
          {geometry.participation.map((bar) =>
            bar.available ? (
              <G key={bar.timestamp} testID="participation-available">
                <Rect
                  fill={
                    bar.dominant === "retail"
                      ? chartPalette.retail
                      : bar.dominant === "main"
                        ? chartPalette.main
                        : chartPalette.even
                  }
                  height={Math.max(bar.markHeight, 0.8)}
                  testID={`participation-${bar.dominant}`}
                  width={bar.width}
                  x={bar.x - bar.width / 2}
                  y={bar.markY}
                />
              </G>
            ) : (
              // An unavailable bar keeps its slot and stays visibly empty; a
              // filled one would read as an even split that was measured.
              <Rect
                fill={chartPalette.grid}
                height={1.6}
                key={bar.timestamp}
                testID="participation-missing"
                width={bar.width}
                x={bar.x - bar.width / 2}
                y={bar.midY - 0.8}
              />
            ),
          )}
        </G>
      ) : null}

      {geometry.timeAxis.map((label) => (
        <SvgText
          fill={chartPalette.axis}
          fontSize={8.5}
          key={`time-${label.timestamp}`}
          testID={`chart-time-label:${label.label}`}
          textAnchor="middle"
          x={label.x}
          y={panels.axisY + 12}>
          {label.label}
        </SvgText>
      ))}

      {markers.map((marker) => (
        <G key={marker.key}>
          <Rect
            fill={chartPalette.magicNine}
            height={13}
            rx={3}
            testID={marker.testID}
            width={13}
            x={marker.x - 6.5}
            y={marker.y - 6.5}
          />
          <SvgText
            fill={chartPalette.surface}
            fontSize={8}
            fontWeight="800"
            textAnchor="middle"
            x={marker.x}
            y={marker.y + 3}>
            {marker.label}
          </SvgText>
        </G>
      ))}

      {selectedX === null ? null : (
        <Line
          stroke={chartPalette.crosshair}
          strokeDasharray="2 3"
          strokeOpacity={0.45}
          strokeWidth={0.9}
          testID="chart-crosshair"
          x1={selectedX}
          x2={selectedX}
          y1={panels.price.top}
          y2={panels.axisY}
        />
      )}
    </Svg>
  );
}
