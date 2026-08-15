import type {
  Candle,
  ForecastSnapshot,
  ParticipationBar,
} from "./models";

export type CandleGeometry = {
  timestamp: string;
  /** Index in the snapshot's own candle list, which is how the server names bars. */
  sourceIndex: number;
  x: number;
  bodyWidth: number;
  bodyTop: number;
  bodyHeight: number;
  wickTop: number;
  wickBottom: number;
  direction: "up" | "down";
  volumeX: number;
  volumeY: number;
  volumeHeight: number;
};

export type ForecastGeometry = {
  x: number;
  medianY: number;
  lower50Y: number;
  upper50Y: number;
  lower80Y: number;
  upper80Y: number;
};

export type ParticipationGeometry = {
  timestamp: string;
  x: number;
  width: number;
  top: number;
  height: number;
  /** The even-split line the marks are read against. */
  midY: number;
  markY: number;
  markHeight: number;
  dominant: "main" | "retail" | "even" | null;
  available: boolean;
  mainShare: number | null;
  retailShare: number | null;
  coverage: number | null;
  source: string | null;
  missingReason: string | null;
};

export type ChartPanelKey = "volume" | "macd" | "rsi" | "participation";

export type PanelBounds = { top: number; bottom: number };

export type ChartPanels = {
  price: PanelBounds;
  volume: PanelBounds | null;
  macd: PanelBounds | null;
  rsi: PanelBounds | null;
  participation: PanelBounds | null;
  /** Baseline the time labels sit on, below every panel. */
  axisY: number;
};

/**
 * A series the server published, one value per candle in the same order.
 *
 * `null` means the method had no value for that bar — a warm-up window, not a
 * zero — so the line breaks there instead of being interpolated across it.
 */
export type ChartOverlaySeries = {
  key: string;
  label: string;
  values: (number | null)[];
};

export type ChartSeriesPoint = {
  /** Index into the point-in-time candles the geometry kept. */
  index: number;
  x: number;
  y: number;
  value: number;
};

export type ChartOverlayGeometry = {
  key: string;
  label: string;
  path: string;
  points: ChartSeriesPoint[];
};

export type ChartMacdSeriesInput = {
  line: (number | null)[];
  signal: (number | null)[];
  histogram: (number | null)[];
};

export type ChartMacdGeometry = PanelBounds & {
  available: boolean;
  zeroY: number;
  bars: { x: number; width: number; y: number; height: number; positive: boolean }[];
  linePath: string;
  signalPath: string;
};

export type ChartRsiSeriesInput = { values: (number | null)[] };

export type ChartRsiGeometry = PanelBounds & {
  available: boolean;
  path: string;
  points: ChartSeriesPoint[];
  references: { value: number; y: number }[];
};

export type ChartAxisLabel = {
  x: number;
  label: string;
  timestamp: string;
};

/** A window before it has been put on a series: bar counts, no pixels. */
export type ChartWindowSlice = { size: number; offset: number };

/**
 * The slice of the point-in-time series that is drawn.
 *
 * `offset` counts bars from the oldest point-in-time bar, so it survives a
 * zoom: the window keeps naming the same bars whatever the pixel width is.
 *
 * `total` is how many bars that offset was counted against, and it is what
 * makes the window re-anchorable. A live series grows while the chart is open,
 * so an offset alone names a different slice after every refresh: a window that
 * had been dragged onto the newest bar silently stopped being on the newest
 * bar, taking the forecast — only ever drawn where the series ends — with it.
 */
export type ChartWindow = ChartWindowSlice & { total: number };

export type ChartGeometryInput = {
  candles: Candle[];
  forecast: ForecastSnapshot | null;
  participationBars: ParticipationBar[];
  decisionCutoff: string;
  width: number;
  height: number;
  panels?: readonly ChartPanelKey[];
  overlays?: readonly ChartOverlaySeries[];
  macdSeries?: ChartMacdSeriesInput | null;
  rsiSeries?: ChartRsiSeriesInput | null;
  /** Omitted means the readable default window, anchored on the newest bar. */
  window?: ChartWindow | null;
};

export type ChartGeometry = {
  candles: CandleGeometry[];
  forecastPoints: ForecastGeometry[];
  participation: ParticipationGeometry[];
  overlays: ChartOverlayGeometry[];
  macd: ChartMacdGeometry | null;
  rsi: ChartRsiGeometry | null;
  timeAxis: ChartAxisLabel[];
  sessionBreaks: ChartAxisLabel[];
  panels: ChartPanels;
  /** Distance between two neighbouring bars; the axis is ordinal, not clock. */
  step: number;
  plotLeft: number;
  plotRight: number;
  boundaryX: number;
  band50: string;
  band80: string;
  medianPath: string;
  priceMin: number;
  priceMax: number;
  priceTicks: { label: string; y: number }[];
  window: ChartWindow;
};

const inset = { left: 8, right: 44, top: 14 } as const;
const axisHeight = 18;
const panelGap = 8;
const panelOrder: readonly ChartPanelKey[] = [
  "volume",
  "macd",
  "rsi",
  "participation",
];
const panelWeight: Record<ChartPanelKey, number> = {
  volume: 0.15,
  macd: 0.17,
  rsi: 0.17,
  participation: 0.09,
};
const panelMinimum: Record<ChartPanelKey, number> = {
  volume: 26,
  macd: 34,
  rsi: 34,
  participation: 18,
};
const dayMs = 86_400_000;

/**
 * The body width the default window is solved for.
 *
 * A body narrower than its own wick is not a candle: both are drawn in the
 * bar's colour, so at that density up and down stop reading. Three points
 * cleared the wick and nothing else — the bars still ran into each other. Four
 * points against a one-point wick, at the body-to-gap proportion below, is the
 * density the approved K-line reference draws at.
 */
export const minReadableBodyWidth = 4;
/** Pinched all the way in. Fewer bars than this is no longer a chart. */
export const minWindowBars = 30;
/**
 * Zoomed all the way out, a body may narrow to this but no further.
 *
 * Pinching out is a request for more history, not for a chart that can no
 * longer be read: at two pixels the body is still distinguishable from its
 * wick, and below that up and down stop reading — the same failure the
 * default window is solved away from. Earlier bars stay reachable by
 * dragging rather than by thinning every bar on screen.
 */
export const minZoomedOutBodyWidth = 2;

/**
 * Pinched all the way out. Derived from the density floor above rather than
 * chosen: a hand-picked 200 put the body back at one pixel on a 390pt phone,
 * which is where this whole exercise started.
 */
export function maxWindowBarsFor(width: number) {
  const { left, right } = plotBounds(width);
  return Math.max(
    minWindowBars,
    Math.floor((right - left) / (minZoomedOutBodyWidth / bodyWidthRatio)),
  );
}

/**
 * Body against slot, so a little under half of every slot stays empty.
 *
 * The gap is what separates one bar from the next; the approved K-line
 * reference draws a 12pt body on a 22pt slot, and at 0.62 the bodies were
 * closing that gap to under two points and reading as a solid block.
 */
const bodyWidthRatio = 0.55;
/** Few bars on a landscape chart get the reference's own body, not a slab. */
const maxBodyWidth = 12;

const clampNumber = (value: number, low: number, high: number) =>
  Math.min(Math.max(value, low), high);

const plotBounds = (width: number) => {
  const left = inset.left;
  return { left, right: Math.max(width - inset.right, left + 1) };
};

/**
 * The largest window whose bodies still clear {@link minReadableBodyWidth}.
 *
 * `reservedSlots` are the slots the forecast takes on the same ordinal axis:
 * they narrow every bar, so they have to be paid for out of the window.
 */
export function readableWindowSize(width: number, reservedSlots = 0) {
  const { left, right } = plotBounds(width);
  const affordable =
    Math.floor((right - left) / (minReadableBodyWidth / bodyWidthRatio)) -
    reservedSlots;
  return clampNumber(affordable, minWindowBars, maxWindowBarsFor(width));
}

const wholeBars = (value: number) =>
  Number.isFinite(value) ? Math.round(value) : 0;

/**
 * Fits a window to the data: whole bars, never wider than the series, never
 * scrolled past either end. The pinch limits are not applied here — a caller
 * that asks for an exact slice gets it, and only {@link zoomChartWindow}
 * enforces how far a finger may take it.
 *
 * An empty series yields an empty window rather than a one-bar one: "no bar
 * passed the decision cutoff" and "one bar is on screen" are different facts.
 */
export function clampChartWindow(
  window: ChartWindowSlice,
  total: number,
): ChartWindow {
  const series = Math.max(wholeBars(total), 0);
  const size = clampNumber(wholeBars(window.size), Math.min(1, series), series);
  return {
    size,
    offset: clampNumber(wholeBars(window.offset), 0, Math.max(series - size, 0)),
    total: series,
  };
}

/** Whether the window's right edge is sitting on the last bar it knows of. */
const followsLatest = (window: ChartWindow) =>
  window.offset + window.size >= window.total;

/**
 * Moves a window measured against one series length onto another.
 *
 * A window whose right edge was on the last bar belongs to a reader standing
 * at the live edge, so it keeps ending on the last bar as new ones close.
 * A window parked in history keeps the bars it was showing, because dragging
 * back to a particular hour is a request for that hour, not for whatever is
 * newest. Bars only ever arrive at the newest end of a point-in-time series,
 * which is what makes the second case a plain offset again.
 */
export function reanchorChartWindow(
  window: ChartWindow,
  total: number,
): ChartWindow {
  // A window can only have been measured against a series it fits inside, so a
  // recorded total shorter than the window itself is not one; its own extent
  // stands in, which leaves it at the live edge rather than collapsing it.
  const previous = clampChartWindow(
    window,
    Math.max(
      wholeBars(window.total),
      wholeBars(window.offset) + wholeBars(window.size),
    ),
  );
  return clampChartWindow(
    followsLatest(previous)
      ? { size: previous.size, offset: wholeBars(total) - previous.size }
      : previous,
    total,
  );
}

/**
 * Puts a window the reader left behind back on the chart being drawn now.
 *
 * The window outlives both the series it was cut from and the layout it was
 * pinched at: bars close while the chart is open, and a rotation hands the same
 * bar count a different span. Neither is consent to lose the live edge or to
 * draw hairlines, so a window that no longer fits is re-anchored and narrowed
 * rather than obeyed literally.
 */
export function resolveChartWindow({
  window,
  total,
  width,
  reservedSlots = 0,
}: {
  window: ChartWindow | null;
  total: number;
  width: number;
  /** Slots the forecast takes on the same axis; they narrow every bar. */
  reservedSlots?: number;
}): ChartWindow {
  const series = Math.max(wholeBars(total), 0);
  if (!window || !(window.size > 0)) {
    const size = readableWindowSize(width, reservedSlots);
    return clampChartWindow({ size, offset: series - size }, series);
  }
  const anchored = reanchorChartWindow(window, series);
  const affordable = maxWindowBarsFor(width);
  if (anchored.size <= affordable) return anchored;
  return clampChartWindow(
    {
      size: affordable,
      // Narrowing keeps the edge the reader was reading from: at the live edge
      // the newest bar stays on screen, in history the oldest bar in view does.
      offset: followsLatest(anchored) ? series - affordable : anchored.offset,
    },
    series,
  );
}

/**
 * Rescales the window around the pinch centre.
 *
 * `scale` is the gesture's own cumulative scale, so pinching apart (> 1) shows
 * fewer bars. The bar under `focusRatio` keeps its place under the fingers,
 * which is what makes a pinch feel like zooming rather than like re-cropping.
 * Offsets are whole bars, so the anchor can land up to half a bar off.
 */
export function zoomChartWindow({
  window,
  total,
  scale,
  focusRatio,
  width,
}: {
  window: ChartWindow;
  total: number;
  scale: number;
  focusRatio: number;
  width: number;
}): ChartWindow {
  const bounded = reanchorChartWindow(window, total);
  const ratio = clampNumber(Number.isFinite(focusRatio) ? focusRatio : 0.5, 0, 1);
  const safeScale = Number.isFinite(scale) && scale > 0 ? scale : 1;
  const size = clampNumber(
    Math.round(bounded.size / safeScale),
    minWindowBars,
    Math.min(maxWindowBarsFor(width), Math.max(bounded.total, 1)),
  );
  const focusBar = bounded.offset + ratio * bounded.size;
  return clampChartWindow(
    { size, offset: focusBar - ratio * size },
    bounded.total,
  );
}

/** Slides the window along the series; both ends are hard stops. */
export function panChartWindow({
  window,
  total,
  barDelta,
}: {
  window: ChartWindow;
  total: number;
  barDelta: number;
}): ChartWindow {
  const bounded = reanchorChartWindow(window, total);
  const delta = Number.isFinite(barDelta) ? barDelta : 0;
  return clampChartWindow(
    { size: bounded.size, offset: bounded.offset + delta },
    bounded.total,
  );
}

/** Where a touch sits across the plot, as a share of it. */
export function focusRatioForX({
  x,
  plotLeft,
  plotRight,
}: {
  x: number;
  plotLeft: number;
  plotRight: number;
}) {
  const span = plotRight - plotLeft;
  if (!(span > 0) || !Number.isFinite(x)) return 0.5;
  return clampNumber((x - plotLeft) / span, 0, 1);
}

const twoDigits = (value: number) => String(value).padStart(2, "0");

const clockLabel = (timestamp: number) => {
  const time = new Date(timestamp);
  return `${twoDigits(time.getUTCHours())}:${twoDigits(time.getUTCMinutes())}`;
};

const dateLabel = (timestamp: number) => {
  const time = new Date(timestamp);
  return `${twoDigits(time.getUTCMonth() + 1)}-${twoDigits(time.getUTCDate())}`;
};

const utcDay = (timestamp: number) => Math.floor(timestamp / dayMs);

/** How many multiples of `step` fall inside the drawn range. */
const levelsIn = (min: number, max: number, step: number) =>
  Math.floor(max / step + 1e-9) - Math.ceil(min / step - 1e-9) + 1;

/**
 * 1, 2, 2.5 or 5 × 10ⁿ: steps a reader adds up without doing arithmetic.
 *
 * The candidate is the one whose count of levels lands closest to what the
 * panel has room for, a tie going to the finer step — an extra line costs a
 * hairline, while too few make the reader interpolate. Rounding the step up to
 * the next round number instead ruled a two-dollar intraday window with a
 * single line, which is a price axis only in that it has a number on it.
 */
const niceStep = (min: number, max: number, target: number) => {
  const magnitude = 10 ** Math.floor(Math.log10((max - min) / target));
  const distance = (step: number) => Math.abs(levelsIn(min, max, step) - target);
  return [1, 2, 2.5, 5, 10]
    .map((factor) => factor * magnitude)
    .reduce((best, step) => (distance(step) < distance(best) ? step : best));
};

/** Just enough decimals to print the step exactly, so no two levels collide. */
const stepDecimals = (step: number) => {
  for (let digits = 0; digits < 6; digits += 1) {
    const scaled = step * 10 ** digits;
    if (Math.abs(scaled - Math.round(scaled)) < 1e-9) return digits;
  }
  return 6;
};

/**
 * Round price levels inside the drawn range, the way a paper chart is ruled.
 *
 * Dividing the panel into equal thirds labels whatever price happens to land
 * there — 141.37 against 143.62 — and the reader has to do the subtraction
 * themselves to place a bar between two lines.
 */
function priceAxisTicks(min: number, max: number, target: number) {
  const span = max - min;
  if (!(span > 0) || !(target > 0)) return [];
  const step = niceStep(min, max, target);
  const decimals = stepDecimals(step);
  const first = Math.ceil(min / step) * step;
  const levels: { value: number; label: string }[] = [];
  for (let index = 0; first + step * index <= max + step * 1e-9; index += 1) {
    const value = first + step * index;
    levels.push({ value, label: value.toFixed(decimals) });
  }
  // Highest first, so the ticks run down the panel the way they are drawn.
  return levels.reverse();
}

function layoutPanels(height: number, requested: readonly ChartPanelKey[]): ChartPanels {
  const active = panelOrder.filter((key) => requested.includes(key));
  const axisY = Math.max(height - axisHeight, inset.top + 1);
  const usable = Math.max(axisY - inset.top - panelGap * active.length, 1);
  const raw = active.map((key) =>
    Math.max(panelMinimum[key], height * panelWeight[key]),
  );
  const rawTotal = raw.reduce((total, value) => total + value, 0);
  // The price panel is the subject of the chart and the indicators are read
  // against it, so it always keeps the larger half of the stack; the rest
  // scale down together instead. At their own weights four sub-panels took
  // more of the frame than the bars they describe.
  const subtotalCap = usable * 0.42;
  const scale = rawTotal > subtotalCap ? subtotalCap / rawTotal : 1;
  const heights = raw.map((value) => value * scale);
  const priceHeight = usable - heights.reduce((total, value) => total + value, 0);

  const bounds: Partial<Record<ChartPanelKey, PanelBounds>> = {};
  let cursor = inset.top + priceHeight;
  const price: PanelBounds = { top: inset.top, bottom: cursor };
  active.forEach((key, index) => {
    const top = cursor + panelGap;
    const bottom = top + heights[index]!;
    bounds[key] = { top, bottom };
    cursor = bottom;
  });

  return {
    price,
    volume: bounds.volume ?? null,
    macd: bounds.macd ?? null,
    rsi: bounds.rsi ?? null,
    participation: bounds.participation ?? null,
    axisY,
  };
}

const emptyGeometry = (
  width: number,
  height: number,
  requested: readonly ChartPanelKey[],
  window: ChartWindow,
): ChartGeometry => {
  const { left: plotLeft, right: plotRight } = plotBounds(width);
  return {
    window,
    candles: [],
    forecastPoints: [],
    participation: [],
    overlays: [],
    macd: null,
    rsi: null,
    timeAxis: [],
    sessionBreaks: [],
    panels: layoutPanels(height, requested),
    step: plotRight - plotLeft,
    plotLeft,
    plotRight,
    boundaryX: plotLeft,
    band50: "",
    band80: "",
    medianPath: "",
    priceMin: 0,
    priceMax: 1,
    priceTicks: [],
  };
};

const linePath = (points: { x: number; y: number }[]) =>
  points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");

/** Joins runs of drawable points, starting a new subpath at every gap. */
const segmentedPath = (points: ChartSeriesPoint[]) => {
  let path = "";
  let previousIndex: number | null = null;
  points.forEach((point) => {
    const command = previousIndex !== null && point.index === previousIndex + 1 ? "L" : "M";
    path += `${path === "" ? "" : " "}${command} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
    previousIndex = point.index;
  });
  return path;
};

const bandPath = (
  points: ForecastGeometry[],
  upperKey: "upper50Y" | "upper80Y",
  lowerKey: "lower50Y" | "lower80Y",
) => {
  if (!points.length) return "";
  const upper = points.map((point) => ({ x: point.x, y: point[upperKey] }));
  const lower = [...points].reverse().map((point) => ({ x: point.x, y: point[lowerKey] }));
  return `${linePath(upper)} ${lower.map((point) => `L ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ")} Z`;
};

/**
 * A best-effort chart width from the viewport alone, before the chart's own
 * Pressable has actually been laid out.
 *
 * The chrome subtracted here is only ever an estimate: the card and screen
 * padding it approximates live in component styles that can change without
 * this function following, which is exactly how it went stale once already.
 * Hit-testing does not lean on this number's precision — once the Pressable
 * has measured itself, {@link alignTouchXToViewBox} reconciles whatever gap
 * is left between this guess and the real layout.
 */
export const resolveChartWidth = (viewportWidth: number) =>
  Math.min(Math.max(viewportWidth - 56, 304), 1_180);

/**
 * Maps an x from the Pressable's own layout frame into the SVG viewBox's
 * coordinate system.
 *
 * The canvas is told to render at `renderedWidth` (`width="100%"` of its
 * Pressable) while its content is authored at `chartWidth` (the viewBox).
 * Whenever those two widths differ — {@link resolveChartWidth}'s guess
 * drifting from the card's actual padding, a phone too narrow for the
 * readable-bar floor to fit — `preserveAspectRatio`'s default `xMidYMid meet`
 * scales and centres the drawing to reconcile them. A caller comparing a raw
 * touch x straight against viewBox-space candle positions is comparing across
 * that reconciliation as if it never happened; this undoes exactly the scale
 * and offset `meet` applied, so a touch lands on the candle under the finger
 * regardless of how — or why — the two widths came to differ.
 */
export function alignTouchXToViewBox({
  x,
  renderedWidth,
  chartWidth,
}: {
  /** The touch's x in the Pressable's own layout frame, e.g. `locationX`. */
  x: number;
  /** The Pressable's actual measured width, from its `onLayout`. */
  renderedWidth: number;
  /** The viewBox width geometry was built at. */
  chartWidth: number;
}): number {
  if (!(renderedWidth > 0) || !(chartWidth > 0) || !Number.isFinite(x)) {
    return x;
  }
  // Equal declared and rendered heights mean "meet" only ever scales by the
  // width ratio, and never past 1: a wider Pressable is letterboxed (scale 1,
  // centred), a narrower one is downscaled to fit (no residual letterboxing).
  const scale = Math.min(renderedWidth / chartWidth, 1);
  const offset = (renderedWidth - chartWidth * scale) / 2;
  return (x - offset) / scale;
}

export function findNearestByX<T extends { x: number }>(
  points: T[],
  targetX: number,
): T | undefined {
  return points.reduce<T | undefined>(
    (nearest, point) =>
      nearest === undefined ||
      Math.abs(point.x - targetX) < Math.abs(nearest.x - targetX)
        ? point
        : nearest,
    undefined,
  );
}

const finiteAt = (values: readonly (number | null)[] | undefined, index: number) => {
  const value = values?.[index];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
};

export function buildChartGeometry(input: ChartGeometryInput): ChartGeometry {
  const {
    candles,
    forecast,
    participationBars,
    decisionCutoff,
    width,
    height,
    panels: requestedPanels = ["volume"],
    overlays: overlayInputs = [],
    macdSeries = null,
    rsiSeries = null,
    window: requestedWindow = null,
  } = input;

  const decisionTime = Date.parse(decisionCutoff);
  const hasValidCutoff = Number.isFinite(decisionTime);
  // Every series the server sent is indexed against the candle list it came
  // with, so the source index travels with the bar through the point-in-time
  // filter and the visible window. Re-indexing after the fact would silently
  // shift an indicator onto the wrong candle.
  const decided = hasValidCutoff
    ? candles
        .map((candle, sourceIndex) => ({ candle, sourceIndex }))
        .filter(({ candle }) => {
          const availableAt = Date.parse(candle.availableAt);
          return (
            candle.complete &&
            Number.isFinite(availableAt) &&
            availableAt <= decisionTime
          );
        })
        .sort(
          (left, right) =>
            Date.parse(left.candle.timestamp) - Date.parse(right.candle.timestamp),
        )
    : [];
  const publishedForecast = forecast?.points ?? [];
  const totalBars = decided.length;
  // Every bar stays in memory to be dragged back into view; only the window is
  // turned into geometry, because that is what density costs.
  const window = resolveChartWindow({
    window: requestedWindow,
    total: totalBars,
    width,
    reservedSlots: publishedForecast.length,
  });
  const pointInTime = decided.slice(
    window.offset,
    window.offset + window.size,
  );
  const pointInTimeCandles = pointInTime.map(({ candle }) => candle);
  // The forecast continues from the newest bar. Dragged back into history it
  // has nothing to continue from, so it is not drawn there.
  const forecastPoints = followsLatest(window) ? publishedForecast : [];

  if (!pointInTimeCandles.length && !forecastPoints.length) {
    return emptyGeometry(width, height, requestedPanels, window);
  }

  const panels = layoutPanels(height, requestedPanels);
  const { left: plotLeft, right: plotRight } = plotBounds(width);
  // Ordinal axis: one slot per bar, closed sessions included nowhere. A time
  // axis would price the overnight gap into blank pixels the reader cannot use.
  const slots = pointInTimeCandles.length + forecastPoints.length;
  const step = (plotRight - plotLeft) / Math.max(slots, 1);
  const slotX = (slot: number) => plotLeft + step * (slot + 0.5);
  const bodyWidth = Math.max(1, Math.min(maxBodyWidth, step * bodyWidthRatio));

  const overlayValues = overlayInputs.map((overlay) => ({
    overlay,
    picked: pointInTime.map(({ sourceIndex }) => finiteAt(overlay.values, sourceIndex)),
  }));

  const allPrices = [
    ...pointInTimeCandles.flatMap(({ high, low }) => [high, low]),
    ...forecastPoints.flatMap(({ upper80, lower80 }) => [upper80, lower80]),
    ...overlayValues.flatMap(({ picked }) =>
      picked.filter((value): value is number => value !== null),
    ),
  ];
  const rawMin = Math.min(...allPrices);
  const rawMax = Math.max(...allPrices);
  const rawRange = Math.max(rawMax - rawMin, 1);
  const priceMin = rawMin - rawRange * 0.04;
  const priceMax = rawMax + rawRange * 0.04;
  const priceRange = priceMax - priceMin;
  const mapY = (price: number) =>
    panels.price.top +
    ((priceMax - price) / priceRange) * (panels.price.bottom - panels.price.top);

  const volumePanel = panels.volume;
  const maxVolume = Math.max(...pointInTimeCandles.map(({ volume }) => volume), 1);
  const candleGeometry = pointInTime.map(({ candle, sourceIndex }, index): CandleGeometry => {
    const x = slotX(index);
    const openY = mapY(candle.open);
    const closeY = mapY(candle.close);
    const volumeHeight = volumePanel
      ? ((volumePanel.bottom - volumePanel.top) * candle.volume) / maxVolume
      : 0;
    return {
      timestamp: candle.timestamp,
      sourceIndex,
      x,
      bodyWidth,
      bodyTop: Math.min(openY, closeY),
      bodyHeight: Math.max(Math.abs(closeY - openY), 1.8),
      wickTop: mapY(candle.high),
      wickBottom: mapY(candle.low),
      direction: candle.close >= candle.open ? "up" : "down",
      volumeX: x - bodyWidth / 2,
      volumeY: volumePanel ? volumePanel.bottom - volumeHeight : 0,
      volumeHeight,
    };
  });

  const overlays = overlayValues
    .map(({ overlay, picked }): ChartOverlayGeometry => {
      const points = picked.flatMap((value, index) =>
        value === null
          ? []
          : [{ index, x: candleGeometry[index]!.x, y: mapY(value), value }],
      );
      return {
        key: overlay.key,
        label: overlay.label,
        path: segmentedPath(points),
        points,
      };
    })
    .filter(({ points }) => points.length > 0);

  const participationByTimestamp = new Map(
    participationBars.map((bar) => [bar.closedAt, bar]),
  );
  const participationPanel = panels.participation;
  const participation = participationPanel
    ? candleGeometry.map((candle): ParticipationGeometry => {
        const bar = participationByTimestamp.get(candle.timestamp);
        const availableAt = bar ? Date.parse(bar.availableAt) : Number.NaN;
        const activityTotal =
          bar?.mainActivity != null && bar.retailActivity != null
            ? bar.mainActivity + bar.retailActivity
            : Number.NaN;
        const available =
          Number.isFinite(availableAt) &&
          availableAt <= decisionTime &&
          bar?.qualityStatus === "live" &&
          bar.mainShare !== null &&
          bar.retailShare !== null &&
          Number.isFinite(bar.mainShare) &&
          Number.isFinite(bar.retailShare) &&
          bar.mainShare >= 0 &&
          bar.retailShare >= 0 &&
          bar.mainShare + bar.retailShare === 1 &&
          bar.coverage === 1 &&
          bar.mainActivity !== null &&
          bar.retailActivity !== null &&
          bar.mainActivity >= 0 &&
          bar.retailActivity >= 0 &&
          Number.isFinite(activityTotal) &&
          activityTotal > 0 &&
          bar.mainShare === bar.mainActivity / activityTotal &&
          bar.retailShare === 1 - bar.mainShare;
        const approvedMissing =
          Number.isFinite(availableAt) &&
          availableAt <= decisionTime &&
          bar?.qualityStatus === "unavailable";
        const panelHeight = participationPanel.bottom - participationPanel.top;
        const midY = participationPanel.top + panelHeight / 2;
        // Read against an even split rather than stacked to full height: the
        // question is which side is doing the trading, and by how much.
        const lean = available ? bar.mainShare! - 0.5 : 0;
        const markHeight = Math.abs(lean) * panelHeight;
        return {
          timestamp: candle.timestamp,
          x: candle.x,
          width: candle.bodyWidth,
          top: participationPanel.top,
          height: panelHeight,
          midY,
          markY: lean >= 0 ? midY - markHeight : midY,
          markHeight,
          dominant: !available ? null : lean > 0 ? "main" : lean < 0 ? "retail" : "even",
          available,
          mainShare: available ? bar.mainShare : null,
          retailShare: available ? bar.retailShare : null,
          coverage: available || approvedMissing ? bar.coverage : null,
          source: available || approvedMissing ? bar.source : null,
          missingReason: available
            ? null
            : approvedMissing
              ? bar.missingReason
              : bar
                ? "决策截止时不可用"
                : "活动占比不可用",
        };
      })
    : [];

  const macdPanel = panels.macd;
  const macd: ChartMacdGeometry | null = macdPanel
    ? (() => {
        const picked = pointInTime.map(({ sourceIndex }) => ({
          line: finiteAt(macdSeries?.line, sourceIndex),
          signal: finiteAt(macdSeries?.signal, sourceIndex),
          histogram: finiteAt(macdSeries?.histogram, sourceIndex),
        }));
        const magnitudes = picked.flatMap(({ line, signal, histogram }) =>
          [line, signal, histogram].filter(
            (value): value is number => value !== null,
          ),
        );
        const panelHeight = macdPanel.bottom - macdPanel.top;
        const zeroY = macdPanel.top + panelHeight / 2;
        const bound = Math.max(...magnitudes.map(Math.abs), Number.EPSILON);
        const mapMacdY = (value: number) =>
          zeroY - (value / bound) * (panelHeight / 2 - 2);
        const bars = picked.flatMap(({ histogram }, index) => {
          if (histogram === null) return [];
          const y = mapMacdY(histogram);
          const size = Math.max(Math.abs(zeroY - y), 0.6);
          return [
            {
              x: candleGeometry[index]!.x,
              width: bodyWidth,
              y: histogram >= 0 ? zeroY - size : zeroY,
              height: size,
              positive: histogram >= 0,
            },
          ];
        });
        const seriesPoints = (key: "line" | "signal") =>
          picked.flatMap((entry, index) =>
            entry[key] === null
              ? []
              : [
                  {
                    index,
                    x: candleGeometry[index]!.x,
                    y: mapMacdY(entry[key]!),
                    value: entry[key]!,
                  },
                ],
          );
        return {
          ...macdPanel,
          available: magnitudes.length > 0,
          zeroY,
          bars,
          linePath: segmentedPath(seriesPoints("line")),
          signalPath: segmentedPath(seriesPoints("signal")),
        };
      })()
    : null;

  const rsiPanel = panels.rsi;
  const rsi: ChartRsiGeometry | null = rsiPanel
    ? (() => {
        const panelHeight = rsiPanel.bottom - rsiPanel.top;
        // RSI is defined on a fixed 0–100 scale, so the reference lines are the
        // indicator's own definition, not something read off the data.
        const mapRsiY = (value: number) =>
          rsiPanel.top + ((100 - value) / 100) * panelHeight;
        const points = pointInTime.flatMap(({ sourceIndex }, index) => {
          const value = finiteAt(rsiSeries?.values, sourceIndex);
          return value === null
            ? []
            : [{ index, x: candleGeometry[index]!.x, y: mapRsiY(value), value }];
        });
        return {
          ...rsiPanel,
          available: points.length > 0,
          path: segmentedPath(points),
          points,
          references: [70, 50, 30].map((value) => ({ value, y: mapRsiY(value) })),
        };
      })()
    : null;

  const forecastGeometry = forecastPoints.map((point, index): ForecastGeometry => {
    const x = slotX(pointInTimeCandles.length + index);
    return {
      x,
      medianY: mapY(point.median),
      lower50Y: mapY(point.lower50),
      upper50Y: mapY(point.upper50),
      lower80Y: mapY(point.lower80),
      upper80Y: mapY(point.upper80),
    };
  });

  // One rule every 50 points or so: closer and the labels crowd each other,
  // further apart and the reader is interpolating across a third of the panel.
  const tickTarget = clampNumber(
    Math.round((panels.price.bottom - panels.price.top) / 50),
    3,
    6,
  );
  const priceTicks = priceAxisTicks(priceMin, priceMax, tickTarget).map(
    ({ value, label }) => ({ label, y: mapY(value) }),
  );

  const times = pointInTimeCandles.map(({ timestamp }) => Date.parse(timestamp));
  const deltas = times.slice(1).map((time, index) => time - times[index]!).sort((a, b) => a - b);
  const medianDelta = deltas.length ? deltas[Math.floor(deltas.length / 2)]! : null;
  const intraday = medianDelta === null || medianDelta < dayMs;
  const labelBudget = clampNumber(
    Math.round((plotRight - plotLeft) / 64),
    2,
    6,
  );
  const labelIndices =
    times.length <= labelBudget
      ? times.map((_, index) => index)
      : Array.from(
          new Set(
            // Half a slot in from each end: a label centred on the first or the
            // last bar hangs off the plot and is clipped by the price gutter,
            // and a clipped time is worse than one bar further in.
            Array.from({ length: labelBudget }, (_, slot) =>
              Math.round(((slot + 0.5) / labelBudget) * (times.length - 1)),
            ),
          ),
        );
  const timeAxis: ChartAxisLabel[] = labelIndices.map((index) => ({
    x: candleGeometry[index]!.x,
    // Ordinal spacing, real clock: the reader still has to know which bar is
    // which hour, they just should not pay plot width for the closed session.
    label: intraday ? clockLabel(times[index]!) : dateLabel(times[index]!),
    timestamp: pointInTimeCandles[index]!.timestamp,
  }));
  const sessionBreaks: ChartAxisLabel[] = intraday
    ? times.flatMap((time, index) =>
        index > 0 && utcDay(time) !== utcDay(times[index - 1]!)
          ? [
              {
                x: candleGeometry[index]!.x - step / 2,
                label: dateLabel(time),
                timestamp: pointInTimeCandles[index]!.timestamp,
              },
            ]
          : [],
      )
    : [];

  return {
    window,
    candles: candleGeometry,
    forecastPoints: forecastGeometry,
    participation,
    overlays,
    macd,
    rsi,
    timeAxis,
    sessionBreaks,
    panels,
    step,
    plotLeft,
    plotRight,
    boundaryX: plotLeft + step * pointInTimeCandles.length,
    band50: bandPath(forecastGeometry, "upper50Y", "lower50Y"),
    band80: bandPath(forecastGeometry, "upper80Y", "lower80Y"),
    medianPath: linePath(forecastGeometry.map((point) => ({ x: point.x, y: point.medianY }))),
    priceMin,
    priceMax,
    priceTicks,
  };
}
