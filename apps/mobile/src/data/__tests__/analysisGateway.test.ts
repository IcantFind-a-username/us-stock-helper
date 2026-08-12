import { describe, expect, it, jest } from "@jest/globals";

import { createAnalysisClient, decodeDecisionEnvelope } from "../analysisGateway";

import { decisionFixture } from "./decision.fixture";

const now = new Date("2026-07-25T16:00:10.000Z");

function jsonResponse(value: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => value,
  } as Response;
}

describe("decision envelope validation", () => {
  it("decodes a live decision with its coverage intact", () => {
    const decision = decodeDecisionEnvelope(decisionFixture(), { now });

    expect(decision).toMatchObject({
      status: "live",
      symbol: "NVDA",
      horizon: "short",
      decisionCutoff: "2026-07-25T16:00:00.000Z",
    });
    expect(decision.score).toMatchObject({
      value: 72.5,
      direction: "bullish",
      factorCoverage: 0.7,
    });
    expect(decision.score?.unavailableFactors).toContain("macro");
    expect(decision.notes).toHaveLength(1);
  });

  it("keeps an unavailable factor as null rather than zero", () => {
    const decision = decodeDecisionEnvelope(decisionFixture(), { now });

    const macro = decision.score?.contributions.find(
      (item) => item.name === "macro",
    );
    expect(macro?.rawValue).toBeNull();
    expect(macro?.points).toBe(0);
  });

  it("accepts a decision with no forecast and keeps the reason", () => {
    const value = decisionFixture();
    value.forecast = null;
    value.riskPlan = null;
    value.notes = ["Realized volatility could not be measured."];

    const decision = decodeDecisionEnvelope(value, { now });

    // The absence is the message: a caller must not be able to mistake it for
    // a forecast that simply failed to render.
    expect(decision.forecast).toBeNull();
    expect(decision.riskPlan).toBeNull();
    expect(decision.notes[0]).toContain("volatility");
  });

  it("accepts an explicitly unavailable decision", () => {
    const value = decisionFixture();
    value.status = "unavailable";
    value.score = null;
    value.forecast = null;
    value.riskPlan = null;

    const decision = decodeDecisionEnvelope(value, { now });

    expect(decision.status).toBe("unavailable");
    expect(decision.score).toBeNull();
  });

  it.each([
    ["an unsupported schema version", (value: ReturnType<typeof decisionFixture>) => {
      value.schemaVersion = "2";
    }],
    ["a decision cutoff in the future", (value: ReturnType<typeof decisionFixture>) => {
      value.decisionCutoff = "2030-01-01T00:00:00.000Z";
    }],
    ["a coverage outside zero to one", (value: ReturnType<typeof decisionFixture>) => {
      (value.score as Record<string, unknown>).factorCoverage = 1.4;
    }],
    ["a score outside zero to one hundred", (value: ReturnType<typeof decisionFixture>) => {
      (value.score as Record<string, unknown>).value = 140;
    }],
    ["scenario probabilities that do not sum to one", (value: ReturnType<typeof decisionFixture>) => {
      const cases = (value.forecast as { cases: { probability: number }[] }).cases;
      cases[0]!.probability = 0.9;
    }],
    ["a forecast missing one of its three scenarios", (value: ReturnType<typeof decisionFixture>) => {
      const forecast = value.forecast as { cases: unknown[] };
      forecast.cases = forecast.cases.slice(0, 2);
    }],
    ["a live status with no score", (value: ReturnType<typeof decisionFixture>) => {
      value.score = null;
    }],
    ["a citation without a source link", (value: ReturnType<typeof decisionFixture>) => {
      value.citations[0]!.url = "";
    }],
  ])("rejects %s", (_label, mutate) => {
    const value = decisionFixture();
    mutate(value);

    expect(() => decodeDecisionEnvelope(value, { now })).toThrow();
  });

  it("rejects a payload carrying anything that could place an order", () => {
    const value = decisionFixture() as Record<string, unknown>;
    value.submitOrder = { quantity: 100 };

    // The server has no such field; if one ever appears the app must refuse
    // the payload rather than render around it.
    expect(() => decodeDecisionEnvelope(value, { now })).toThrow(/order/i);
  });
});

describe("analysis client transport", () => {
  it("requests one decision over an authorized LAN origin", async () => {
    const fetchImpl = jest.fn(async () =>
      jsonResponse(decisionFixture()),
    ) as unknown as typeof fetch;
    const client = createAnalysisClient({
      baseUrl: "http://192.168.1.10:8788/",
      authorizationToken: "0123456789abcdef0123456789abcdef",
      fetchImpl,
      now: () => now,
    });

    const decision = await client.getDecision("nvda", "short");

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://192.168.1.10:8788/decision?symbol=NVDA&horizon=short",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer 0123456789abcdef0123456789abcdef",
        }),
      }),
    );
    expect(decision).toMatchObject({
      status: "live",
      symbol: "NVDA",
      horizon: "short",
    });
    expect(decision.score?.factorCoverage).toBe(0.7);
  });

  it("requires an ephemeral token before connecting to a LAN analysis service", () => {
    expect(() =>
      createAnalysisClient({
        baseUrl: "http://192.168.1.10:8788",
        fetchImpl: jest.fn() as unknown as typeof fetch,
      }),
    ).toThrow(/token/i);
  });

  it("rejects a LAN token shorter than the 32-character runtime policy", () => {
    expect(() =>
      createAnalysisClient({
        baseUrl: "http://192.168.1.10:8788",
        authorizationToken: "x".repeat(31),
        fetchImpl: jest.fn() as unknown as typeof fetch,
      }),
    ).toThrow(/32/);
  });

  it.each([
    "ftp://127.0.0.1:8788",
    "http://user:secret@127.0.0.1:8788",
    "http://127.0.0.1:8788/api?token=secret",
    "not-a-url",
  ])("rejects an unsafe analysis base URL: %s", (baseUrl) => {
    expect(() =>
      createAnalysisClient({
        baseUrl,
        fetchImpl: jest.fn() as unknown as typeof fetch,
      }),
    ).toThrow(/baseUrl/i);
  });

  it("returns an explicitly unavailable decision rather than inventing one", async () => {
    const value = decisionFixture();
    value.status = "unavailable";
    value.score = null;
    value.forecast = null;
    value.riskPlan = null;
    value.notes = ["No completed candles were available."];
    const client = createAnalysisClient({
      baseUrl: "http://127.0.0.1:8788",
      fetchImpl: jest.fn(async () => jsonResponse(value)) as unknown as typeof fetch,
      now: () => now,
    });

    const decision = await client.getDecision("NVDA", "short");

    expect(decision.status).toBe("unavailable");
    expect(decision.score).toBeNull();
    expect(decision.notes[0]).toContain("No completed candles");
  });

  it("rejects a decision that answers a different question than it was asked", async () => {
    const value = decisionFixture();
    value.symbol = "TSLA";
    const client = createAnalysisClient({
      baseUrl: "http://127.0.0.1:8788",
      fetchImpl: jest.fn(async () => jsonResponse(value)) as unknown as typeof fetch,
      now: () => now,
    });

    await expect(client.getDecision("NVDA", "short")).rejects.toMatchObject({
      name: "AnalysisRequestError",
      kind: "malformed",
    });
  });

  it.each([
    [
      "login required",
      async () => jsonResponse({}, 401),
      "login-required",
    ],
    [
      "permission denied",
      async () => jsonResponse({ error: { code: "PERMISSION_DENIED" } }, 403),
      "permission",
    ],
    [
      "offline",
      async () => {
        throw new Error("connection refused");
      },
      "offline",
    ],
    [
      "a rejected argument",
      async () =>
        jsonResponse({ error: { code: "INVALID_ARGUMENT" } }, 400),
      "contract",
    ],
    [
      "a failed chain",
      async () => jsonResponse({ error: { code: "ANALYSIS_FAILED" } }, 500),
      "malformed",
    ],
    [
      "an unreadable body",
      async () =>
        ({
          ok: true,
          status: 200,
          json: async () => {
            throw new Error("not json");
          },
        }) as unknown as Response,
      "malformed",
    ],
    [
      "an unsupported schema",
      async () => jsonResponse({ schemaVersion: "9" }),
      "malformed",
    ],
  ])("classifies %s without falling back to demo analysis", async (_label, reply, kind) => {
    const client = createAnalysisClient({
      baseUrl: "http://127.0.0.1:8788",
      fetchImpl: jest.fn(reply) as unknown as typeof fetch,
      now: () => now,
    });

    await expect(client.getDecision("NVDA", "short")).rejects.toMatchObject({
      name: "AnalysisRequestError",
      kind,
    });
  });

  it("aborts the fetch and reports AbortError when the caller cancels first", async () => {
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
    const client = createAnalysisClient({
      baseUrl: "http://127.0.0.1:8788",
      fetchImpl,
      now: () => now,
    });

    const request = client.getDecision("NVDA", "short", caller.signal);
    await Promise.resolve();
    caller.abort();

    expect(fetchSignal?.aborted).toBe(true);
    await expect(request).rejects.toMatchObject({ name: "AbortError" });
  });

  it("refuses to start once the caller has already cancelled", async () => {
    const caller = new AbortController();
    caller.abort();
    const fetchImpl = jest.fn() as unknown as typeof fetch;
    const client = createAnalysisClient({
      baseUrl: "http://127.0.0.1:8788",
      fetchImpl,
      now: () => now,
    });

    await expect(
      client.getDecision("NVDA", "short", caller.signal),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("aborts and classifies a decision request that outruns its deadline", async () => {
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
                  Object.assign(new Error("timed out"), { name: "AbortError" }),
                ),
              { once: true },
            );
          }),
      ) as unknown as typeof fetch;
      const client = createAnalysisClient({
        baseUrl: "http://127.0.0.1:8788",
        fetchImpl,
        now: () => now,
        timeoutMs: 25,
      });

      const request = client.getDecision("NVDA", "short");
      await Promise.resolve();
      jest.advanceTimersByTime(25);

      expect(fetchSignal?.aborted).toBe(true);
      await expect(request).rejects.toMatchObject({
        name: "AnalysisRequestError",
        kind: "timeout",
      });
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      jest.useRealTimers();
    }
  });

  it("keeps caller cancellation distinct from a timeout that follows it", async () => {
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
      const client = createAnalysisClient({
        baseUrl: "http://127.0.0.1:8788",
        fetchImpl,
        now: () => now,
        timeoutMs: 25,
      });

      const request = client.getDecision("NVDA", "short", caller.signal);
      await Promise.resolve();
      caller.abort();
      jest.advanceTimersByTime(25);

      await expect(request).rejects.toMatchObject({ name: "AbortError" });
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      jest.useRealTimers();
    }
  });
});
