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
  grid: colors.line,
  axis: colors.muted,
  panelLabel: colors.muted,
  crosshair: colors.ink,
  up: colors.green,
  down: colors.red,
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
} as const;

export const overlayColor = (key: string) =>
  chartPalette.overlay[key] ?? chartPalette.overlayFallback;
