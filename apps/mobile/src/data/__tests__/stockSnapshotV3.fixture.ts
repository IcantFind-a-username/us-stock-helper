const cutoff = "2026-07-25T15:59:50.000Z";

function unavailableSection(errorCode = "NOT_REQUESTED") {
  return {
    availabilityStatus: "unavailable",
    qualityStatus: "invalid",
    source: null,
    asOf: null,
    availableAt: null,
    receivedAt: null,
    data: null,
    errorCode,
    reason:
      errorCode === "NOT_REQUESTED"
        ? "此切片未请求该数据"
        : "此数据切片不可用",
    warnings: [] as string[],
    anomalies: [] as { code: string; reason: string; rowIndex?: number }[],
    methodVersion: "unavailable-v1",
  };
}

/** A literal schema-v3 response matching the gateway's public wire contract. */
export function stockSnapshotV3Fixture() {
  return {
    schemaVersion: "3",
    status: "partial",
    symbol: "NVDA",
    interval: "5m",
    count: 200,
    decisionCutoff: cutoff,
    requestedSections: [
      "quote",
      "candles",
      "technical",
      "currentSessionFlow",
      "holdings",
    ],
    sections: {
      quote: {
        availabilityStatus: "live",
        qualityStatus: "validated",
        source: "moomoo",
        asOf: "2026-07-25T15:59:48.000Z",
        availableAt: "2026-07-25T15:59:48.000Z",
        receivedAt: "2026-07-25T15:59:49.000Z",
        data: {
          price: 142.25,
          changePercent: 2.4,
          source: "moomoo",
          asOf: "2026-07-25T15:59:48.000Z",
          availableAt: "2026-07-25T15:59:48.000Z",
          methodVersion: "provider-quote-v1",
          qualityStatus: "live",
        },
        errorCode: null,
        reason: null,
        warnings: [] as string[],
        anomalies: [] as { code: string; reason: string; rowIndex?: number }[],
        methodVersion: "provider-quote-v1",
      },
      candles: {
        availabilityStatus: "live",
        qualityStatus: "validated",
        source: "moomoo",
        asOf: "2026-07-25T15:55:00.000Z",
        availableAt: "2026-07-25T15:55:01.000Z",
        receivedAt: "2026-07-25T15:55:02.000Z",
        data: {
          priceAdjustment: "forward-adjusted",
          candles: [
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
        },
        errorCode: null,
        reason: null,
        warnings: [] as string[],
        anomalies: [] as { code: string; reason: string; rowIndex?: number }[],
        methodVersion: "provider-completed-candle-v1",
      },
      technical: {
        availabilityStatus: "live",
        qualityStatus: "validated",
        source: "analysis-core",
        asOf: "2026-07-25T15:55:00.000Z",
        availableAt: cutoff,
        receivedAt: cutoff,
        data: {
          indicators: {
            ma5: {
              value: 140.8,
              source: "analysis-core",
              asOf: "2026-07-25T15:55:00.000Z",
              availableAt: cutoff,
              methodVersion: "sma-5-v1",
              qualityStatus: "live",
              series: [null, 140.8] as (number | null)[],
            },
            rsi: {
              value: 56.2,
              source: "analysis-core",
              asOf: "2026-07-25T15:55:00.000Z",
              availableAt: cutoff,
              methodVersion: "wilder-rsi-14-v1",
              qualityStatus: "live",
              series: [48.5, 56.2] as (number | null)[],
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
              lineSeries: [0.3, 0.45] as (number | null)[],
              signalSeries: [0.25, 0.3] as (number | null)[],
              histogramSeries: [0.05, 0.15] as (number | null)[],
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
            patternShapes: {
              source: "analysis-core",
              asOf: "2026-07-25T15:55:00.000Z",
              availableAt: cutoff,
              methodVersion: "patterns-shapes-v1",
              qualityStatus: "live",
              // Two candles is below every detector's own minimum window, so
              // each one reports its own typed-unavailable reason.
              detections: [
                {
                  detector: "fractal",
                  minimumWindow: 3,
                  sampleSize: 2,
                  qualityStatus: "unavailable",
                  missingReason: "完整K线不足 3 根，暂无法识别分型",
                  methodVersion: "patterns-shapes-v1",
                  signals: [] as unknown[],
                },
                {
                  detector: "double_extreme",
                  minimumWindow: 7,
                  sampleSize: 2,
                  qualityStatus: "unavailable",
                  missingReason: "完整K线不足 7 根，暂无法识别双重顶/底",
                  methodVersion: "patterns-shapes-v1",
                  signals: [] as unknown[],
                },
                {
                  detector: "head_and_shoulders",
                  minimumWindow: 8,
                  sampleSize: 2,
                  qualityStatus: "unavailable",
                  missingReason: "完整K线不足 8 根，暂无法识别头肩形态",
                  methodVersion: "patterns-shapes-v1",
                  signals: [] as unknown[],
                },
                {
                  detector: "ma5_pullback",
                  minimumWindow: 8,
                  sampleSize: 2,
                  qualityStatus: "unavailable",
                  missingReason: "完整K线不足 8 根，暂无法识别回踩五日线形态",
                  methodVersion: "patterns-shapes-v1",
                  signals: [] as unknown[],
                },
              ],
            },
          },
          magicNine: {
            direction: "bullish" as string | null,
            count: 2,
            series: [
              { direction: "bullish", count: 1 },
              { direction: "bullish", count: 2 },
            ] as ({ direction: string; count: number } | null)[],
            completed: false,
            perfected: false as boolean | null,
            confirmedAtIndex: null as number | null,
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
        errorCode: null,
        reason: null,
        warnings: [] as string[],
        anomalies: [] as { code: string; reason: string; rowIndex?: number }[],
        methodVersion: "analysis-core-indicators-v1",
      },
      currentSessionFlow: {
        availabilityStatus: "live",
        qualityStatus: "validated",
        source: "moomoo",
        asOf: "2026-07-25T15:55:00.000Z",
        availableAt: "2026-07-25T15:55:01.000Z",
        receivedAt: "2026-07-25T15:55:02.000Z",
        data: [
          {
            timestamp: "2026-07-25T15:50:00.000Z",
            availableAt: "2026-07-25T15:50:01.000Z",
            session: "2026-07-25",
            totalNetFlow: 2500,
            extraLargeOrderNetFlow: 1000,
            largeOrderNetFlow: 800,
            mediumOrderNetFlow: 500,
            smallOrderNetFlow: 200,
            largeOrderProxyNetFlow: 1800,
            institutionalIdentity: false as false,
          },
          {
            timestamp: "2026-07-25T15:55:00.000Z",
            availableAt: "2026-07-25T15:55:01.000Z",
            session: "2026-07-25",
            totalNetFlow: 3200,
            extraLargeOrderNetFlow: 1200,
            largeOrderNetFlow: 900,
            mediumOrderNetFlow: 700,
            smallOrderNetFlow: 400,
            largeOrderProxyNetFlow: 2100,
            institutionalIdentity: false as false,
          },
        ],
        errorCode: null,
        reason: null,
        warnings: [] as string[],
        anomalies: [] as { code: string; reason: string; rowIndex?: number }[],
        methodVersion: "provider-capital-flow-normalized-v1",
      },
      holdings: {
        availabilityStatus: "delayed",
        qualityStatus: "anomalous",
        source: "moomoo-delayed-institutional-disclosure",
        asOf: "2026-03-31T00:00:00.000Z",
        availableAt: "2026-05-15T00:00:00.000Z",
        receivedAt: "2026-07-25T15:55:02.000Z",
        data: [
          {
            period: "2026/Q1",
            reportedAt: "2026-03-31T00:00:00.000Z",
            reportedAtBasis: "reporting-period-end",
            availableAt: "2026-05-15T00:00:00.000Z",
            source: "moomoo-delayed-institutional-disclosure",
            institutionCount: 100,
            institutionCountChange: 2,
            sharesHeld: 2_000_000,
            sharesHeldChange: 100_000,
            holdingPercent: 345.937,
            holdingPercentChange: 0.4,
          },
        ],
        errorCode: null,
        reason: null,
        warnings: [
          "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释",
        ],
        anomalies: [
          {
            rowIndex: 0,
            code: "AGGREGATE_PERCENT_ABOVE_100",
            reason:
              "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释",
          },
        ],
        methodVersion: "reported-holdings-v2-anomaly-aware",
      },
      fundamentals: unavailableSection(),
      marketContext: unavailableSection(),
      news: unavailableSection(),
      forecastDecision: unavailableSection(),
    },
  };
}

/**
 * A schema-v3 payload built to distinguish two readings of the same served
 * flow data: diffing adjacent minute samples inside each candle's window
 * (the design doc's §7.3/§7.4 semantics and analysis_core's own
 * `_build_bar`), versus reading a single sample's session-cumulative
 * magnitude at the candle's close (the bug this fixture exists to catch).
 *
 * The four flow points below are cumulative-since-open magnitudes that only
 * ever grow. A decoder that (wrongly) reads the lone point at each candle's
 * close reports the whole session-to-date split on every candle after the
 * first: candle 52 would show ~33.3% main (100 of 300) and candle 53 would
 * show 60% main (300 of 500). A decoder that (correctly) diffs adjacent
 * points and aggregates only the delta inside each candle's one-minute
 * window reports 0% main on candle 52 and 100% main on candle 53 instead —
 * an opposite lean the cumulative reading can never produce, so a fixture
 * built from small hand-picked numbers cannot quietly pass under either
 * implementation.
 *
 * Quote, technical and holdings are marked unavailable throughout: this
 * fixture exists only to pin the candles/currentSessionFlow participation
 * math, and every other section would otherwise need its own candle-count-
 * matched series for no test this fixture backs.
 */
export function stockSnapshotV3ParticipationDeltaFixture() {
  function flow(
    minute: number,
    {
      extraLarge,
      large = 0,
      medium,
      small = 0,
    }: { extraLarge: number; large?: number; medium: number; small?: number },
  ) {
    const timestamp = `2026-07-25T15:${minute}:00.000Z`;
    return {
      timestamp,
      availableAt: `2026-07-25T15:${minute}:01.000Z`,
      session: "2026-07-25",
      totalNetFlow: extraLarge + large + medium + small,
      extraLargeOrderNetFlow: extraLarge,
      largeOrderNetFlow: large,
      mediumOrderNetFlow: medium,
      smallOrderNetFlow: small,
      largeOrderProxyNetFlow: extraLarge + large,
      institutionalIdentity: false as false,
    };
  }

  function candle(minute: number) {
    const timestamp = `2026-07-25T15:${minute}:00.000Z`;
    return {
      timestamp,
      complete: true,
      open: 140,
      high: 141,
      low: 139.5,
      close: 140.5,
      volume: 1000,
      source: "moomoo",
      asOf: timestamp,
      availableAt: `2026-07-25T15:${minute}:01.000Z`,
      receivedAt: `2026-07-25T15:${minute}:02.000Z`,
      priceAdjustment: "forward-adjusted" as const,
      methodVersion: "provider-completed-candle-v1",
      qualityStatus: "live",
    };
  }

  return {
    schemaVersion: "3",
    status: "partial",
    symbol: "NVDA",
    interval: "1m",
    count: 200,
    decisionCutoff: cutoff,
    requestedSections: [
      "quote",
      "candles",
      "technical",
      "currentSessionFlow",
      "holdings",
    ],
    sections: {
      quote: unavailableSection("QUOTE_UNAVAILABLE"),
      candles: {
        availabilityStatus: "live",
        qualityStatus: "validated",
        source: "moomoo",
        asOf: "2026-07-25T15:53:00.000Z",
        availableAt: "2026-07-25T15:53:01.000Z",
        receivedAt: "2026-07-25T15:53:02.000Z",
        data: {
          priceAdjustment: "forward-adjusted",
          candles: [candle(51), candle(52), candle(53)],
        },
        errorCode: null,
        reason: null,
        warnings: [] as string[],
        anomalies: [] as { code: string; reason: string; rowIndex?: number }[],
        methodVersion: "provider-completed-candle-v1",
      },
      technical: unavailableSection("TECHNICAL_UNAVAILABLE"),
      currentSessionFlow: {
        availabilityStatus: "live",
        qualityStatus: "validated",
        source: "moomoo",
        asOf: "2026-07-25T15:53:00.000Z",
        availableAt: "2026-07-25T15:53:01.000Z",
        receivedAt: "2026-07-25T15:53:02.000Z",
        data: [
          flow(50, { extraLarge: 0, medium: 0 }),
          flow(51, { extraLarge: 100, medium: 0 }),
          flow(52, { extraLarge: 100, medium: 200 }),
          flow(53, { extraLarge: 300, medium: 200 }),
        ],
        errorCode: null,
        reason: null,
        warnings: [] as string[],
        anomalies: [] as { code: string; reason: string; rowIndex?: number }[],
        methodVersion: "provider-capital-flow-normalized-v1",
      },
      holdings: unavailableSection("HOLDINGS_UNAVAILABLE"),
      fundamentals: unavailableSection(),
      marketContext: unavailableSection(),
      news: unavailableSection(),
      forecastDecision: unavailableSection(),
    },
  };
}
