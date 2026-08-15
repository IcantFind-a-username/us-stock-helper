import { describe, expect, it, jest } from "@jest/globals";

import { toDemoChartSnapshot, type WatchlistQuote } from "@/domain/models";
import { stockFixtures } from "@/fixtures/stocks";
import {
  createMarketGatewayClient,
  decodeCandleEnvelope,
  decodeStockSnapshotEnvelope,
  decodeStockSnapshotV3Envelope,
  decodeWatchlistEnvelope,
  GatewayClientUpdateRequiredError,
  GatewayRequestError,
  GatewaySnapshotUnavailableError,
} from "../marketGateway";
import {
  stockSnapshotFixture,
  stockSnapshotWithSeriesFixture,
} from "./stockSnapshot.fixture";
import { stockSnapshotV3Fixture } from "./stockSnapshotV3.fixture";

const now = new Date("2026-07-25T16:00:00.000Z");
const aggregateHoldingsReason =
  "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释";
const fallback: WatchlistQuote[] = [
  {
    symbol: "NVDA",
    price: 141.3,
    changePercent: 1.2,
    direction: "bullish",
    summary: "演示回退",
  },
];

function jsonResponse(value: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => value,
  } as Response;
}

describe("market gateway point-in-time validation", () => {
  it("accepts a fresh healthy moomoo watchlist without mixing fixture rows", () => {
    const result = decodeWatchlistEnvelope(
      {
        schemaVersion: "1",
        source: "moomoo",
        session: "healthy",
        asOf: "2026-07-25T15:59:50.000Z",
        availableAt: "2026-07-25T15:59:51.000Z",
        items: [
          {
            code: "US.NVDA",
            price: 142.25,
            changePercent: 2.4,
            availableAt: "2026-07-25T15:59:49.000Z",
          },
        ],
      },
      { maxAgeMs: 30_000, now },
    );

    expect(result.source).toBe("moomoo");
    expect(result.quotes).toEqual([
      {
        symbol: "NVDA",
        price: 142.25,
        changePercent: 2.4,
        direction: "bullish",
        summary: "实时只读",
      },
    ]);
  });

  it.each([
    ["behind", "2026-07-25T15:58:00.000Z"],
    ["ahead", "2026-07-25T18:00:00.000Z"],
  ])("accepts a server-consistent watchlist when the device clock is %s", (_label, deviceNow) => {
    expect(() =>
      decodeWatchlistEnvelope(
        {
          schemaVersion: "1",
          source: "moomoo",
          session: "healthy",
          asOf: "2026-07-25T16:00:03.000Z",
          availableAt: "2026-07-25T16:00:04.000Z",
          items: [],
        },
        { now: new Date(deviceNow) },
      ),
    ).not.toThrow();
  });

  it("rejects a watchlist whose top-level server timestamps are incoherent", () => {
    expect(() =>
      decodeWatchlistEnvelope(
        {
          schemaVersion: "1",
          source: "moomoo",
          session: "healthy",
          asOf: "2026-07-25T16:00:04.001Z",
          availableAt: "2026-07-25T16:00:04.000Z",
          items: [],
        },
        { now },
      ),
    ).toThrow();
  });

  it("rejects fixture-labelled, unhealthy, malformed, and mixed-time live responses", () => {
    const base = {
      schemaVersion: "1",
      source: "moomoo",
      session: "healthy",
      asOf: "2026-07-25T15:59:50.000Z",
      availableAt: "2026-07-25T15:59:51.000Z",
      items: [],
    };

    expect(() => decodeWatchlistEnvelope({ ...base, source: "fixture" }, { now })).toThrow();
    expect(() => decodeWatchlistEnvelope({ ...base, session: "login-required" }, { now })).toThrow();
    expect(() => decodeWatchlistEnvelope({ ...base, items: [{ code: "US.NVDA" }] }, { now })).toThrow();
    expect(() =>
      decodeWatchlistEnvelope(
        {
          ...base,
          items: [
            {
              code: "US.NVDA",
              price: 142,
              changePercent: 1,
              availableAt: "2026-07-25T16:00:01.000Z",
            },
          ],
        },
        { now },
      ),
    ).toThrow();
  });

  it("only accepts completed candles available by the response cutoff", () => {
    const valid = {
      schemaVersion: "1",
      source: "moomoo",
      session: "healthy",
      asOf: "2026-07-25T15:59:50.000Z",
      availableAt: "2026-07-25T15:59:51.000Z",
      symbol: "NVDA",
      interval: "5m",
      items: [
        {
          timestamp: "2026-07-25T15:55:00.000Z",
          availableAt: "2026-07-25T15:55:01.000Z",
          complete: true,
          open: 140,
          high: 142,
          low: 139.5,
          close: 141.5,
          volume: 1200,
        },
      ],
    };

    expect(decodeCandleEnvelope(valid, { now }).candles).toHaveLength(1);
    expect(() =>
      decodeCandleEnvelope(
        {
          ...valid,
          items: [{ ...valid.items[0], complete: false }],
        },
        { now },
      ),
    ).toThrow();
    expect(() =>
      decodeCandleEnvelope(
        {
          ...valid,
          items: [
            {
              ...valid.items[0],
              availableAt: "2026-07-25T16:00:01.000Z",
            },
          ],
        },
        { now },
      ),
    ).toThrow();
  });
});

describe("schema-v2 stock snapshot validation", () => {
  it("decodes a cutoff-consistent live snapshot without demo fields", () => {
    const result = decodeStockSnapshotEnvelope(stockSnapshotFixture(), { now });

    expect(result).toMatchObject({
      demoData: false,
      symbol: "NVDA",
      interval: "5m",
      forecast: null,
      source: {
        source: "moomoo",
        status: "live",
        decisionCutoff: "2026-07-25T15:59:50.000Z",
      },
      quote: { price: 142.25, changePercent: 2.4 },
      participationBars: [
        { closedAt: "2026-07-25T15:50:00.000Z", mainShare: 0.6, retailShare: 0.4 },
        {
          closedAt: "2026-07-25T15:55:00.000Z",
          mainShare: null,
          retailShare: null,
          missingReason: "capital flow unavailable",
        },
      ],
      institutionalHoldings: [
        { qualityStatus: "delayed", reportedAt: "2026-03-31T00:00:00.000Z" },
      ],
      warnings: ["Capital-flow participation is partially unavailable."],
    });
    expect(result.candles.map((candle) => candle.timestamp)).toEqual([
      "2026-07-25T15:50:00.000Z",
      "2026-07-25T15:55:00.000Z",
    ]);
  });

  it.each([
    ["behind", "2026-07-25T15:00:00.000Z"],
    ["ahead", "2026-07-25T18:00:00.000Z"],
  ])("accepts a cutoff-consistent snapshot when the device clock is %s", (_label, deviceNow) => {
    expect(() =>
      decodeStockSnapshotEnvelope(stockSnapshotFixture(), {
        now: new Date(deviceNow),
      }),
    ).not.toThrow();
  });

  it.each([
    ["future candle", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.completedCandles[1]!.availableAt = "2026-07-25T16:00:01.000Z";
    }],
    ["future quote", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.decisionCutoff = "2026-07-25T16:00:00.000Z";
      value.quote.availableAt = "2026-07-25T16:00:00.001Z";
    }],
    ["future indicator", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.decisionCutoff = "2026-07-25T16:00:00.000Z";
      value.indicators.rsi.availableAt = "2026-07-25T16:00:00.001Z";
    }],
    ["future provenance", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.decisionCutoff = "2026-07-25T16:00:00.000Z";
      value.provenance[0]!.availableAt = "2026-07-25T16:00:00.001Z";
    }],
    ["duplicate candle", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.completedCandles[1]!.timestamp = value.completedCandles[0]!.timestamp;
    }],
    ["out-of-order candle", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.completedCandles[1]!.timestamp = "2026-07-25T15:45:00.000Z";
    }],
    ["unsupported candle method", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.completedCandles[0]!.methodVersion = "guessed-v1";
    }],
    ["misaligned participation", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.participationBars[1]!.closedAt = "2026-07-25T15:54:00.000Z";
    }],
    ["institution identity claim", (value: ReturnType<typeof stockSnapshotFixture>) => {
      (value.participationBars[0] as Record<string, unknown>).institutionalIdentity = true;
    }],
    ["invalid participation shares", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.participationBars[0]!.retailShare = 0.5;
    }],
    ["unsupported participation method", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.participationBars[0]!.methodVersion = "guessed-v1";
    }],
    ["fixture masquerading as live", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.source = "fixture";
    }],
    ["fixture provenance", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.provenance[0]!.source = "fixture";
    }],
  ])("rejects a %s snapshot", (_label, mutate) => {
    const value = stockSnapshotFixture();
    mutate(value);

    expect(() => decodeStockSnapshotEnvelope(value, { maxAgeMs: 30_000, now })).toThrow();
  });

  it.each([
    ["partial coverage", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.participationBars[0]!.coverage = 0.9999999999999999;
    }],
    ["negative activity", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.participationBars[0]!.mainActivity = -1;
    }],
    ["zero activity", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.participationBars[0]!.mainActivity = 0;
      value.participationBars[0]!.retailActivity = 0;
      value.participationBars[0]!.mainShare = 0.5;
      value.participationBars[0]!.retailShare = 0.5;
    }],
    ["overflowing activity", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.participationBars[0]!.mainActivity = 1e308;
      value.participationBars[0]!.retailActivity = 1e308;
      value.participationBars[0]!.mainShare = 0;
      value.participationBars[0]!.retailShare = 1;
    }],
    ["shares unrelated to activity", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.participationBars[0]!.mainActivity = 70;
      value.participationBars[0]!.retailActivity = 30;
    }],
    ["tiny non-complement share", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.participationBars[0]!.mainShare = 0.6000000001;
    }],
  ])("rejects live participation with %s", (_label, mutate) => {
    const value = stockSnapshotFixture();
    mutate(value);

    expect(() => decodeStockSnapshotEnvelope(value, { now })).toThrow();
  });

  it("carries realized volatility with its sample size", () => {
    const snapshot = decodeStockSnapshotEnvelope(stockSnapshotFixture(), { now });

    expect(snapshot.indicators.volatility).toMatchObject({
      value: 0.42,
      sampleSize: 60,
      qualityStatus: "live",
      missingReason: null,
      methodVersion: "close-to-close-realized-v1",
    });
  });

  it("keeps an unavailable volatility null instead of guessing a default", () => {
    const value = stockSnapshotFixture();
    value.indicators.volatility.value = null;
    value.indicators.volatility.qualityStatus = "unavailable";
    value.indicators.volatility.missingReason = "insufficient sample: 3 of 20 returns";

    const snapshot = decodeStockSnapshotEnvelope(value, { now });

    expect(snapshot.indicators.volatility.value).toBeNull();
    expect(snapshot.indicators.volatility.missingReason).toContain("sample");
  });

  it.each([
    ["a live volatility with no value", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.indicators.volatility.value = null;
    }],
    ["a live volatility carrying a missing reason", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.indicators.volatility.missingReason = "why";
    }],
    ["a non-positive volatility", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.indicators.volatility.value = 0;
    }],
    ["a negative sample size", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.indicators.volatility.sampleSize = -1;
    }],
  ])("rejects %s", (_label, mutate) => {
    const value = stockSnapshotFixture();
    mutate(value);

    expect(() => decodeStockSnapshotEnvelope(value, { now })).toThrow();
  });

  it("carries the price adjustment basis and gateway receipt times", () => {
    const snapshot = decodeStockSnapshotEnvelope(stockSnapshotFixture(), { now });

    expect(snapshot.priceAdjustment).toBe("forward-adjusted");
    for (const candle of snapshot.candles) {
      expect(candle.priceAdjustment).toBe("forward-adjusted");
      expect(candle.receivedAt).toBeDefined();
      expect(Date.parse(candle.receivedAt!)).toBeGreaterThanOrEqual(
        Date.parse(candle.availableAt),
      );
    }
  });

  it.each([
    ["a receipt time before publication", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.completedCandles[0]!.receivedAt = "2020-01-01T00:00:00.000Z";
    }],
    ["a receipt time after the decision cutoff", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.completedCandles[0]!.receivedAt = "2030-01-01T00:00:00.000Z";
    }],
    ["an undeclared adjustment basis", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.priceAdjustment = "unknown";
    }],
    ["a candle that disagrees with the snapshot basis", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.completedCandles[0]!.priceAdjustment = "unadjusted";
    }],
  ])("rejects %s", (_label, mutate) => {
    const value = stockSnapshotFixture();
    mutate(value);

    expect(() => decodeStockSnapshotEnvelope(value, { now })).toThrow();
  });

  it("names a version mismatch instead of calling an old gateway malformed", () => {
    const value = stockSnapshotFixture();
    value.schemaVersion = "2";
    delete (value.completedCandles[0] as { receivedAt?: string }).receivedAt;

    // An older gateway that predates receivedAt is not sending corrupt data;
    // it is sending an older contract. Calling that "malformed" hides that the
    // fix is to update the gateway.
    expect(() => decodeStockSnapshotEnvelope(value, { now })).toThrow(
      expect.objectContaining({ name: "GatewayContractError" }),
    );
  });

  it("maps an outdated gateway contract to its own error kind", async () => {
    const value = stockSnapshotFixture();
    delete (value.completedCandles[0] as { receivedAt?: string }).receivedAt;
    const fetchImpl = jest
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({}, 404))
      .mockResolvedValueOnce(jsonResponse(value));
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl: fetchImpl as unknown as typeof fetch,
      now: () => now,
    });

    await expect(client.getStockSnapshot("NVDA", "5m", 200)).rejects.toMatchObject({
      kind: "contract",
    });
  });

  it("rejects a snapshot schema version it does not implement", () => {
    const value = stockSnapshotFixture();
    value.schemaVersion = "3";

    expect(() => decodeStockSnapshotEnvelope(value, { now })).toThrow(
      /schemaVersion/i,
    );
  });

  it("accepts an unchecked perfection verdict as null", () => {
    const value = stockSnapshotFixture();
    // The server sends null when the bar 8/9 comparison was not performed;
    // rejecting it here would throw away every in-progress setup.
    value.indicators.magicNine.perfected = null;

    const snapshot = decodeStockSnapshotEnvelope(value, { now });

    expect(snapshot.magicNine.perfected).toBeNull();
  });

  it("keeps every index-aligned TD count instead of only the latest one", () => {
    const snapshot = decodeStockSnapshotEnvelope(stockSnapshotFixture(), { now });

    expect(snapshot.magicNine.series).toEqual([
      { direction: "bullish", count: 1 },
      { direction: "bullish", count: 2 },
    ]);
  });

  it("keeps an older schema-2 snapshot usable when the optional TD series is absent", () => {
    const value = stockSnapshotFixture();
    // `series` was added without a schema-version bump. During a rolling local
    // upgrade an already-running gateway can still return the earlier schema-2
    // shape; rejecting the whole snapshot made every stock detail say 响应异常.
    delete (value.indicators.magicNine as { series?: unknown }).series;

    const snapshot = decodeStockSnapshotEnvelope(value, { now });

    expect(snapshot.magicNine.series).toBeNull();
    expect(snapshot.symbol).toBe("NVDA");
  });

  it.each([
    [[{ direction: "bullish", count: 1 }], "wrong length"],
    [[null, { direction: "sideways", count: 2 }], "unknown direction"],
    [[null, { direction: "bullish", count: 10 }], "count beyond nine"],
  ])("rejects a TD series with %s", (series) => {
    const value = stockSnapshotFixture();
    value.indicators.magicNine.series = series as typeof value.indicators.magicNine.series;

    expect(() => decodeStockSnapshotEnvelope(value, { now })).toThrow(/magic nine series/i);
  });

  it("keeps a completed TD setup visible after counting restarts", () => {
    const value = stockSnapshotFixture();
    value.indicators.magicNine.lastCompleted = {
      direction: "bearish",
      confirmedAtIndex: 0,
      perfected: true,
      barsSince: 1,
    };

    const snapshot = decodeStockSnapshotEnvelope(value, { now });

    expect(snapshot.magicNine.lastCompleted).toEqual({
      direction: "bearish",
      confirmedAtIndex: 0,
      perfected: true,
      barsSince: 1,
    });
    expect(snapshot.magicNine.perfected).toBe(false);
  });

  it.each([
    ["an out-of-range completed index", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.indicators.magicNine.lastCompleted = {
        direction: "bearish",
        confirmedAtIndex: 99,
        perfected: true,
        barsSince: 1,
      };
    }],
    ["a bars-since count that contradicts the index", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.indicators.magicNine.lastCompleted = {
        direction: "bearish",
        confirmedAtIndex: 0,
        perfected: true,
        barsSince: 7,
      };
    }],
    ["a non-boolean perfection verdict", (value: ReturnType<typeof stockSnapshotFixture>) => {
      (value.indicators.magicNine as { perfected: unknown }).perfected = "yes";
    }],
    ["an unknown completed direction", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.indicators.magicNine.lastCompleted = {
        direction: "sideways",
        confirmedAtIndex: 0,
        perfected: true,
        barsSince: 1,
      };
    }],
    ["a superseded method version", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.indicators.magicNine.methodVersion = "sequential-close-4-v1";
    }],
  ])("rejects magic nine with %s", (_label, mutate) => {
    const value = stockSnapshotFixture();
    mutate(value);

    expect(() => decodeStockSnapshotEnvelope(value, { now })).toThrow();
  });

  it("adapts an explicit demo stock into the shared chart shape", () => {
    const chart = toDemoChartSnapshot(stockFixtures["NVDA:short"]!);

    expect(chart).toMatchObject({
      demoData: true,
      source: { source: "fixture", status: "demo" },
      symbol: "NVDA",
      interval: "day",
      forecast: stockFixtures["NVDA:short"]!.forecast,
      candles: stockFixtures["NVDA:short"]!.candles,
      indicators: {
        rsi: { value: stockFixtures["NVDA:short"]!.indicators.rsi.value },
        macd: { line: stockFixtures["NVDA:short"]!.indicators.macd.dif },
      },
    });
    expect(chart.magicNine.series?.filter(Boolean).map((point) => point?.count)).toEqual([
      1,
      2,
      3,
      4,
      5,
      6,
      7,
    ]);
    expect(chart.institutionalHoldings).toHaveLength(1);
  });
});

describe("schema-v3 stock snapshot validation", () => {
  function makeSectionUnavailable(
    payload: ReturnType<typeof stockSnapshotV3Fixture>,
    name: "quote" | "candles" | "technical" | "currentSessionFlow" | "holdings",
    errorCode: string,
  ) {
    Object.assign(payload.sections[name], {
      availabilityStatus: "unavailable",
      qualityStatus: "invalid",
      source: null,
      asOf: null,
      availableAt: null,
      receivedAt: null,
      data: null,
      errorCode,
      reason: "此数据切片不可用",
      warnings: [],
      anomalies: [],
      methodVersion: "unavailable-v1",
    });
  }

  function makeSectionStale(
    payload: ReturnType<typeof stockSnapshotV3Fixture>,
    name: "quote" | "candles" | "currentSessionFlow" | "holdings",
  ) {
    const reason = {
      quote: "实时报价不可用",
      candles: "已完成蜡烛图数据不可用",
      currentSessionFlow: "当前交易时段资金流数据不可用",
      holdings: "机构持仓数据不可用",
    }[name];
    Object.assign(payload.sections[name], {
      availabilityStatus: "stale",
      qualityStatus: "invalid",
      source: null,
      asOf: null,
      availableAt: null,
      receivedAt: null,
      data: null,
      errorCode:
        name === "currentSessionFlow"
          ? "CURRENT_SESSION_FLOW_UNAVAILABLE"
          : "STALE_DATA",
      reason,
      warnings: [],
      anomalies: [],
      methodVersion: "unavailable-v1",
    });
  }

  function makeHoldingsValidated(
    payload: ReturnType<typeof stockSnapshotV3Fixture>,
  ) {
    payload.sections.holdings.qualityStatus = "validated";
    payload.sections.holdings.data[0]!.holdingPercent = 34.5937;
    payload.sections.holdings.warnings = [];
    payload.sections.holdings.anomalies = [];
  }

  function makeEmptyCandlesStructurallyValid(
    payload: ReturnType<typeof stockSnapshotV3Fixture>,
  ) {
    payload.sections.candles.data.candles = [];
    payload.sections.candles.asOf = payload.sections.candles.receivedAt;
    payload.sections.candles.availableAt = payload.sections.candles.receivedAt;
    payload.sections.technical.asOf = payload.sections.candles.receivedAt;
    for (const indicator of [
      payload.sections.technical.data.indicators.ma5,
      payload.sections.technical.data.indicators.rsi,
    ]) {
      indicator.asOf = payload.sections.technical.asOf;
      indicator.series = [];
    }
    payload.sections.technical.data.indicators.macd.asOf =
      payload.sections.technical.asOf;
    payload.sections.technical.data.indicators.macd.series = {
      line: [],
      signal: [],
      histogram: [],
    };
    payload.sections.technical.data.indicators.volatility.asOf =
      payload.sections.technical.asOf;
    payload.sections.technical.data.magicNine.asOf =
      payload.sections.technical.asOf;
    payload.sections.technical.data.magicNine.series = [];
  }

  it("decodes anomalous aggregate holdings without pretending they are unique ownership", () => {
    const snapshot = decodeStockSnapshotV3Envelope(stockSnapshotV3Fixture(), {
      now,
    });

    expect(snapshot).toMatchObject({
      snapshotStatus: "partial",
      compatibility: "v3",
      requestedCount: 200,
      source: { status: "partial" },
    });
    expect(snapshot.institutionalHoldings[0]?.holdingPercent).toBe(345.937);
    expect(snapshot.sections.holdings.qualityStatus).toBe("anomalous");
    expect(snapshot.warnings).toContain(
      "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释",
    );
  });

  it("records a fully validated v3 response as live", () => {
    const payload = stockSnapshotV3Fixture();
    payload.status = "live";
    payload.sections.holdings.qualityStatus = "validated";
    payload.sections.holdings.data[0]!.holdingPercent = 34.5937;
    payload.sections.holdings.warnings = [];
    payload.sections.holdings.anomalies = [];

    const snapshot = decodeStockSnapshotV3Envelope(payload, { now });

    expect(snapshot.snapshotStatus).toBe("live");
    expect(snapshot.source.status).toBe("live");
    expect(snapshot.compatibility).toBe("v3");
  });

  it("keeps a quote-only partial snapshot honest", () => {
    const payload = stockSnapshotV3Fixture();
    makeSectionUnavailable(payload, "candles", "OPEND_OFFLINE");
    makeSectionUnavailable(payload, "technical", "CANDLES_UNAVAILABLE");

    const snapshot = decodeStockSnapshotV3Envelope(payload, { now });

    expect(snapshot.snapshotStatus).toBe("partial");
    expect(snapshot.quote?.price).toBe(142.25);
    expect(snapshot.candles).toEqual([]);
    expect(snapshot.priceAdjustment).toBeNull();
  });

  it("keeps a candles-only partial snapshot honest", () => {
    const payload = stockSnapshotV3Fixture();
    makeSectionUnavailable(payload, "quote", "PROVIDER_ERROR");

    const snapshot = decodeStockSnapshotV3Envelope(payload, { now });

    expect(snapshot.snapshotStatus).toBe("partial");
    expect(snapshot.quote).toBeNull();
    expect(snapshot.candles).toHaveLength(2);
    expect(snapshot.priceAdjustment).toBe("forward-adjusted");
  });

  it("keeps direct current-session flow independent of the requested chart interval", () => {
    const fiveMinute = stockSnapshotV3Fixture();
    const daily = stockSnapshotV3Fixture();
    daily.interval = "day";

    const fiveMinuteSnapshot = decodeStockSnapshotV3Envelope(fiveMinute, { now });
    const dailySnapshot = decodeStockSnapshotV3Envelope(daily, { now });

    expect(dailySnapshot.sections.currentSessionFlow.data).toEqual(
      fiveMinuteSnapshot.sections.currentSessionFlow.data,
    );
    expect(dailySnapshot.participationBars).toEqual(
      fiveMinuteSnapshot.participationBars,
    );
  });

  it("renders the served order-size flow buckets as live participation bars instead of a false unavailability", () => {
    const payload = stockSnapshotV3Fixture();

    const snapshot = decodeStockSnapshotV3Envelope(payload, { now });

    // A live/validated currentSessionFlow section must never fall back to the
    // placeholder reason the server itself never asserted.
    expect(
      snapshot.participationBars.some(
        (bar) => bar.missingReason === "CURRENT_SESSION_FLOW_NOT_CANDLE_ALIGNED",
      ),
    ).toBe(false);
    expect(snapshot.participationBars).toEqual([
      {
        closedAt: "2026-07-25T15:50:00.000Z",
        asOf: "2026-07-25T15:50:00.000Z",
        availableAt: "2026-07-25T15:50:01.000Z",
        mainShare: 0.72,
        retailShare: 0.28,
        mainActivity: 1800,
        retailActivity: 700,
        netFlow: 2500,
        coverage: 1,
        source: "moomoo",
        methodVersion: "order-size-activity-share-v1",
        qualityStatus: "live",
        missingReason: null,
      },
      {
        closedAt: "2026-07-25T15:55:00.000Z",
        asOf: "2026-07-25T15:55:00.000Z",
        availableAt: "2026-07-25T15:55:01.000Z",
        mainShare: 2100 / 3200,
        retailShare: 1100 / 3200,
        mainActivity: 2100,
        retailActivity: 1100,
        netFlow: 3200,
        coverage: 1,
        source: "moomoo",
        methodVersion: "order-size-activity-share-v1",
        qualityStatus: "live",
        missingReason: null,
      },
    ]);
  });

  it("reports a zero-activity flow sample as unavailable rather than a fabricated split", () => {
    const payload = stockSnapshotV3Fixture();
    for (const row of payload.sections.currentSessionFlow.data) {
      row.extraLargeOrderNetFlow = 0;
      row.largeOrderNetFlow = 0;
      row.mediumOrderNetFlow = 0;
      row.smallOrderNetFlow = 0;
      row.totalNetFlow = 0;
      row.largeOrderProxyNetFlow = 0;
    }

    const snapshot = decodeStockSnapshotV3Envelope(payload, { now });

    expect(
      snapshot.participationBars.every(
        (bar) =>
          bar.qualityStatus === "unavailable" &&
          bar.mainShare === null &&
          bar.netFlow === null &&
          bar.missingReason === "zero activity denominator",
      ),
    ).toBe(true);
  });

  it.each(["unavailable", "stale"] as const)(
    "shows the server's own reason when currentSessionFlow is genuinely %s, never the candle-alignment placeholder",
    (kind) => {
      const payload = stockSnapshotV3Fixture();
      if (kind === "unavailable") {
        makeSectionUnavailable(payload, "currentSessionFlow", "CURRENT_SESSION_FLOW_PROVIDER_ERROR");
      } else {
        makeSectionStale(payload, "currentSessionFlow");
      }

      const snapshot = decodeStockSnapshotV3Envelope(payload, { now });

      expect(snapshot.candles).toHaveLength(2);
      expect(snapshot.participationBars).toHaveLength(2);
      expect(
        snapshot.participationBars.every((bar) => bar.qualityStatus === "unavailable"),
      ).toBe(true);
      const expectedReason = payload.sections.currentSessionFlow.reason;
      expect(expectedReason).toEqual(expect.any(String));
      expect(
        snapshot.participationBars.every(
          (bar) => bar.missingReason === expectedReason,
        ),
      ).toBe(true);
      expect(
        snapshot.participationBars.some(
          (bar) => bar.missingReason === "CURRENT_SESSION_FLOW_NOT_CANDLE_ALIGNED",
        ),
      ).toBe(false);
    },
  );

  it.each([
    ["institutional identity", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      (payload.sections.currentSessionFlow.data[0] as { institutionalIdentity: boolean }).institutionalIdentity = true;
    }],
    ["a future timestamp", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.currentSessionFlow.data[0]!.timestamp = "2026-07-25T16:00:00.000Z";
    }],
    ["out-of-order timestamps", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.currentSessionFlow.data[1]!.timestamp = "2026-07-25T15:45:00.000Z";
    }],
    ["the wrong method version", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.currentSessionFlow.methodVersion = "candle-aligned-flow-v1";
    }],
    ["a non-finite amount", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.currentSessionFlow.data[0]!.totalNetFlow = Number.NaN;
    }],
  ])("rejects direct current-session flow carrying %s", (_label, mutate) => {
    const payload = stockSnapshotV3Fixture();
    mutate(payload);

    expect(() => decodeStockSnapshotV3Envelope(payload, { now })).toThrow();
  });

  it("keeps usable price when one optional requested section is unavailable", () => {
    const payload = stockSnapshotV3Fixture();
    makeSectionUnavailable(payload, "holdings", "MALFORMED_PROVIDER_DATA");

    const snapshot = decodeStockSnapshotV3Envelope(payload, { now });

    expect(snapshot.quote?.price).toBe(142.25);
    expect(snapshot.candles).toHaveLength(2);
    expect(snapshot.institutionalHoldings).toEqual([]);
    expect(snapshot.sections.holdings.errorCode).toBe("MALFORMED_PROVIDER_DATA");
  });

  it.each(["currentSessionFlow", "holdings"] as const)(
    "keeps usable price when the optional %s section has a producer stale envelope",
    (name) => {
      const payload = stockSnapshotV3Fixture();
      makeSectionStale(payload, name);

      const snapshot = decodeStockSnapshotV3Envelope(payload, { now });

      expect(snapshot.snapshotStatus).toBe("partial");
      expect(snapshot.quote?.price).toBe(142.25);
      expect(snapshot.candles).toHaveLength(2);
      expect(snapshot.sections[name]).toMatchObject({
        availabilityStatus: "stale",
        qualityStatus: "invalid",
        data: null,
      });
    },
  );

  it.each([
    ["a negative aggregate", -1],
    ["a non-finite aggregate", Number.POSITIVE_INFINITY],
  ])("rejects holdings with %s", (_label, holdingPercent) => {
    const payload = stockSnapshotV3Fixture();
    payload.sections.holdings.data[0]!.holdingPercent = holdingPercent;

    expect(() => decodeStockSnapshotV3Envelope(payload, { now })).toThrow();
  });

  it("uses original provider row indexes for aggregate holdings anomalies", () => {
    const payload = stockSnapshotV3Fixture();
    payload.sections.holdings.anomalies = [
      {
        rowIndex: 0,
        code: "MISSING_REQUIRED_FIELD",
        reason: "机构持仓记录缺少必填字段",
      },
      {
        rowIndex: 1,
        code: "AGGREGATE_PERCENT_ABOVE_100",
        reason: aggregateHoldingsReason,
      },
    ];

    const snapshot = decodeStockSnapshotV3Envelope(payload, { now });

    expect(snapshot.institutionalHoldings).toHaveLength(1);
    expect(snapshot.institutionalHoldings[0]?.holdingPercent).toBe(345.937);
  });

  it.each([
    ["wrong code", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.holdings.anomalies[0]!.code = "INVALID_NUMERIC_VALUE";
    }],
    ["missing code", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      delete (payload.sections.holdings.anomalies[0] as { code?: string }).code;
    }],
    ["wrong reason", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.holdings.anomalies[0]!.reason = "聚合比例说明不匹配";
    }],
    ["missing reason", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      delete (payload.sections.holdings.anomalies[0] as { reason?: string }).reason;
    }],
  ])("rejects aggregate holdings with a %s", (_label, mutate) => {
    const payload = stockSnapshotV3Fixture();
    mutate(payload);

    expect(() => decodeStockSnapshotV3Envelope(payload, { now })).toThrow();
  });

  it("keeps v2 and v3 decoders version-specific", () => {
    expect(() =>
      decodeStockSnapshotV3Envelope(stockSnapshotFixture(), { now }),
    ).toThrow(/schemaVersion/i);
    expect(() =>
      decodeStockSnapshotEnvelope(stockSnapshotV3Fixture(), { now }),
    ).toThrow(/schemaVersion/i);
  });

  it("distinguishes an unknown major from malformed provider data", () => {
    const payload = stockSnapshotV3Fixture();
    payload.schemaVersion = "4";

    expect(() => decodeStockSnapshotV3Envelope(payload, { now })).toThrow(
      GatewayClientUpdateRequiredError,
    );
  });

  it("throws a typed unavailable error after validating all section envelopes", () => {
    const payload = stockSnapshotV3Fixture();
    payload.status = "unavailable";
    makeSectionUnavailable(payload, "quote", "LOGIN_REQUIRED");
    makeSectionUnavailable(payload, "candles", "LOGIN_REQUIRED");
    makeSectionUnavailable(payload, "technical", "CANDLES_UNAVAILABLE");

    expect(() => decodeStockSnapshotV3Envelope(payload, { now })).toThrow(
      GatewaySnapshotUnavailableError,
    );
    try {
      decodeStockSnapshotV3Envelope(payload, { now });
    } catch (error) {
      expect(error).toMatchObject({
        name: "GatewaySnapshotUnavailableError",
        kind: "login-required",
      });
    }
  });

  it("classifies producer stale quote and candles envelopes as unavailable stale data", () => {
    const payload = stockSnapshotV3Fixture();
    payload.status = "unavailable";
    makeSectionStale(payload, "quote");
    makeSectionStale(payload, "candles");
    makeSectionUnavailable(payload, "technical", "CANDLES_UNAVAILABLE");

    expect(() => decodeStockSnapshotV3Envelope(payload, { now })).toThrow(
      expect.objectContaining({
        name: "GatewaySnapshotUnavailableError",
        kind: "stale",
      }),
    );
  });

  it("rejects a validated empty candle section as an unusable price source", () => {
    const payload = stockSnapshotV3Fixture();
    payload.status = "unavailable";
    makeSectionUnavailable(payload, "quote", "PROVIDER_ERROR");
    makeSectionUnavailable(payload, "technical", "CANDLES_UNAVAILABLE");
    payload.sections.candles.data.candles = [];

    expect(() => decodeStockSnapshotV3Envelope(payload, { now })).toThrow(
      GatewaySnapshotUnavailableError,
    );
  });

  it("rejects live status when validated candles are structurally valid but empty", () => {
    const payload = stockSnapshotV3Fixture();
    payload.status = "live";
    makeHoldingsValidated(payload);
    makeEmptyCandlesStructurallyValid(payload);

    expect(() => decodeStockSnapshotV3Envelope(payload, { now })).toThrow(
      /status/i,
    );
  });

  it("accepts partial status when validated candles are structurally valid but empty", () => {
    const payload = stockSnapshotV3Fixture();
    payload.status = "partial";
    makeHoldingsValidated(payload);
    makeEmptyCandlesStructurallyValid(payload);

    const snapshot = decodeStockSnapshotV3Envelope(payload, { now });

    expect(snapshot.snapshotStatus).toBe("partial");
    expect(snapshot.quote?.price).toBe(142.25);
    expect(snapshot.candles).toEqual([]);
  });

  it.each([
    ["a flow row timestamp later than section asOf", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.currentSessionFlow.data[1]!.timestamp =
        "2026-07-25T15:55:00.500Z";
    }],
    ["a flow row availability later than section availableAt", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.currentSessionFlow.data[1]!.availableAt =
        "2026-07-25T15:55:01.500Z";
    }],
    ["a candle receipt later than section receivedAt", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.candles.data.candles[1]!.receivedAt =
        "2026-07-25T15:55:03.000Z";
    }],
    ["a candle asOf that differs from its timestamp", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.candles.data.candles[0]!.asOf =
        "2026-07-25T15:49:59.000Z";
    }],
    ["a candle section asOf that differs from its latest row", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.candles.asOf = "2026-07-25T15:54:59.000Z";
    }],
    ["a candle section availableAt that differs from its latest row availability", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.candles.availableAt = "2026-07-25T15:55:01.500Z";
    }],
    ["holdings section asOf that differs from the first report", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.holdings.asOf = "2026-03-30T00:00:00.000Z";
    }],
    ["holdings section availableAt that differs from the first row", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.holdings.availableAt = "2026-05-16T00:00:00.000Z";
    }],
    ["technical indicator provenance that differs from its section", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.technical.data.indicators.ma5.asOf =
        "2026-07-25T15:54:59.000Z";
    }],
    ["technical pattern provenance that differs from its section", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.technical.data.magicNine.availableAt =
        "2026-07-25T15:59:49.000Z";
    }],
  ])("rejects %s", (_label, mutate) => {
    const payload = stockSnapshotV3Fixture();
    mutate(payload);

    expect(() => decodeStockSnapshotV3Envelope(payload, { now })).toThrow();
  });

  it.each([
    ["a missing envelope field", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      delete (payload.sections.news as { warnings?: string[] }).warnings;
    }],
    ["a future envelope timestamp", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.holdings.receivedAt = "2026-07-25T16:00:00.000Z";
    }],
    ["quality that contradicts unavailable data", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.sections.news.qualityStatus = "validated";
    }],
    ["duplicate requested sections", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.requestedSections[4] = "quote";
    }],
  ])("rejects %s", (_label, mutate) => {
    const payload = stockSnapshotV3Fixture();
    mutate(payload);

    expect(() => decodeStockSnapshotV3Envelope(payload, { now })).toThrow();
  });
});

describe("market gateway fallback", () => {
  it.each([
    [
      // A bare 401 is the gateway refusing this device's token, which is a
      // pairing problem. The brokerage login it used to be reported as arrives
      // as LOGIN_REQUIRED with a 503 instead.
      "an unusable device token",
      async () => jsonResponse({}, 401),
      { name: "GatewayRequestError", kind: "auth-required" },
    ],
    [
      "permission denied",
      async () => jsonResponse({}, 403),
      { name: "GatewayRequestError", kind: "permission" },
    ],
    [
      "offline",
      async () => {
        throw new Error("offline");
      },
      { name: "GatewayRequestError", kind: "offline" },
    ],
    [
      "stale",
      async () =>
        jsonResponse(
          {
            schemaVersion: "1",
            source: "moomoo",
            sourceStatus: "stale",
            error: { code: "STALE_DATA" },
          },
          503,
        ),
      { name: "GatewayRequestError", kind: "stale" },
    ],
    [
      "invalid schema",
      async () => jsonResponse({ schemaVersion: "wrong" }),
      { name: "GatewayValidationError" },
    ],
  ])(
    "strict watchlist rejects %s without a fixture fallback",
    async (_label, reply, expected) => {
      const client = createMarketGatewayClient({
        baseUrl: "http://127.0.0.1:8765",
        fetchImpl: jest.fn(reply) as unknown as typeof fetch,
        now: () => now,
      });

      await expect(client.getWatchlist()).rejects.toMatchObject(expected);
    },
  );

  it("fails closed to one explicit fixture snapshot when the gateway is unavailable", async () => {
    const fetchImpl = jest.fn(async () => {
      throw new Error("offline");
    }) as unknown as typeof fetch;
    const client = createMarketGatewayClient({
      baseUrl: "http://192.168.1.10:8765",
      authorizationToken: "0123456789abcdef0123456789abcdef",
      fetchImpl,
      now: () => now,
    });

    const result = await client.getWatchlistOrFallback(fallback);

    expect(result.source).toBe("fixture");
    expect(result.quotes).toEqual(fallback);
    expect(result.fallbackReason).toBe("gateway-unavailable");
  });

  it("falls back on stale, malformed, permission, or non-moomoo responses", async () => {
    const fetchImpl = jest.fn(async () =>
      jsonResponse({
        schemaVersion: "1",
        source: "moomoo",
        session: "permission-denied",
        asOf: "2026-07-25T15:59:50.000Z",
        availableAt: "2026-07-25T15:59:51.000Z",
        items: [],
      }),
    ) as unknown as typeof fetch;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    await expect(client.getWatchlistOrFallback(fallback)).resolves.toMatchObject({
      source: "fixture",
      fallbackReason: "gateway-invalid",
      quotes: fallback,
    });
  });

  it("returns live rows only after successful schema, source, health, and freshness checks", async () => {
    const fetchImpl = jest.fn(async () =>
      jsonResponse({
        schemaVersion: "1",
        source: "moomoo",
        session: "healthy",
        asOf: "2026-07-25T15:59:50.000Z",
        availableAt: "2026-07-25T15:59:51.000Z",
        items: [
          {
            code: "US.TSLA",
            price: 320,
            changePercent: -1.5,
            availableAt: "2026-07-25T15:59:49.000Z",
          },
        ],
      }),
    ) as unknown as typeof fetch;
    const client = createMarketGatewayClient({
      baseUrl: "http://192.168.1.10:8765/",
      authorizationToken: "0123456789abcdef0123456789abcdef",
      fetchImpl,
      now: () => now,
    });

    const result = await client.getWatchlistOrFallback(fallback);

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://192.168.1.10:8765/watchlist",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer 0123456789abcdef0123456789abcdef",
        }),
      }),
    );
    expect(result).toMatchObject({
      source: "moomoo",
      quotes: [{ symbol: "TSLA", direction: "bearish" }],
    });
    expect(result.quotes).not.toContainEqual(fallback[0]);
  });

  it("requires an ephemeral token before connecting to a LAN gateway", () => {
    expect(() =>
      createMarketGatewayClient({
        baseUrl: "http://192.168.1.10:8765",
        fetchImpl: jest.fn() as unknown as typeof fetch,
      }),
    ).toThrow(/token/i);
  });

  it("rejects a LAN token shorter than the 32-character runtime policy", () => {
    expect(() =>
      createMarketGatewayClient({
        baseUrl: "http://192.168.1.10:8765",
        authorizationToken: "x".repeat(31),
        fetchImpl: jest.fn() as unknown as typeof fetch,
      }),
    ).toThrow(/32/);
  });

  it.each([
    "ftp://127.0.0.1:8765",
    "http://user:secret@127.0.0.1:8765",
    "http://127.0.0.1:8765/api?token=secret",
  ])("rejects an unsafe gateway base URL: %s", (baseUrl) => {
    expect(() =>
      createMarketGatewayClient({
        baseUrl,
        fetchImpl: jest.fn() as unknown as typeof fetch,
      }),
    ).toThrow(/baseUrl/i);
  });

  it("fetches and validates completed candles without fixture mixing", async () => {
    const fetchImpl = jest.fn(async () =>
      jsonResponse({
        schemaVersion: "1",
        source: "moomoo",
        session: "healthy",
        asOf: "2026-07-25T15:59:50.000Z",
        availableAt: "2026-07-25T15:59:51.000Z",
        symbol: "NVDA",
        interval: "5m",
        items: [
          {
            timestamp: "2026-07-25T15:55:00.000Z",
            availableAt: "2026-07-25T15:55:01.000Z",
            complete: true,
            open: 140,
            high: 142,
            low: 139.5,
            close: 141.5,
            volume: 1200,
          },
        ],
      }),
    ) as unknown as typeof fetch;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    const result = await client.getCandles("nvda", "5m", 200);

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/candles?symbol=NVDA&interval=5m&count=200",
      expect.objectContaining({ method: "GET" }),
    );
    expect(result).toMatchObject({
      source: "moomoo",
      symbol: "NVDA",
      interval: "5m",
      candles: [{ complete: true, close: 141.5 }],
    });
  });

  it("requests schema v3 first and never substitutes a fixture", async () => {
    const payload = stockSnapshotV3Fixture();
    payload.interval = "day";
    const fetchImpl = jest.fn(async () =>
      jsonResponse(payload),
    ) as unknown as typeof fetch;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    const result = await client.getStockSnapshot(" us.nvda ", "day", 200);
    const requestedPaths = (fetchImpl as unknown as jest.MockedFunction<typeof fetch>)
      .mock.calls.map(([request]) => {
        const url = new URL(String(request));
        return `${url.pathname}${url.search}`;
      });

    expect(requestedPaths).toEqual([
      "/v3/stock-snapshot?symbol=NVDA&interval=day&count=200",
    ]);
    expect(result).toMatchObject({
      demoData: false,
      compatibility: "v3",
      requestedCount: 200,
      source: { source: "moomoo" },
    });
  });

  it.each([" US.nvda ", "US.NVDA", "nvda", "NvDa"])(
    "rejects non-canonical v3 response symbol %p without fallback",
    async (responseSymbol) => {
      const payload = stockSnapshotV3Fixture();
      payload.symbol = responseSymbol;
      const fetchImpl = jest.fn(async () =>
        jsonResponse(payload),
      ) as unknown as jest.MockedFunction<typeof fetch>;
      const client = createMarketGatewayClient({
        baseUrl: "http://127.0.0.1:8765",
        fetchImpl,
        now: () => now,
      });

      await expect(
        client.getStockSnapshot("nvda", "5m", 200),
      ).rejects.toMatchObject({ kind: "validation" });
      expect(fetchImpl).toHaveBeenCalledTimes(1);
    },
  );

  it.each([404, 426])(
    "falls back to schema v2 only when the v3 route returns HTTP %s",
    async (status) => {
      const legacyPayload = stockSnapshotFixture();
      legacyPayload.interval = "day";
      const fetchImpl = jest
        .fn<typeof fetch>()
        .mockResolvedValueOnce(jsonResponse({}, status))
        .mockResolvedValueOnce(jsonResponse(legacyPayload));
      const client = createMarketGatewayClient({
        baseUrl: "http://127.0.0.1:8765",
        fetchImpl: fetchImpl as unknown as typeof fetch,
        now: () => now,
      });

      const snapshot = await client.getStockSnapshot("NVDA", "day", 200);
      const requestedPaths = fetchImpl.mock.calls.map(([request]) => {
        const url = new URL(String(request));
        return `${url.pathname}${url.search}`;
      });

      expect(requestedPaths).toEqual([
        "/v3/stock-snapshot?symbol=NVDA&interval=day&count=200",
        "/stock-snapshot?symbol=NVDA&interval=day&count=200",
      ]);
      expect(snapshot).toMatchObject({
        snapshotStatus: "live",
        compatibility: "v2-fallback",
        requestedCount: 200,
        source: { status: "live" },
        sections: {
          currentSessionFlow: {
            availabilityStatus: "unavailable",
            qualityStatus: "invalid",
            data: null,
            errorCode: "LEGACY_V2_CANDLE_ALIGNED_ONLY",
          },
        },
      });
      expect(snapshot.participationBars[0]?.mainShare).toBe(0.6);
    },
  );

  it.each([
    ["HTTP 401", () => jsonResponse({}, 401), "auth-required"],
    ["HTTP 403", () => jsonResponse({}, 403), "permission"],
    [
      "HTTP 500 provider error",
      () => jsonResponse({ error: { code: "PROVIDER_ERROR" } }, 500),
      "provider-error",
    ],
  ])("does not fall back after %s", async (_label, reply, kind) => {
    const fetchImpl = jest.fn(async () => reply()) as unknown as jest.MockedFunction<
      typeof fetch
    >;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    await expect(
      client.getStockSnapshot("NVDA", "5m", 200),
    ).rejects.toMatchObject({ kind });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("does not fall back after malformed schema-v3 data", async () => {
    const payload = stockSnapshotV3Fixture();
    (payload.sections.quote.warnings as unknown[]) = [42];
    const fetchImpl = jest.fn(async () => jsonResponse(payload)) as unknown as jest.MockedFunction<
      typeof fetch
    >;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    await expect(
      client.getStockSnapshot("NVDA", "5m", 200),
    ).rejects.toMatchObject({ kind: "validation" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("maps stale quote and candles sections to stale without v2 fallback", async () => {
    const payload = stockSnapshotV3Fixture();
    payload.status = "unavailable";
    Object.assign(payload.sections.quote, {
      availabilityStatus: "stale",
      qualityStatus: "invalid",
      source: null,
      asOf: null,
      availableAt: null,
      receivedAt: null,
      data: null,
      errorCode: "STALE_DATA",
      reason: "实时报价不可用",
      warnings: [],
      anomalies: [],
      methodVersion: "unavailable-v1",
    });
    Object.assign(payload.sections.candles, {
      availabilityStatus: "stale",
      qualityStatus: "invalid",
      source: null,
      asOf: null,
      availableAt: null,
      receivedAt: null,
      data: null,
      errorCode: "STALE_DATA",
      reason: "已完成蜡烛图数据不可用",
      warnings: [],
      anomalies: [],
      methodVersion: "unavailable-v1",
    });
    Object.assign(payload.sections.technical, {
      availabilityStatus: "unavailable",
      qualityStatus: "invalid",
      source: null,
      asOf: null,
      availableAt: null,
      receivedAt: null,
      data: null,
      errorCode: "CANDLES_UNAVAILABLE",
      reason: "技术指标需要已验证的蜡烛图数据",
      warnings: [],
      anomalies: [],
      methodVersion: "unavailable-v1",
    });
    const fetchImpl = jest.fn(async () =>
      jsonResponse(payload),
    ) as unknown as jest.MockedFunction<typeof fetch>;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    await expect(
      client.getStockSnapshot("NVDA", "5m", 200),
    ).rejects.toMatchObject({
      name: "GatewayRequestError",
      kind: "stale",
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("maps an unknown major to client-update-required without fallback", async () => {
    const payload = stockSnapshotV3Fixture();
    payload.schemaVersion = "4";
    const fetchImpl = jest.fn(async () => jsonResponse(payload)) as unknown as jest.MockedFunction<
      typeof fetch
    >;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    await expect(
      client.getStockSnapshot("NVDA", "5m", 200),
    ).rejects.toMatchObject({
      name: "GatewayRequestError",
      kind: "client-update-required",
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["symbol", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.symbol = "TSLA";
    }],
    ["interval", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.interval = "day";
    }],
    ["count", (payload: ReturnType<typeof stockSnapshotV3Fixture>) => {
      payload.count = 199;
    }],
  ])("rejects a %s echo mismatch without fallback", async (_label, mutate) => {
    const payload = stockSnapshotV3Fixture();
    mutate(payload);
    const fetchImpl = jest.fn(async () => jsonResponse(payload)) as unknown as jest.MockedFunction<
      typeof fetch
    >;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    await expect(
      client.getStockSnapshot("NVDA", "5m", 200),
    ).rejects.toMatchObject({ kind: "validation" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("maps a mid-operation OPEND_OFFLINE snapshot response to retryable offline", async () => {
    const fetchImpl = jest.fn(async () =>
      jsonResponse(
        {
          schemaVersion: "2",
          source: "moomoo",
          sourceStatus: "unavailable",
          symbol: "NVDA",
          interval: "5m",
          decisionCutoff: "2026-07-25T15:59:50.000Z",
          error: {
            code: "OPEND_OFFLINE",
            message: "moomoo OpenD is offline",
            retriable: true,
          },
        },
        503,
      ),
    ) as unknown as typeof fetch;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    await expect(
      client.getStockSnapshot("NVDA", "5m", 200),
    ).rejects.toMatchObject({
      name: "GatewayRequestError",
      kind: "offline",
    });
  });

  it("aborts the fetch and returns AbortError when the caller cancels first", async () => {
    const caller = new AbortController();
    let fetchSignal: AbortSignal | undefined;
    const fetchImpl = jest.fn(
      async (_url: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          fetchSignal = init?.signal as AbortSignal;
          fetchSignal.addEventListener(
            "abort",
            () =>
              reject(
                Object.assign(new Error("request aborted"), {
                  name: "AbortError",
                }),
              ),
            { once: true },
          );
        }),
    ) as unknown as typeof fetch;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    const request = client.getStockSnapshot("NVDA", "5m", 200, caller.signal);
    await Promise.resolve();
    caller.abort();

    expect(fetchSignal?.aborted).toBe(true);
    await expect(request).rejects.toMatchObject({ name: "AbortError" });
  });

  it("keeps caller-first cancellation distinct after the timeout deadline", async () => {
    jest.useFakeTimers();
    try {
      const caller = new AbortController();
      let fetchSignal: AbortSignal | undefined;
      const fetchImpl = jest.fn(
        async (_url: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            fetchSignal = init?.signal as AbortSignal;
            fetchSignal.addEventListener(
              "abort",
              () =>
                reject(
                  Object.assign(new Error("request aborted"), {
                    name: "AbortError",
                  }),
                ),
              { once: true },
            );
          }),
      ) as unknown as typeof fetch;
      const client = createMarketGatewayClient({
        baseUrl: "http://127.0.0.1:8765",
        fetchImpl,
        now: () => now,
        timeoutMs: 25,
      });

      const request = client.getStockSnapshot(
        "NVDA",
        "5m",
        200,
        caller.signal,
      );
      await Promise.resolve();
      caller.abort();
      jest.advanceTimersByTime(25);

      expect(fetchSignal?.aborted).toBe(true);
      await expect(request).rejects.toMatchObject({ name: "AbortError" });
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      jest.useRealTimers();
    }
  });

  it("still aborts and classifies a strict snapshot timeout", async () => {
    jest.useFakeTimers();
    try {
      let fetchSignal: AbortSignal | undefined;
      const fetchImpl = jest.fn(
        async (_url: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            fetchSignal = init?.signal as AbortSignal;
            fetchSignal.addEventListener(
              "abort",
              () =>
                reject(
                  Object.assign(new Error("timed out"), {
                    name: "AbortError",
                  }),
                ),
              { once: true },
            );
          }),
      ) as unknown as typeof fetch;
      const client = createMarketGatewayClient({
        baseUrl: "http://127.0.0.1:8765",
        fetchImpl,
        now: () => now,
        timeoutMs: 25,
      });

      const request = client.getStockSnapshot("NVDA", "5m", 200);
      await Promise.resolve();
      jest.advanceTimersByTime(25);

      expect(fetchSignal?.aborted).toBe(true);
      await expect(request).rejects.toMatchObject({
        name: "GatewayRequestError",
        kind: "timeout",
      });
      expect(fetchImpl).toHaveBeenCalledTimes(1);
    } finally {
      jest.useRealTimers();
    }
  });

  it("keeps timeout-first classification when the caller aborts later", async () => {
    jest.useFakeTimers();
    try {
      const caller = new AbortController();
      const fetchImpl = jest.fn(
        async (_url: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            const fetchSignal = init?.signal as AbortSignal;
            fetchSignal.addEventListener(
              "abort",
              () =>
                reject(
                  Object.assign(new Error("request aborted"), {
                    name: "AbortError",
                  }),
                ),
              { once: true },
            );
          }),
      ) as unknown as typeof fetch;
      const client = createMarketGatewayClient({
        baseUrl: "http://127.0.0.1:8765",
        fetchImpl,
        now: () => now,
        timeoutMs: 25,
      });

      const request = client.getStockSnapshot(
        "NVDA",
        "5m",
        200,
        caller.signal,
      );
      await Promise.resolve();
      jest.advanceTimersByTime(25);
      caller.abort();

      await expect(request).rejects.toMatchObject({
        name: "GatewayRequestError",
        kind: "timeout",
      });
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      jest.useRealTimers();
    }
  });

  it("classifies a fetch AbortError without a known abort cause as offline", async () => {
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl: jest.fn(async () => {
        throw Object.assign(new Error("fetch aborted internally"), {
          name: "AbortError",
        });
      }) as unknown as typeof fetch,
      now: () => now,
    });

    await expect(
      client.getStockSnapshot("NVDA", "5m"),
    ).rejects.toMatchObject({
      name: "GatewayRequestError",
      kind: "offline",
    });
  });

  it("surfaces an unavailable snapshot as a typed error instead of falling back", async () => {
    const fetchImpl = jest.fn(async () =>
      jsonResponse(
        {
          schemaVersion: "2",
          source: "moomoo",
          sourceStatus: "unavailable",
          error: { code: "LOGIN_REQUIRED" },
        },
        503,
      ),
    ) as unknown as typeof fetch;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    await expect(client.getStockSnapshot("NVDA", "5m")).rejects.toMatchObject({
      name: "GatewayRequestError",
      kind: "login-required",
    } satisfies Partial<GatewayRequestError>);
  });

  it.each([
    ["offline", async () => { throw new Error("offline"); }, "offline"],
    [
      "permission denied",
      async () => jsonResponse({ error: { code: "PERMISSION_DENIED" } }, 403),
      "permission",
    ],
    [
      "stale",
      async () => jsonResponse({ sourceStatus: "stale", error: { code: "STALE_DATA" } }, 503),
      "stale",
    ],
    // A schema this app cannot read is this app's problem, not a verdict on
    // the provider's data; `malformed` is reserved for the gateway's own.
    ["an unreadable schema", async () => jsonResponse({ schemaVersion: "wrong" }), "validation"],
  ])("classifies %s snapshot failures without a fixture fallback", async (_label, reply, kind) => {
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl: jest.fn(reply) as unknown as typeof fetch,
      now: () => now,
    });

    await expect(client.getStockSnapshot("NVDA", "5m")).rejects.toMatchObject({
      name: "GatewayRequestError",
      kind,
    });
  });
});

/**
 * The gateway names fifteen distinct failures. The app used to collapse most of
 * them into "malformed", which is the one word that cannot be acted on: it
 * describes a broken payload, and almost none of these are that.
 */
describe("market gateway failure classification", () => {
  function clientReplying(reply: () => Promise<Response>) {
    return createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl: jest.fn(reply) as unknown as typeof fetch,
      now: () => now,
    });
  }

  it.each([
    ["INVALID_ARGUMENT", 400, "invalid-request"],
    ["AUTH_REQUIRED", 401, "auth-required"],
    ["CLIENT_NOT_ALLOWED", 403, "client-not-allowed"],
    ["ORIGIN_NOT_ALLOWED", 403, "client-not-allowed"],
    ["PERMISSION_DENIED", 403, "permission"],
    ["PATH_NOT_ALLOWED", 404, "route-unsupported"],
    ["METHOD_NOT_ALLOWED", 405, "route-unsupported"],
    ["QUOTA_EXCEEDED", 429, "rate-limited"],
    ["UNSUPPORTED_CAPABILITY", 501, "unsupported"],
    ["MALFORMED_PROVIDER_DATA", 502, "malformed"],
    ["PROVIDER_ERROR", 502, "provider-error"],
    ["SDK_UNAVAILABLE", 503, "sdk-unavailable"],
    ["OPEND_OFFLINE", 503, "offline"],
    ["LOGIN_REQUIRED", 503, "login-required"],
    ["STALE_DATA", 503, "stale"],
  ])("gives %s its own kind", async (code, status, kind) => {
    const client = clientReplying(async () =>
      jsonResponse({ error: { code, message: "upstream said so" } }, status),
    );

    await expect(client.getStockSnapshot("NVDA", "5m")).rejects.toMatchObject({
      name: "GatewayRequestError",
      kind,
    });
  });

  it("keeps every gateway code mapped to a kind of its own", async () => {
    const codes = [
      "INVALID_ARGUMENT",
      "AUTH_REQUIRED",
      "CLIENT_NOT_ALLOWED",
      "PERMISSION_DENIED",
      "PATH_NOT_ALLOWED",
      "QUOTA_EXCEEDED",
      "UNSUPPORTED_CAPABILITY",
      "MALFORMED_PROVIDER_DATA",
      "PROVIDER_ERROR",
      "SDK_UNAVAILABLE",
      "OPEND_OFFLINE",
      "LOGIN_REQUIRED",
      "STALE_DATA",
    ];
    const kinds = await Promise.all(
      codes.map(async (code) => {
        const client = clientReplying(async () =>
          jsonResponse({ error: { code } }, 500),
        );
        const error = (await client
          .getStockSnapshot("NVDA", "5m")
          .catch((caught: unknown) => caught)) as GatewayRequestError;
        return error.kind;
      }),
    );

    expect(new Set(kinds).size).toBe(codes.length);
  });

  it("separates a payload this app cannot decode from one the gateway rejected", async () => {
    // The gateway saying "the provider's data failed point-in-time validation"
    // and this app failing to read the gateway's own answer are different
    // facts with different fixes, and the screen explains them differently.
    const undecodable = clientReplying(async () =>
      jsonResponse({ schemaVersion: "wrong" }),
    );

    await expect(
      undecodable.getStockSnapshot("NVDA", "5m"),
    ).rejects.toMatchObject({ name: "GatewayRequestError", kind: "validation" });
  });

  it("says a refusal carried no reason rather than inventing one", async () => {
    // An unavailable snapshot with no error object used to be reported as
    // malformed provider data, which would now put a point-in-time explanation
    // on screen that the gateway never claimed.
    const silent = clientReplying(async () =>
      jsonResponse({ schemaVersion: "2", source: "moomoo", sourceStatus: "unavailable" }, 503),
    );

    await expect(silent.getStockSnapshot("NVDA", "5m")).rejects.toMatchObject({
      name: "GatewayRequestError",
      kind: "unspecified",
    });
  });
});

describe("indicator series", () => {
  it("reads the drawable series the gateway published for every indicator", () => {
    const snapshot = decodeStockSnapshotEnvelope(
      stockSnapshotWithSeriesFixture(),
      { now },
    );

    expect(snapshot.indicators.ma5.series).toMatchObject({
      values: [null, 140.8],
      source: "analysis-core",
      methodVersion: "sma-5-v1",
      qualityStatus: "live",
    });
    expect(snapshot.indicators.rsi.series?.values).toEqual([48.5, 56.2]);
    expect(snapshot.indicators.macd.series).toMatchObject({
      line: [0.3, 0.45],
      signal: [0.25, 0.3],
      histogram: [0.05, 0.15],
      methodVersion: "macd-12-26-9-v1",
    });
  });

  it("reports a series the gateway did not publish as missing", () => {
    const snapshot = decodeStockSnapshotEnvelope(stockSnapshotFixture(), { now });

    expect(snapshot.indicators.ma5.series).toBeNull();
    expect(snapshot.indicators.rsi.series).toBeNull();
    expect(snapshot.indicators.macd.series).toBeNull();
    expect(snapshot.indicators.ma5.value).toBe(140.8);
  });

  it("treats an unavailable indicator as having no series to draw", () => {
    // The series shares the indicator's quality: one the gateway could not
    // measure has nothing to draw, and an empty line would read as a
    // measurement of zero.
    const payload = stockSnapshotWithSeriesFixture();
    payload.indicators.ma5.qualityStatus = "unavailable";
    payload.indicators.ma5.value = null as unknown as number;

    const snapshot = decodeStockSnapshotEnvelope(payload, { now });

    expect(snapshot.indicators.ma5.series).toBeNull();
  });

  it.each([
    ["short series", (value: ReturnType<typeof stockSnapshotWithSeriesFixture>) => {
      value.indicators.ma5.series = [140.8];
    }],
    ["long series", (value: ReturnType<typeof stockSnapshotWithSeriesFixture>) => {
      value.indicators.ma5.series = [140.2, 140.8, 141.4];
    }],
    ["non-numeric entry", (value: ReturnType<typeof stockSnapshotWithSeriesFixture>) => {
      (value.indicators.ma5.series as unknown[])[1] = "140.8";
    }],
    ["a series that is not an array", (value: ReturnType<typeof stockSnapshotWithSeriesFixture>) => {
      value.indicators.ma5.series = { values: [140.2, 140.8] } as never;
    }],
    ["ragged macd series", (value: ReturnType<typeof stockSnapshotWithSeriesFixture>) => {
      value.indicators.macd.series!.signal = [0.25];
    }],
  ])("rejects a series that cannot be drawn on the candles: %s", (_label, mutate) => {
    // A series one bar out of step draws every point against the wrong
    // candle, which looks plausible rather than broken.
    const payload = stockSnapshotWithSeriesFixture();
    mutate(payload);

    expect(() => decodeStockSnapshotEnvelope(payload, { now })).toThrow(/series/);
  });
});

it("reads an indicator series the gateway sends as a bare array", () => {
  // The gateway publishes the values alongside the indicator's own source,
  // timestamps, method version and quality — the series has no separate
  // provenance because it has none to have. Requiring a nested envelope meant
  // the chart said "服务端未提供版本化序列" while the server was sending them.
  const payload = stockSnapshotFixture();
  const candles = payload.completedCandles.length;
  payload.indicators.ma5 = {
    ...payload.indicators.ma5,
    series: Array.from({ length: candles }, (_unused, index) =>
      index < 4 ? null : 100 + index,
    ),
  };

  const snapshot = decodeStockSnapshotEnvelope(payload, { now, maxAgeMs: 60_000 });

  expect(snapshot.indicators.ma5.series?.values).toHaveLength(candles);
  expect(snapshot.indicators.ma5.series?.values[0]).toBeNull();
  expect(snapshot.indicators.ma5.series?.methodVersion).toBe(
    payload.indicators.ma5.methodVersion,
  );
});
