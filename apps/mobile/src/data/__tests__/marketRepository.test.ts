import { expect, it, jest } from "@jest/globals";

import {
  createGatewayMarketRepository,
} from "../marketRepository";

function jsonResponse(value: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => value,
  } as Response;
}

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

it.each([
  ["HTTP 401", async () => jsonResponse({}, 401), "login-required"],
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
    async () => {
      const asOf = new Date(Date.now() - 61_000).toISOString();
      const availableAt = new Date(Date.now() - 60_000).toISOString();
      return jsonResponse({
        schemaVersion: "1",
        source: "moomoo",
        session: "healthy",
        asOf,
        availableAt,
        items: [],
      });
    },
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
