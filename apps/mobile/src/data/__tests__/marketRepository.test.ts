import { expect, it, jest } from "@jest/globals";

import {
  createGatewayMarketRepository,
  createMarketRepository,
  isRetryableMarketError,
  MarketDataError,
  type MarketDataErrorCategory,
} from "../marketRepository";
import { describeMarketError } from "@/i18n/marketErrorCopy";
import { stockSnapshotV3Fixture } from "./stockSnapshotV3.fixture";

function jsonResponse(value: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => value,
  } as Response;
}

it("does not start a snapshot load for an already-aborted consumer", async () => {
  let loadStarted = false;
  const repository = createMarketRepository({
    async loadSnapshot() {
      loadStarted = true;
      return new Promise<never>(() => {});
    },
    async loadWatchlist() {
      return new Promise<never>(() => {});
    },
  });
  const caller = new AbortController();
  caller.abort();

  await expect(
    repository.getStockSnapshot(
      { symbol: "NVDA", interval: "5m", count: 200 },
      { signal: caller.signal },
    ),
  ).rejects.toMatchObject({ name: "AbortError" });
  await Promise.resolve();

  expect(loadStarted).toBe(false);
});

it("does not start a watchlist load for an already-aborted consumer", async () => {
  let loadStarted = false;
  const repository = createMarketRepository({
    async loadSnapshot() {
      return new Promise<never>(() => {});
    },
    async loadWatchlist() {
      loadStarted = true;
      return new Promise<never>(() => {});
    },
  });
  const caller = new AbortController();
  caller.abort();

  await expect(
    repository.getWatchlist({ signal: caller.signal }),
  ).rejects.toMatchObject({ name: "AbortError" });
  await Promise.resolve();

  expect(loadStarted).toBe(false);
});

async function requestWatchlist(
  reply: () => Promise<Response>,
): Promise<unknown> {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = jest.fn(reply) as unknown as typeof fetch;
  try {
    const repository = createGatewayMarketRepository({
      apiUrl: "http://127.0.0.1:8765",
    });
    return await repository.getWatchlist({ forceRefresh: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
}

async function requestStockSnapshot(
  reply: () => Promise<Response>,
): Promise<unknown> {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = jest.fn(reply) as unknown as typeof fetch;
  try {
    const repository = createGatewayMarketRepository({
      apiUrl: "http://127.0.0.1:8765",
    });
    return await repository.getStockSnapshot(
      { symbol: "NVDA", interval: "5m", count: 200 },
      { forceRefresh: true },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
}

it.each([
  // A 401 with no code names the device token, not the brokerage session.
  ["HTTP 401", async () => jsonResponse({}, 401), "auth-required"],
  ["HTTP 403", async () => jsonResponse({}, 403), "permission"],
  [
    "offline transport",
    async () => {
      throw new Error("offline");
    },
    "offline",
  ],
  [
    "stale response",
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
    "stale",
  ],
  [
    "schema validation",
    async () => jsonResponse({ schemaVersion: "wrong" }),
    "validation",
  ],
])("preserves %s as a repository error", async (_label, reply, category) => {
  await expect(requestWatchlist(reply)).rejects.toMatchObject({
    name: "MarketDataError",
    category,
  });
});

it("returns only a strict live watchlist from the production repository", async () => {
  const asOf = new Date().toISOString();
  const result = await requestWatchlist(async () =>
    jsonResponse({
      schemaVersion: "1",
      source: "moomoo",
      session: "healthy",
      asOf,
      availableAt: asOf,
      items: [
        {
          code: "US.NVDA",
          price: 142.25,
          changePercent: 2.4,
          availableAt: asOf,
        },
      ],
    }),
  );

  expect(result).toMatchObject({
    source: "moomoo",
    asOf,
    quotes: [{ symbol: "NVDA", price: 142.25 }],
  });
});

it("preserves an unknown snapshot major as client-update-required", async () => {
  const payload = stockSnapshotV3Fixture();
  payload.schemaVersion = "4";

  await expect(
    requestStockSnapshot(async () => jsonResponse(payload)),
  ).rejects.toMatchObject({
    name: "MarketDataError",
    category: "client-update-required",
  });
  expect(describeMarketError("client-update-required")).toEqual({
    label: "需更新",
    title: "App 与行情网关版本不兼容",
    body: "行情网关返回了本版 App 不认识的新主版本。App 不会猜测字段含义，也不会退回旧接口或演示数据。请同时更新 App 和行情网关后重试。",
  });
});

/**
 * Retrying is a claim that waiting will help. Making it about a missing SDK or
 * a revoked pairing keeps the screen looking busy while it is actually waiting
 * for a person, and that person never learns they are the blocker.
 */
it.each<[MarketDataErrorCategory, boolean]>([
  ["offline", true],
  ["timeout", true],
  ["stale", true],
  // A quota resets on its own, and the caller backs off between attempts.
  ["rate-limited", true],
  ["malformed", false],
  ["analysis-failed", false],
  ["sdk-unavailable", false],
  ["auth-required", false],
  ["login-required", false],
  ["permission", false],
  ["contract", false],
  ["client-update-required", false],
  ["validation", false],
  ["unspecified", false],
])("retries %s: %s", (category, retryable) => {
  expect(
    isRetryableMarketError(new MarketDataError(category, category)),
  ).toBe(retryable);
});
