import { describe, expect, it, jest } from "@jest/globals";

import { createAnalysisClient, decodeDecisionEnvelope } from "../analysisGateway";

import {
  adviserCouncilFixture,
  adviserUsageFixture,
  decisionFixture,
  newsInterpretationFixture,
} from "./decision.fixture";

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
      interval: "day",
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
    ["a risk plan entry range with a non-numeric member", (value: ReturnType<typeof decisionFixture>) => {
      (value.riskPlan as Record<string, unknown>).entryRange = ["12.5", "abc"];
    }],
    ["a risk plan entry range with only one bound", (value: ReturnType<typeof decisionFixture>) => {
      (value.riskPlan as Record<string, unknown>).entryRange = [118.3];
    }],
    ["a risk plan entry range with reversed bounds", (value: ReturnType<typeof decisionFixture>) => {
      (value.riskPlan as Record<string, unknown>).entryRange = [125, 118];
    }],
    ["a risk plan target range with a non-numeric member", (value: ReturnType<typeof decisionFixture>) => {
      (value.riskPlan as Record<string, unknown>).targetRange = ["122", "abc"];
    }],
    ["a risk plan target range with only one bound", (value: ReturnType<typeof decisionFixture>) => {
      (value.riskPlan as Record<string, unknown>).targetRange = [122.0];
    }],
    ["a risk plan invalidation price that is NaN", (value: ReturnType<typeof decisionFixture>) => {
      (value.riskPlan as Record<string, unknown>).invalidationPrice = NaN;
    }],
    ["a risk plan invalidation price that is infinite", (value: ReturnType<typeof decisionFixture>) => {
      (value.riskPlan as Record<string, unknown>).invalidationPrice = Infinity;
    }],
    ["a risk plan invalidation price that is a numeric string", (value: ReturnType<typeof decisionFixture>) => {
      (value.riskPlan as Record<string, unknown>).invalidationPrice = "114.7";
    }],
  ])("rejects %s", (_label, mutate) => {
    const value = decisionFixture();
    mutate(value);

    expect(() => decodeDecisionEnvelope(value, { now })).toThrow();
  });

  it("accepts a risk plan whose ranges collapse to a single price", () => {
    const value = decisionFixture();
    (value.riskPlan as Record<string, unknown>).entryRange = [119.0, 119.0];

    const decision = decodeDecisionEnvelope(value, { now });

    expect(decision.riskPlan?.entryRange).toEqual([119.0, 119.0]);
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

  it("adds news adviser mode only to an explicit single-stock request", async () => {
    const fetchImpl = jest.fn(async () =>
      jsonResponse(decisionFixture()),
    ) as unknown as typeof fetch;
    const client = createAnalysisClient({
      baseUrl: "http://127.0.0.1:8788",
      fetchImpl,
      now: () => now,
    });

    await client.getDecision("nvda", "short", undefined, { adviser: "news" });

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://127.0.0.1:8788/decision?symbol=NVDA&horizon=short&adviser=news",
      expect.any(Object),
    );
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
      kind: "validation",
    });
  });

  it.each([
    [
      // This service answers 401 only when the device gate rejects the phone's
      // token; the brokerage login is a different service's problem.
      "an unusable device token",
      async () => jsonResponse({}, 401),
      "auth-required",
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
      "invalid-request",
    ],
    [
      "a failed chain",
      async () => jsonResponse({ error: { code: "ANALYSIS_FAILED" } }, 500),
      "analysis-failed",
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
      "validation",
    ],
    [
      "an unsupported schema",
      async () => jsonResponse({ schemaVersion: "9" }),
      "validation",
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

  it("does not abandon a live deterministic decision at the old eight-second deadline", async () => {
    jest.useFakeTimers();
    try {
      let fetchSignal: AbortSignal | undefined;
      const fetchImpl = jest.fn(
        async (_url: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((resolve, reject) => {
            fetchSignal = init?.signal as AbortSignal;
            const answer = setTimeout(
              () => resolve(jsonResponse(decisionFixture())),
              9_000,
            );
            fetchSignal.addEventListener(
              "abort",
              () => {
                clearTimeout(answer);
                reject(
                  Object.assign(new Error("request aborted"), {
                    name: "AbortError",
                  }),
                );
              },
              { once: true },
            );
          }),
      ) as unknown as typeof fetch;
      const client = createAnalysisClient({
        baseUrl: "http://127.0.0.1:8788",
        fetchImpl,
        now: () => now,
      });

      const request = client.getDecision("NVDA", "short");
      await jest.advanceTimersByTimeAsync(9_000);

      expect(fetchSignal?.aborted).toBe(false);
      await expect(request).resolves.toMatchObject({
        symbol: "NVDA",
        interval: "day",
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

it("rejects an unavailable decision that still carries a score", () => {
  // The two states mean different things and the screens render them
  // differently: leaving this open let one payload read as a live 72.5 on the
  // dashboard and as "暂不可用" on the stock page.
  const value = decisionFixture();
  value.status = "unavailable";

  expect(() => decodeDecisionEnvelope(value, { now })).toThrow();
});

it("tolerates the clock skew between this device and the service", () => {
  // The service stamps the cutoff at the instant it answers, so by the time
  // the payload lands here that instant is a few milliseconds old — or a few
  // milliseconds in the future if this device's clock lags. Rejecting on that
  // turns every decision into "malformed" for no reason. The check exists to
  // catch a service claiming to know the future, which is minutes, not
  // milliseconds.
  const value = decisionFixture();
  value.decisionCutoff = new Date(now.getTime() + 3_000).toISOString();

  const decision = decodeDecisionEnvelope(value, { now });

  expect(decision.decisionCutoff).toBe(value.decisionCutoff);
});

it("still refuses a cutoff that is meaningfully in the future", () => {
  const value = decisionFixture();
  value.decisionCutoff = new Date(now.getTime() + 20 * 60_000).toISOString();

  expect(() => decodeDecisionEnvelope(value, { now })).toThrow(/future/);
});

/**
 * "The decision chain could not be evaluated" is a statement about the chain,
 * not about the payload. Reporting it as a malformed response sent the reader
 * looking for corrupt data that was never there.
 */
describe("analysis failure classification", () => {
  function clientReplying(reply: () => Promise<Response>) {
    return createAnalysisClient({
      baseUrl: "http://127.0.0.1:8788",
      fetchImpl: jest.fn(reply) as unknown as typeof fetch,
      now: () => now,
    });
  }

  it.each([
    ["INVALID_ARGUMENT", 400, "invalid-request"],
    ["AUTH_REQUIRED", 401, "auth-required"],
    ["CLIENT_NOT_ALLOWED", 403, "client-not-allowed"],
    ["PERMISSION_DENIED", 403, "permission"],
    ["PATH_NOT_ALLOWED", 404, "route-unsupported"],
    ["METHOD_NOT_ALLOWED", 405, "route-unsupported"],
    ["ANALYSIS_FAILED", 500, "analysis-failed"],
    ["AUTH_UNAVAILABLE", 503, "auth-unavailable"],
  ])("gives %s its own kind", async (code, status, kind) => {
    const client = clientReplying(async () =>
      jsonResponse({ error: { code, message: "服务端说明" } }, status),
    );

    await expect(client.getDecision("NVDA", "short")).rejects.toMatchObject({
      name: "AnalysisRequestError",
      kind,
    });
  });

  it("does not report a declined analysis as a broken payload", async () => {
    const client = clientReplying(async () =>
      jsonResponse({ error: { code: "ANALYSIS_FAILED" } }, 500),
    );

    const error = (await client
      .getDecision("NVDA", "short")
      .catch((caught: unknown) => caught)) as { kind: string };

    expect(error.kind).toBe("analysis-failed");
    expect(error.kind).not.toBe("malformed");
  });

  it("says the service named a code this build does not know", async () => {
    // The service's vocabulary is allowed to grow. What must not happen is a
    // new code silently inheriting the explanation of an old one.
    const client = clientReplying(async () =>
      jsonResponse({ error: { code: "SOMETHING_NEW" } }, 500),
    );

    await expect(client.getDecision("NVDA", "short")).rejects.toMatchObject({
      name: "AnalysisRequestError",
      kind: "unspecified",
    });
  });

  it("keeps a body this app cannot decode apart from a declined analysis", async () => {
    const client = clientReplying(async () => jsonResponse({ schemaVersion: "9" }));

    await expect(client.getDecision("NVDA", "short")).rejects.toMatchObject({
      name: "AnalysisRequestError",
      kind: "validation",
    });
  });

  it("keeps every analysis code mapped to a kind of its own", async () => {
    const codes = [
      "INVALID_ARGUMENT",
      "AUTH_REQUIRED",
      "CLIENT_NOT_ALLOWED",
      "PERMISSION_DENIED",
      "PATH_NOT_ALLOWED",
      "ANALYSIS_FAILED",
      "AUTH_UNAVAILABLE",
    ];
    const kinds = await Promise.all(
      codes.map(async (code) => {
        const client = clientReplying(async () =>
          jsonResponse({ error: { code } }, 500),
        );
        const error = (await client
          .getDecision("NVDA", "short")
          .catch((caught: unknown) => caught)) as { kind: string };
        return error.kind;
      }),
    );

    expect(new Set(kinds).size).toBe(codes.length);
  });
});

/**
 * The adviser layer is optional and it costs money, so its two blocks have
 * three states rather than two. A block that merely arrived null could mean
 * nobody asked for it, the model was unreachable, or the server predates the
 * feature entirely — and the screen renders those three differently.
 */
describe("the adviser layer's two blocks", () => {
  it("keeps a block nobody asked for distinct from one that failed", () => {
    const quiet = decodeDecisionEnvelope(decisionFixture(), { now });

    const failed = decisionFixture();
    failed.newsInterpretation = {
      status: "unavailable",
      reason: "模型请求超时。",
      value: null,
    };

    expect(quiet.newsInterpretation?.status).toBe("not-requested");
    expect(quiet.newsInterpretation?.value).toBeNull();
    expect(quiet.newsInterpretation?.reason).toBeTruthy();
    expect(
      decodeDecisionEnvelope(failed, { now }).newsInterpretation?.status,
    ).toBe("unavailable");
  });

  it("reads a server that has never heard of these fields as null", () => {
    // An older deployment answers without them. That is not a malformed
    // payload and must not take the whole decision down with it.
    const value = decisionFixture() as Record<string, unknown>;
    delete value.newsInterpretation;
    delete value.adviserCouncil;
    delete value.adviserUsage;

    const decision = decodeDecisionEnvelope(value, { now });

    expect(decision.newsInterpretation).toBeNull();
    expect(decision.adviserCouncil).toBeNull();
    expect(decision.adviserUsage).toBeNull();
    expect(decision.status).toBe("live");
  });

  it("decodes an interpretation with every citation intact", () => {
    const value = decisionFixture();
    value.newsInterpretation = newsInterpretationFixture();

    const block = decodeDecisionEnvelope(value, { now }).newsInterpretation;

    expect(block?.status).toBe("available");
    expect(block?.value?.crossSourceReading).toContain("相互独立");
    const conclusion = block?.value?.investmentImpact[0];
    expect(conclusion?.statement).toBeTruthy();
    expect(conclusion?.citations[0]).toMatchObject({
      evidenceId: "a",
      quote: "raises full-year revenue guidance",
      url: "https://reuters.example/a",
      publisher: "reuters",
      availableAt: "2026-07-25T15:41:00Z",
    });
    expect(block?.value?.unknowns).toHaveLength(1);
  });

  it("decodes the council's stance, blind spot and gated score", () => {
    const value = decisionFixture();
    value.adviserCouncil = adviserCouncilFixture();

    const block = decodeDecisionEnvelope(value, { now }).adviserCouncil;

    expect(block?.status).toBe("available");
    const opinion = block?.value?.opinions[0];
    expect(opinion?.frameworkId).toBe("technical");
    expect(opinion?.stance).toBe("bullish");
    // A framework that never names what it cannot see is being sold as
    // omniscient, which is the thing the council exists to avoid.
    expect(opinion?.blindSpot).toBeTruthy();
    expect(block?.value?.baselineScore).toBe(72.5);
    expect(block?.value?.adjustedScore).toBe(75.5);
    expect(block?.value?.disclaimer).toBeTruthy();
  });

  it("decodes what the call actually spent", () => {
    const value = decisionFixture();
    value.adviserUsage = adviserUsageFixture();

    const usage = decodeDecisionEnvelope(value, { now }).adviserUsage;

    expect(usage?.costUsd).toBeCloseTo(0.163, 6);
    expect(usage?.inputTokens).toBe(13000);
    expect(usage?.cacheReadInputTokens).toBe(2000);
    expect(usage?.model).toBe("claude-opus-4-8");
  });

  it.each([
    [
      "a block claiming to be available with nothing in it",
      (value: ReturnType<typeof decisionFixture>) => {
        value.newsInterpretation = {
          status: "available",
          reason: null,
          value: null,
        };
      },
    ],
    [
      "a degraded block that does not say why",
      (value: ReturnType<typeof decisionFixture>) => {
        value.newsInterpretation = {
          status: "unavailable",
          reason: null,
          value: null,
        };
      },
    ],
    [
      "a status this app does not know",
      (value: ReturnType<typeof decisionFixture>) => {
        value.newsInterpretation = {
          status: "pending",
          reason: "稍后再看",
          value: null,
        };
      },
    ],
    [
      "a conclusion with no citation behind it",
      (value: ReturnType<typeof decisionFixture>) => {
        const block = newsInterpretationFixture();
        block.value.investmentImpact[0]!.citations = [];
        value.newsInterpretation = block;
      },
    ],
    [
      "a citation with no source link",
      (value: ReturnType<typeof decisionFixture>) => {
        const block = newsInterpretationFixture();
        block.value.investmentImpact[0]!.citations[0]!.url = "";
        value.newsInterpretation = block;
      },
    ],
    [
      "a citation the reader would open over plain http",
      (value: ReturnType<typeof decisionFixture>) => {
        const block = newsInterpretationFixture();
        block.value.investmentImpact[0]!.citations[0]!.url =
          "http://reuters.example/a";
        value.newsInterpretation = block;
      },
    ],
    [
      "a conclusion whose citation quotes nothing",
      (value: ReturnType<typeof decisionFixture>) => {
        const block = newsInterpretationFixture();
        block.value.investmentImpact[0]!.citations[0]!.quote = "";
        value.newsInterpretation = block;
      },
    ],
    [
      "an interpretation with no investment impact at all",
      (value: ReturnType<typeof decisionFixture>) => {
        const block = newsInterpretationFixture();
        block.value.investmentImpact = [];
        value.newsInterpretation = block;
      },
    ],
    [
      "a usage line reporting a negative cost",
      (value: ReturnType<typeof decisionFixture>) => {
        value.adviserUsage = { ...adviserUsageFixture(), costUsd: -1 };
      },
    ],
    [
      "a council opinion that names no blind spot",
      (value: ReturnType<typeof decisionFixture>) => {
        const block = adviserCouncilFixture();
        block.value.opinions[0]!.blindSpot = "";
        value.adviserCouncil = block;
      },
    ],
  ])("refuses %s", (_label, mutate) => {
    const value = decisionFixture();
    mutate(value);

    expect(() => decodeDecisionEnvelope(value, { now })).toThrow();
  });
});
