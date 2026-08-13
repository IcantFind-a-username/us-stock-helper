import { colors } from "@/theme/tokens";

/**
 * The chart borrows the page's own surface rather than bringing a dark one.
 *
 * A dark chart card on a light page read as a foreign object dropped into the
 * screen, and it forced a second set of greys, borders and label colours that
 * matched nothing else. Everything here maps onto an existing token, so the
 * chart and the cards around it stay one surface.
 */
export const chartPalette = {
  surface: colors.card,
  border: colors.line,
  /**
   * Background ruling, a step lighter than the card border.
   *
   * The grid is there to be read against, not to be read: at the border's own
   * weight a full set of horizontal and vertical rules competes with 4pt
   * candle bodies for the reader's attention, and the bars stop being the ink.
   */
  grid: "#E8EDF3",
  /** Lines that carry a value: panel separators, MACD zero, session breaks. */
  axisLine: colors.line,
  axis: colors.muted,
  panelLabel: colors.muted,
  crosshair: colors.ink,
  /**
   * Candle ink, darker than the page's own green and red.
   *
   * Those tokens are tuned for pills and large filled areas; at a 4pt body over
   * a white card the pastel green measured 2.4:1 against the background, under
   * the 3:1 a small mark needs to hold its colour. These are the values the
   * approved K-line reference draws candles with.
   */
  up: "#13A96F",
  down: "#E0525B",
  /** Overlay lines, keyed by the series the server publishes. */
  overlay: {
    ma5: colors.amber,
    ma10: colors.blue,
    ma20: colors.purple,
  } as Record<string, string>,
  overlayFallback: colors.ink,
  macdLine: colors.blue,
  macdSignal: colors.amber,
  rsiLine: colors.purple,
  main: colors.blue,
  retail: colors.muted,
  even: colors.muted,
  forecastBand: colors.blue,
  forecastWideBand: colors.blueBright,
  forecastMedian: colors.purple,
  magicNine: colors.amber,
  magicNineBullish: colors.green,
  magicNineBearish: colors.red,
} as const;

export const overlayColor = (key: string) =>
  chartPalette.overlay[key] ?? chartPalette.overlayFallback;
