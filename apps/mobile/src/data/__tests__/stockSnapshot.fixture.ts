const cutoff = "2026-07-25T15:59:50.000Z";

/**
 * A per-candle series as the gateway publishes it: one entry per completed
 * candle, null where the method has no value for that bar.
 */
/**
 * The gateway publishes a series as a bare array beside the indicator it
 * belongs to. Its source, timestamps, method version and quality are the
 * indicator's own — a second copy could only disagree with the first.
 */
export type SeriesPayload = (number | null)[];

export type MacdSeriesPayload = {
  line: (number | null)[];
  signal: (number | null)[];
  histogram: (number | null)[];
};

/** The same fixture once the gateway also publishes the drawable series. */
export function stockSnapshotWithSeriesFixture() {
  const payload = stockSnapshotFixture();
  payload.indicators.ma5.series = [null, 140.8];
  payload.indicators.rsi.series = [48.5, 56.2];
  payload.indicators.macd.series = {
    line: [0.3, 0.45],
    signal: [0.25, 0.3],
    histogram: [0.05, 0.15],
  };
  return payload;
}

export function stockSnapshotFixture() {
  return {
    schemaVersion: "2",
    source: "moomoo",
    sourceStatus: "live",
    symbol: "NVDA",
    interval: "5m",
    decisionCutoff: cutoff,
    priceAdjustment: "forward-adjusted",
    quote: {
      price: 142.25,
      changePercent: 2.4,
      source: "moomoo",
      asOf: "2026-07-25T15:59:48.000Z",
      availableAt: "2026-07-25T15:59:48.000Z",
      methodVersion: "provider-quote-v1",
      qualityStatus: "live",
    },
    completedCandles: [
      {
        timestamp: "2026-07-25T15:50:00.000Z",
        complete: true,
        open: 140,
        high: 141,
        low: 139.5,
        close: 140.5,
        volume: 1200,
        source: "moomoo",
        asOf: "2026-07-25T15:50:00.000Z",
        availableAt: "2026-07-25T15:50:01.000Z",
        receivedAt: "2026-07-25T15:50:02.000Z",
        priceAdjustment: "forward-adjusted",
        methodVersion: "provider-completed-candle-v1",
        qualityStatus: "live",
      },
      {
        timestamp: "2026-07-25T15:55:00.000Z",
        complete: true,
        open: 140.5,
        high: 142,
        low: 140,
        close: 141.5,
        volume: 1500,
        source: "moomoo",
        asOf: "2026-07-25T15:55:00.000Z",
        availableAt: "2026-07-25T15:55:01.000Z",
        receivedAt: "2026-07-25T15:55:02.000Z",
        priceAdjustment: "forward-adjusted",
        methodVersion: "provider-completed-candle-v1",
        qualityStatus: "live",
      },
    ],
    participationBars: [
      {
        closedAt: "2026-07-25T15:50:00.000Z",
        mainShare: 0.6,
        retailShare: 0.4,
        mainActivity: 60,
        retailActivity: 40,
        netFlow: 50,
        coverage: 1,
        source: "moomoo",
        asOf: "2026-07-25T15:50:00.000Z",
        availableAt: "2026-07-25T15:50:01.000Z",
        methodVersion: "order-size-activity-share-v1",
        qualityStatus: "live",
        missingReason: null,
      },
      {
        closedAt: "2026-07-25T15:55:00.000Z",
        mainShare: null,
        retailShare: null,
        mainActivity: null,
        retailActivity: null,
        netFlow: null,
        coverage: 0,
        source: "moomoo",
        asOf: "2026-07-25T15:55:00.000Z",
        availableAt: "2026-07-25T15:55:01.000Z",
        methodVersion: "order-size-activity-share-v1",
        qualityStatus: "unavailable",
        missingReason: "capital flow unavailable",
      },
    ],
    indicators: {
      ma5: {
        value: 140.8,
        source: "analysis-core",
        asOf: "2026-07-25T15:55:00.000Z",
        availableAt: cutoff,
        methodVersion: "sma-5-v1",
        qualityStatus: "live",
        series: undefined as SeriesPayload | undefined,
      },
      rsi: {
        value: 56.2,
        source: "analysis-core",
        asOf: "2026-07-25T15:55:00.000Z",
        availableAt: cutoff,
        methodVersion: "wilder-rsi-14-v1",
        qualityStatus: "live",
        series: undefined as SeriesPayload | undefined,
      },
      macd: {
        line: 0.45,
        signal: 0.3,
        histogram: 0.15,
        source: "analysis-core",
        asOf: "2026-07-25T15:55:00.000Z",
        availableAt: cutoff,
        methodVersion: "macd-12-26-9-v1",
        qualityStatus: "live",
        series: undefined as MacdSeriesPayload | undefined,
      },
      volatility: {
        value: 0.42 as number | null,
        sampleSize: 60,
        missingReason: null as string | null,
        source: "analysis-core",
        asOf: "2026-07-25T15:55:00.000Z",
        availableAt: cutoff,
        methodVersion: "close-to-close-realized-v1",
        qualityStatus: "live",
      },
      magicNine: {
        direction: "bullish",
        count: 2,
        series: [
          { direction: "bullish", count: 1 },
          { direction: "bullish", count: 2 },
        ] as ({ direction: string; count: number } | null)[],
        completed: false,
        perfected: false as boolean | null,
        confirmedAtIndex: null,
        lastCompleted: null as {
          direction: string;
          confirmedAtIndex: number;
          perfected: boolean;
          barsSince: number;
        } | null,
        source: "analysis-core",
        asOf: "2026-07-25T15:55:00.000Z",
        availableAt: cutoff,
        methodVersion: "td-setup-close-4-v2",
        qualityStatus: "live",
      },
    },
    institutionalHoldings: [
      {
        period: "2026-Q1",
        reportedAt: "2026-03-31T00:00:00.000Z",
        reportedAtBasis: "reporting-period-end",
        availableAt: "2026-05-15T00:00:00.000Z",
        source: "moomoo-delayed-institutional-disclosure",
        institutionCount: 100,
        institutionCountChange: 2,
        sharesHeld: 2000000,
        sharesHeldChange: 100000,
        holdingPercent: 12.5,
        holdingPercentChange: 0.4,
        asOf: "2026-03-31T00:00:00.000Z",
        methodVersion: "reported-holdings-v1",
        qualityStatus: "delayed",
      },
    ],
    provenance: [
      {
        source: "moomoo",
        asOf: "2026-07-25T15:59:48.000Z",
        availableAt: "2026-07-25T15:59:48.000Z",
        methodVersion: "provider-quote-v1",
        qualityStatus: "live",
      },
    ],
    warnings: ["Capital-flow participation is partially unavailable."],
  };
}
