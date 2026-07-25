import { describe, expect, it, jest } from "@jest/globals";

import { toDemoChartSnapshot, type WatchlistQuote } from "@/domain/models";
import { stockFixtures } from "@/fixtures/stocks";
import {
  createMarketGatewayClient,
  decodeCandleEnvelope,
  decodeStockSnapshotEnvelope,
  decodeWatchlistEnvelope,
  GatewayRequestError,
} from "../marketGateway";
import { stockSnapshotFixture } from "./stockSnapshot.fixture";

const now = new Date("2026-07-25T16:00:00.000Z");
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
    ["stale", "2026-07-25T15:58:00.000Z", "2026-07-25T15:58:01.000Z"],
    ["future", "2026-07-25T16:00:03.000Z", "2026-07-25T16:00:04.000Z"],
  ])("rejects %s watchlist snapshots", (_label, asOf, availableAt) => {
    expect(() =>
      decodeWatchlistEnvelope(
        {
          schemaVersion: "1",
          source: "moomoo",
          session: "healthy",
          asOf,
          availableAt,
          items: [],
        },
        { maxAgeMs: 30_000, now },
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
    ["future decision cutoff", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.decisionCutoff = "2026-07-25T16:00:00.001Z";
    }],
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
    ["stale response", (value: ReturnType<typeof stockSnapshotFixture>) => {
      value.decisionCutoff = "2026-07-25T15:00:00.000Z";
    }],
  ])("rejects a %s snapshot", (_label, mutate) => {
    const value = stockSnapshotFixture();
    mutate(value);

    expect(() => decodeStockSnapshotEnvelope(value, { maxAgeMs: 30_000, now })).toThrow();
  });

  it("adapts an explicit demo stock into the shared chart shape", () => {
    const chart = toDemoChartSnapshot(stockFixtures["NVDA:short"]!);

    expect(chart).toMatchObject({
      demoData: true,
      source: { source: "fixture", status: "demo" },
      symbol: "NVDA",
      forecast: stockFixtures["NVDA:short"]!.forecast,
      candles: stockFixtures["NVDA:short"]!.candles,
      indicators: {
        rsi: { value: stockFixtures["NVDA:short"]!.indicators.rsi.value },
        macd: { line: stockFixtures["NVDA:short"]!.indicators.macd.dif },
      },
    });
  });
});

describe("market gateway fallback", () => {
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

  it("fetches a live stock snapshot and never substitutes a fixture", async () => {
    const fetchImpl = jest.fn(async () =>
      jsonResponse(stockSnapshotFixture()),
    ) as unknown as typeof fetch;
    const client = createMarketGatewayClient({
      baseUrl: "http://127.0.0.1:8765",
      fetchImpl,
      now: () => now,
    });

    const result = await client.getStockSnapshot("nvda", "5m", 200);

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/stock-snapshot?symbol=NVDA&interval=5m&count=200",
      expect.objectContaining({ method: "GET" }),
    );
    expect(result).toMatchObject({ demoData: false, source: { source: "moomoo" } });
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
    ["malformed", async () => jsonResponse({ schemaVersion: "wrong" }), "malformed"],
    [
      "timeout",
      async () => { throw Object.assign(new Error("timeout"), { name: "AbortError" }); },
      "timeout",
    ],
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
