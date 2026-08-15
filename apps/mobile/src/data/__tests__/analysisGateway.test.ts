import { describe, expect, it, jest } from "@jest/globals";

import {
  createAnalysisClient,
  decodeDecisionEnvelope,
  decodeMarketBriefEnvelope,
} from "../analysisGateway";

import {
  adviserCouncilFixture,
  adviserUsageFixture,
  decisionFixture,
  newsInterpretationFixture,
} from "./decision.fixture";

const now = new Date("2026-07-25T16:00:10.000Z");
const marketBriefCutoff = "2026-07-25T16:00:00.000Z";

function jsonResponse(value: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => value,
  } as Response;
}

/**
 * The unsourced eight, exactly as `market_brief.py`'s `_UNSOURCED_REASON`
 * names them -- copied verbatim rather than paraphrased, so a decoder test
 * that asserts on the string is testing the wire contract, not a rewording
 * of it.
 */
const UNSOURCED_DRIVER_REASON: Record<string, string> = {
  breadth: "大盘涨跌家数、新高新低等广度数据源尚未接入。",
  "volatility-options": "波动率与期权持仓数据源尚未接入。",
  sector: "板块轮动强弱数据源尚未接入。",
  "rates-dollar": "利率与美元指数数据源尚未接入。",
  "macro-credit-energy": "信用利差与能源价格数据源尚未接入。",
  "liquidity-correlation": "流动性与相关性压力数据源尚未接入。",
  "broad-market-trend": "大盘趋势判定数据源尚未接入。",
  geopolitics: "地缘政治的独立驱动判定尚未接入，相关报道已计入整体新闻情绪。",
};

const ALL_DRIVER_CATEGORIES = [
  "news-sentiment",
  "breadth",
  "volatility-options",
  "sector",
  "rates-dollar",
  "macro-credit-energy",
  "liquidity-correlation",
  "broad-market-trend",
  "geopolitics",
];

function marketBriefFixture() {
  return {
    schemaVersion: "1",
    status: "available" as "available" | "unavailable",
    reason: null as string | null,
    decisionCutoff: marketBriefCutoff,
    marketSession: "regular" as
      | "premarket"
      | "regular"
      | "afterhours"
      | "closed",
    dataHealth: "fresh" as
      | "fresh"
      | "stale"
      | "conflict"
      | "insufficient"
      | null,
    sentiment: {
      conclusion: "偏多",
      actionScore: 0.42,
      uncertainty: ["独立来源不足"] as string[],
    } as Record<string, unknown> | null,
    driverCoverage: ALL_DRIVER_CATEGORIES.map((category) =>
      category === "news-sentiment"
        ? {
            category,
            available: true,
            conclusion: "偏多",
            actionScore: 0.42,
            missingReason: null as string | null,
          }
        : {
            category,
            available: false,
            conclusion: null as string | null,
            actionScore: null as number | null,
            missingReason: UNSOURCED_DRIVER_REASON[category]!,
          },
    ) as Record<string, unknown>[],
    citations: [
      {
        id: "C1",
        headline: "NVIDIA raises full-year revenue guidance",
        publisher: "reuters",
        url: "https://reuters.example/a",
        availableAt: "2026-07-25T15:44:00Z",
        freshnessSeconds: 1140,
        stale: false as boolean | null,
      },
    ] as Record<string, unknown>[],
    sourceGaps: [] as string[],
    notes: [] as string[],
  };
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

  it("keeps a null adviserAdjustment distinct from a measured zero when no council ran", () => {
    // decisionFixture()'s default is the common case: nobody paid for the
    // adviser council, so baselineScore mirrors score exactly and
    // adviserAdjustment is null -- not the 0.0 this app used to serve for
    // "nobody asked" and "the council found nothing to move" alike.
    const decision = decodeDecisionEnvelope(decisionFixture(), { now });

    expect(decision.baselineScore).toMatchObject({ value: 72.5 });
    expect(decision.adviserAdjustment).toBeNull();
  });

  it("folds the council's own verdict into the top-level fields when it actually ran", () => {
    const value = decisionFixture();
    (value.score as Record<string, unknown>).value = 75.5;
    value.adviserAdjustment = 3;
    value.adviserCouncil = adviserCouncilFixture();

    const decision = decodeDecisionEnvelope(value, { now });

    expect(decision.score?.value).toBe(75.5);
    expect(decision.baselineScore).toMatchObject({ value: 72.5 });
    expect(decision.adviserAdjustment).toBe(3);
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
    ["an adviser adjustment beyond the positive adviser cap", (value: ReturnType<typeof decisionFixture>) => {
      value.adviserAdjustment = 3.5;
    }],
    ["an adviser adjustment beyond the negative adviser cap", (value: ReturnType<typeof decisionFixture>) => {
      value.adviserAdjustment = -3.1;
    }],
    ["an adviser adjustment that is NaN", (value: ReturnType<typeof decisionFixture>) => {
      value.adviserAdjustment = NaN;
    }],
    ["an adviser adjustment that is a numeric string", (value: ReturnType<typeof decisionFixture>) => {
      (value as Record<string, unknown>).adviserAdjustment = "3";
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

/**
 * `GET /market-brief` reuses the Decision envelope's decoding conventions
 * exactly: null-means-absent, the same clock-skew tolerance, the same
 * whole-payload rejection on an embedded order/credential field, https-only
 * citations. The wire shape is frozen by
 * `.superpowers/sdd/2026-08-15-stage5-objective-review/market-brief-contract.md`.
 */
describe("market brief envelope validation", () => {
  it("decodes an available brief with its full nine-category coverage disclosure", () => {
    const brief = decodeMarketBriefEnvelope(marketBriefFixture(), { now });

    expect(brief).toMatchObject({
      status: "available",
      reason: null,
      decisionCutoff: "2026-07-25T16:00:00.000Z",
      marketSession: "regular",
      dataHealth: "fresh",
    });
    expect(brief.sentiment).toMatchObject({
      conclusion: "偏多",
      actionScore: 0.42,
      uncertainty: ["独立来源不足"],
    });
    expect(brief.driverCoverage).toHaveLength(9);
    expect(brief.sourceGaps).toEqual([]);
  });

  it("decodes the one sourced driver category with values and the rest as named absences", () => {
    const brief = decodeMarketBriefEnvelope(marketBriefFixture(), { now });

    const sourced = brief.driverCoverage.find(
      (item) => item.category === "news-sentiment",
    );
    expect(sourced).toMatchObject({
      available: true,
      conclusion: "偏多",
      actionScore: 0.42,
      missingReason: null,
    });

    const unsourced = brief.driverCoverage.filter(
      (item) => item.category !== "news-sentiment",
    );
    expect(unsourced).toHaveLength(8);
    for (const item of unsourced) {
      expect(item.available).toBe(false);
      // An absent field must arrive as an absence, never a fabricated zero
      // or an invented sentence standing in for one.
      expect(item.conclusion).toBeNull();
      expect(item.actionScore).toBeNull();
      expect(item.missingReason).toBeTruthy();
    }
  });

  it("passes the 情绪未测量 uncertainty marker through verbatim, actionScore included", () => {
    // 情绪未测量 is the disambiguator between "measured zero" and "nothing
    // measured": actionScore stays a real float even when nothing could be
    // read, and the marker string is how a reader tells the two apart.
    const value = marketBriefFixture();
    (value.sentiment as Record<string, unknown>).uncertainty = ["情绪未测量"];
    (value.sentiment as Record<string, unknown>).actionScore = 0.0;
    value.dataHealth = "insufficient";

    const brief = decodeMarketBriefEnvelope(value, { now });

    expect(brief.sentiment?.uncertainty).toEqual(["情绪未测量"]);
    expect(brief.sentiment?.actionScore).toBe(0.0);
    expect(brief.dataHealth).toBe("insufficient");
  });

  it("keeps a citation's unmeasured freshness and staleness as null, not zero or false", () => {
    const value = marketBriefFixture();
    const citation = value.citations[0] as Record<string, unknown>;
    citation.freshnessSeconds = null;
    citation.stale = null;

    const brief = decodeMarketBriefEnvelope(value, { now });

    expect(brief.citations[0]?.freshnessSeconds).toBeNull();
    expect(brief.citations[0]?.stale).toBeNull();
  });

  it("decodes an unavailable brief as a typed unavailable carrying the server's reason", () => {
    const value = marketBriefFixture();
    value.status = "unavailable";
    value.reason =
      "本次未能读取任何情报源：sec-current-8-k（HTTP 503）、fred-releases（unreachable）";
    value.dataHealth = null;
    value.sentiment = null;
    value.citations = [];
    value.sourceGaps = [
      "sec-current-8-k（HTTP 503）",
      "fred-releases（unreachable）",
    ];
    value.driverCoverage = value.driverCoverage.map((item) => ({
      ...item,
      available: false,
      conclusion: null,
      actionScore: null,
      missingReason: "本次没有可读取的情报源，无法给出该驱动的结论。",
    }));

    const brief = decodeMarketBriefEnvelope(value, { now });

    expect(brief.status).toBe("unavailable");
    expect(brief.reason).toContain("sec-current-8-k");
    expect(brief.reason).toContain("fred-releases");
    expect(brief.dataHealth).toBeNull();
    expect(brief.sentiment).toBeNull();
    expect(brief.citations).toEqual([]);
    expect(brief.driverCoverage).toHaveLength(9);
    expect(brief.driverCoverage.every((item) => !item.available)).toBe(true);
  });

  it("rejects a non-https citation rather than serving it", () => {
    const value = marketBriefFixture();
    (value.citations[0] as Record<string, unknown>).url =
      "http://reuters.example/a";

    expect(() => decodeMarketBriefEnvelope(value, { now })).toThrow(/https/i);
  });

  it("rejects a payload carrying anything that could place an order", () => {
    const value = marketBriefFixture() as Record<string, unknown>;
    value.submitOrder = { quantity: 100 };

    expect(() => decodeMarketBriefEnvelope(value, { now })).toThrow(/order/i);
  });

  it("rejects a credential field embedded anywhere inside the payload", () => {
    const value = marketBriefFixture() as Record<string, unknown>;
    const driverCoverage = value.driverCoverage as Record<string, unknown>[];
    driverCoverage[0]!.brokerToken = "sk-live-should-never-ride-along";

    expect(() => decodeMarketBriefEnvelope(value, { now })).toThrow(/order/i);
  });

  it("tolerates the same clock skew a decision does", () => {
    const value = marketBriefFixture();
    value.decisionCutoff = new Date(now.getTime() + 3_000).toISOString();

    const brief = decodeMarketBriefEnvelope(value, { now });

    expect(brief.decisionCutoff).toBe(value.decisionCutoff);
  });

  it("still refuses a cutoff that is meaningfully in the future", () => {
    const value = marketBriefFixture();
    value.decisionCutoff = new Date(now.getTime() + 20 * 60_000).toISOString();

    expect(() => decodeMarketBriefEnvelope(value, { now })).toThrow(/future/);
  });

  it.each([
    [
      "an unsupported schema version",
      (value: Record<string, unknown>) => {
        value.schemaVersion = "2";
      },
    ],
    [
      "a status this app does not know",
      (value: Record<string, unknown>) => {
        value.status = "pending";
      },
    ],
    [
      "an unavailable brief that names no reason",
      (value: Record<string, unknown>) => {
        value.status = "unavailable";
        value.dataHealth = null;
        value.sentiment = null;
        value.citations = [];
      },
    ],
    [
      "an available brief carrying a reason it should not have",
      (value: Record<string, unknown>) => {
        value.reason = "should not be present when available";
      },
    ],
    [
      "an unavailable brief that still carries a data health reading",
      (value: Record<string, unknown>) => {
        value.status = "unavailable";
        value.reason = "本次未能读取任何情报源：sec-current-8-k（HTTP 503）";
        value.sentiment = null;
        value.citations = [];
      },
    ],
    [
      "an unavailable brief that still carries a sentiment reading",
      (value: Record<string, unknown>) => {
        value.status = "unavailable";
        value.reason = "本次未能读取任何情报源：sec-current-8-k（HTTP 503）";
        value.dataHealth = null;
        value.citations = [];
      },
    ],
    [
      "a driver coverage list missing one of the nine designed categories",
      (value: Record<string, unknown>) => {
        value.driverCoverage = (
          value.driverCoverage as Record<string, unknown>[]
        ).slice(0, 8);
      },
    ],
    [
      "an available driver category with no conclusion",
      (value: Record<string, unknown>) => {
        (value.driverCoverage as Record<string, unknown>[])[0]!.conclusion =
          null;
      },
    ],
    [
      "an available driver category with no action score",
      (value: Record<string, unknown>) => {
        (value.driverCoverage as Record<string, unknown>[])[0]!.actionScore =
          null;
      },
    ],
    [
      "an unavailable driver category that names no missing reason",
      (value: Record<string, unknown>) => {
        (value.driverCoverage as Record<string, unknown>[])[1]!.missingReason =
          null;
      },
    ],
    [
      "an unsupported market session",
      (value: Record<string, unknown>) => {
        value.marketSession = "midnight";
      },
    ],
    [
      "an unsupported data health value",
      (value: Record<string, unknown>) => {
        value.dataHealth = "great";
      },
    ],
    [
      "a driver category this app does not know",
      (value: Record<string, unknown>) => {
        (value.driverCoverage as Record<string, unknown>[])[0]!.category =
          "vibes";
      },
    ],
    [
      "a driver coverage list with a duplicate category standing in for a missing one",
      (value: Record<string, unknown>) => {
        // Nine entries by count alone: "breadth" is silently dropped and
        // "news-sentiment" appears twice instead. A decoder that only checks
        // .length === 9 would accept this and quietly lose a whole category.
        const driverCoverage = value.driverCoverage as Record<string, unknown>[];
        driverCoverage[1] = { ...driverCoverage[0] };
      },
    ],
    [
      "an unavailable brief whose driver coverage still claims an available category",
      (value: Record<string, unknown>) => {
        // Mirrors decodeDecisionEnvelope's "an unavailable decision must not
        // carry a score" rule at the brief level: status: "unavailable" must
        // hold for every driverCoverage entry too, not just the top-level
        // dataHealth/sentiment/citations fields.
        value.status = "unavailable";
        value.reason = "本次未能读取任何情报源：sec-current-8-k（HTTP 503）";
        value.dataHealth = null;
        value.sentiment = null;
        value.citations = [];
        // driverCoverage left as the fixture's default, where news-sentiment
        // is available: true.
      },
    ],
  ])("rejects %s", (_label, mutate) => {
    const value = marketBriefFixture() as Record<string, unknown>;
    mutate(value);

    expect(() => decodeMarketBriefEnvelope(value, { now })).toThrow();
  });

  it("decodes the news-sentiment driver entry as unavailable, never a measured-looking zero, when nothing was measured this round", () => {
    // Pins the shape landed in 601b131 on services/analysis_api: the
    // unmeasured case flips news-sentiment's own driverCoverage entry to
    // available: false with a dedicated missingReason, instead of
    // available: true with a 中性/0.0 conclusion that looks measured to any
    // consumer reading driverCoverage alone.
    const value = marketBriefFixture();
    (value.sentiment as Record<string, unknown>).uncertainty = ["情绪未测量"];
    (value.sentiment as Record<string, unknown>).actionScore = 0.0;
    value.dataHealth = "insufficient";
    value.driverCoverage = value.driverCoverage.map((item) =>
      item.category === "news-sentiment"
        ? {
            category: "news-sentiment",
            available: false,
            conclusion: null,
            actionScore: null,
            missingReason: "情绪未测量（该时段无可读事件）",
          }
        : item,
    );

    const brief = decodeMarketBriefEnvelope(value, { now });

    const newsSentiment = brief.driverCoverage.find(
      (item) => item.category === "news-sentiment",
    );
    expect(newsSentiment).toMatchObject({
      available: false,
      conclusion: null,
      actionScore: null,
      missingReason: "情绪未测量（该时段无可读事件）",
    });
  });

  it("decodes notes from an available brief", () => {
    const value = marketBriefFixture() as Record<string, unknown>;
    (value.notes as string[]) = [
      "有 1 条证据在决策截点之后才可用，未纳入本次结论：future-1",
    ];

    const brief = decodeMarketBriefEnvelope(value, { now });

    expect(brief.notes).toEqual([
      "有 1 条证据在决策截点之后才可用，未纳入本次结论：future-1",
    ]);
  });

  it("decodes empty notes array from an available brief", () => {
    const value = marketBriefFixture();

    const brief = decodeMarketBriefEnvelope(value, { now });

    expect(brief.notes).toEqual([]);
  });

  it("decodes empty notes array from an unavailable brief", () => {
    const value = marketBriefFixture();
    value.status = "unavailable";
    value.reason =
      "本次未能读取任何情报源：sec-current-8-k（HTTP 503）、fred-releases（unreachable）";
    value.dataHealth = null;
    value.sentiment = null;
    value.citations = [];
    value.sourceGaps = [
      "sec-current-8-k（HTTP 503）",
      "fred-releases（unreachable）",
    ];
    value.driverCoverage = value.driverCoverage.map((item) => ({
      ...item,
      available: false,
      conclusion: null,
      actionScore: null,
      missingReason: "本次没有可读取的情报源，无法给出该驱动的结论。",
    }));

    const brief = decodeMarketBriefEnvelope(value, { now });

    expect(brief.notes).toEqual([]);
  });

  it("rejects a brief with missing notes field", () => {
    const value = marketBriefFixture() as Record<string, unknown>;
    delete value.notes;

    expect(() => decodeMarketBriefEnvelope(value, { now })).toThrow(/notes/i);
  });

  it("rejects a brief with non-array notes", () => {
    const value = marketBriefFixture() as Record<string, unknown>;
    value.notes = "not an array";

    expect(() => decodeMarketBriefEnvelope(value, { now })).toThrow(/notes.*array/i);
  });

  it("rejects a brief with empty-string note entries", () => {
    const value = marketBriefFixture() as Record<string, unknown>;
    (value.notes as unknown[]) = ["有效备注", ""];

    expect(() => decodeMarketBriefEnvelope(value, { now })).toThrow(/note.*non-empty/i);
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

  it("wires the full council mode to the server's boolean adviser flag, not the literal word", async () => {
    const fetchImpl = jest.fn(async () =>
      jsonResponse(decisionFixture()),
    ) as unknown as typeof fetch;
    const client = createAnalysisClient({
      baseUrl: "http://127.0.0.1:8788",
      fetchImpl,
      now: () => now,
    });

    await client.getDecision("nvda", "short", undefined, { adviser: "full" });

    // `_flag` on the server only ever parses "1/true/yes/0/false/no/news";
    // the literal string "full" is not in that vocabulary and would 400. The
    // council is reached the same way `adviser=true` already is: `_flag`
    // reads it as the boolean True and `_adviser_mode(True)` resolves to the
    // "full" mode server-side.
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://127.0.0.1:8788/decision?symbol=NVDA&horizon=short&adviser=true",
      expect.any(Object),
    );
  });

  it("gives the council call the server's 300-second ceiling instead of the normal deadline", async () => {
    jest.useFakeTimers();
    try {
      let fetchSignal: AbortSignal | undefined;
      const fetchImpl = jest.fn(
        async (_url: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((resolve, reject) => {
            fetchSignal = init?.signal as AbortSignal;
            const answer = setTimeout(
              () => resolve(jsonResponse(decisionFixture())),
              290_000,
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

      const request = client.getDecision("NVDA", "short", undefined, {
        adviser: "full",
      });
      // The plain decision path's own 45-second deadline must not fire here:
      // the council is still legitimately working at that mark.
      await jest.advanceTimersByTimeAsync(45_000);
      expect(fetchSignal?.aborted).toBe(false);

      await jest.advanceTimersByTimeAsync(245_000);
      expect(fetchSignal?.aborted).toBe(false);
      await expect(request).resolves.toMatchObject({ symbol: "NVDA" });
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      jest.useRealTimers();
    }
  });

  it("still abandons a plain decision at the client's normal deadline, not the council's", async () => {
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

describe("market brief client transport", () => {
  it("requests the market brief over a plain GET with no query parameters", async () => {
    const fetchImpl = jest.fn(async () =>
      jsonResponse(marketBriefFixture()),
    ) as unknown as typeof fetch;
    const client = createAnalysisClient({
      baseUrl: "http://192.168.1.10:8788/",
      authorizationToken: "0123456789abcdef0123456789abcdef",
      fetchImpl,
      now: () => now,
    });

    const brief = await client.getMarketBrief!();

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://192.168.1.10:8788/market-brief",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer 0123456789abcdef0123456789abcdef",
        }),
      }),
    );
    expect(brief).toMatchObject({ status: "available", marketSession: "regular" });
  });

  it("returns an explicitly unavailable brief rather than inventing one", async () => {
    const value = marketBriefFixture();
    value.status = "unavailable";
    value.reason = "本次未能读取任何情报源：sec-current-8-k（HTTP 503）";
    value.dataHealth = null;
    value.sentiment = null;
    value.citations = [];
    value.driverCoverage = value.driverCoverage.map((item) => ({
      ...item,
      available: false,
      conclusion: null,
      actionScore: null,
      missingReason: "本次没有可读取的情报源，无法给出该驱动的结论。",
    }));
    const client = createAnalysisClient({
      baseUrl: "http://127.0.0.1:8788",
      fetchImpl: jest.fn(async () => jsonResponse(value)) as unknown as typeof fetch,
      now: () => now,
    });

    const brief = await client.getMarketBrief!();

    expect(brief.status).toBe("unavailable");
    expect(brief.reason).toContain("sec-current-8-k");
  });

  it("classifies a market brief failure the same way a decision failure is classified", async () => {
    const client = createAnalysisClient({
      baseUrl: "http://127.0.0.1:8788",
      fetchImpl: jest.fn(async () =>
        jsonResponse({ error: { code: "AUTH_REQUIRED" } }, 401),
      ) as unknown as typeof fetch,
      now: () => now,
    });

    await expect(client.getMarketBrief!()).rejects.toMatchObject({
      name: "AnalysisRequestError",
      kind: "auth-required",
    });
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
      client.getMarketBrief!(caller.signal),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchImpl).not.toHaveBeenCalled();
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
