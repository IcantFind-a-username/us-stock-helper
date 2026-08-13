import { describe, expect, it } from "@jest/globals";

import { decodeNewsBriefingEnvelope, NewsValidationError } from "../newsGateway";

import { newsBriefingFixture } from "./newsBriefing.fixture";

const now = new Date("2026-08-13T13:30:05.000Z");

function decode(mutate: (value: ReturnType<typeof newsBriefingFixture>) => void = () => {}) {
  const value = newsBriefingFixture();
  mutate(value);
  return decodeNewsBriefingEnvelope(value, { now });
}

function connectedFeed(briefing: ReturnType<typeof decode>) {
  if (briefing.feed.status !== "connected") {
    throw new Error(`expected a connected feed, got ${briefing.feed.status}`);
  }
  return briefing.feed;
}

function availableInterpretation(briefing: ReturnType<typeof decode>) {
  if (briefing.interpretation.status !== "available") {
    throw new Error("expected an available interpretation");
  }
  return briefing.interpretation;
}

describe("news briefing decoding", () => {
  it("decodes a connected feed with its verifiable stories", () => {
    const briefing = decode();

    expect(briefing.symbol).toBe("NVDA");
    expect(briefing.asOf).toBe("2026-08-13T13:30:00.000Z");
    const feed = connectedFeed(briefing);
    expect(feed.stories.map((story) => story.id)).toEqual([
      "story-guidance",
      "story-supply",
      "story-partial",
    ]);
  });

  it("drops a story no reader could open and counts what it dropped", () => {
    const feed = connectedFeed(decode());

    // An unverifiable claim that still occupies a row reads as reporting.
    expect(feed.stories.some((story) => story.id === "story-unlinked")).toBe(false);
    expect(feed.hiddenStoryCount).toBe(1);
  });

  it("counts only the independent publishers a reader can open", () => {
    const feed = connectedFeed(decode());
    const guidance = feed.stories.find((story) => story.id === "story-guidance");
    const partial = feed.stories.find((story) => story.id === "story-partial");

    expect(guidance?.sourceCount).toBe(2);
    expect(guidance?.omittedSourceCount).toBe(0);
    expect(partial?.sourceCount).toBe(1);
    expect(partial?.omittedSourceCount).toBe(1);
  });

  it("counts one publisher once no matter how often it republishes", () => {
    const feed = connectedFeed(
      decode((value) => {
        value.feed.stories[0]!.reports.push({
          publisherId: "reuters",
          publisher: "路透社",
          url: "https://reuters.example/nvda-guidance-update",
          reliability: 0.92,
          availableAt: "2026-08-13T13:28:30.000Z",
          receivedAt: "2026-08-13T13:28:40.000Z",
        });
      }),
    );

    expect(
      feed.stories.find((story) => story.id === "story-guidance")?.sourceCount,
    ).toBe(2);
  });

  it("times a story by the earliest copy a reader can actually open", () => {
    const feed = connectedFeed(decode());
    const partial = feed.stories.find((story) => story.id === "story-partial");

    // The unlinked 13:19 report is one minute earlier, but a timestamp the
    // reader cannot trace back to anything is not a timestamp worth showing.
    expect(partial?.availableAt).toBe("2026-08-13T13:20:00.000Z");
    expect(partial?.receivedAt).toBe("2026-08-13T13:20:10.000Z");
  });

  it("withholds a conclusion whose evidence cannot be opened", () => {
    const interpretation = availableInterpretation(decode());

    expect(interpretation.claims.map((claim) => claim.id)).toEqual([
      "claim-guidance",
      "claim-capacity",
    ]);
    expect(interpretation.withheldClaimCount).toBe(1);
  });

  it("withholds a conclusion when any one of its citations is unverifiable", () => {
    const interpretation = availableInterpretation(
      decode((value) => {
        value.interpretation.claims[1]!.evidenceIds = [
          "story-supply",
          "story-unlinked",
        ];
      }),
    );

    expect(interpretation.claims.map((claim) => claim.id)).toEqual([
      "claim-guidance",
    ]);
    expect(interpretation.withheldClaimCount).toBe(2);
  });

  it("keeps a disconnected feed disconnected instead of inventing stories", () => {
    const briefing = decode((value) => {
      value.feed.status = "not-connected";
      value.feed.reason = "尚未配置新闻源凭据";
      value.feed.stories = [];
      value.interpretation.claims = [];
    });

    expect(briefing.feed).toEqual({
      status: "not-connected",
      reason: "尚未配置新闻源凭据",
    });
  });

  it("refuses an interpretation that outlives the feed it was built on", () => {
    // Without the evidence in the same payload there is nothing for the reader
    // to check the conclusion against, so it cannot be a conclusion any more.
    expect(() =>
      decode((value) => {
        value.feed.status = "not-connected";
        value.feed.reason = "尚未配置新闻源凭据";
        value.feed.stories = [];
      }),
    ).toThrow(/story-guidance/);
  });

  it("keeps an unavailable interpretation apart from an empty one", () => {
    const briefing = decode((value) => {
      value.interpretation.status = "unavailable";
      value.interpretation.reason = "解读模型未响应";
      value.interpretation.claims = [];
    });

    expect(briefing.interpretation).toEqual({
      status: "unavailable",
      reason: "解读模型未响应",
    });
  });

  it("accepts a connected feed that simply has nothing to report", () => {
    const feed = connectedFeed(
      decode((value) => {
        value.feed.stories = [];
        value.interpretation.claims = [];
      }),
    );

    expect(feed.stories).toEqual([]);
    expect(feed.hiddenStoryCount).toBe(0);
  });
});

describe("news briefing rejection", () => {
  it("rejects a payload that is not an object", () => {
    expect(() => decodeNewsBriefingEnvelope("[]", { now })).toThrow(
      NewsValidationError,
    );
  });

  it("rejects an unsupported schema version", () => {
    expect(() => decode((value) => void (value.schemaVersion = "2"))).toThrow(
      /schemaVersion/,
    );
  });

  it("rejects a snapshot taken after the reader's clock", () => {
    expect(() =>
      decode((value) => void (value.asOf = "2026-08-13T13:31:00.000Z")),
    ).toThrow(/asOf/);
  });

  it("rejects a source link that is not https", () => {
    expect(() =>
      decode((value) => {
        value.feed.stories[0]!.reports[0]!.url = "http://reuters.example/a";
      }),
    ).toThrow(/https/);
  });

  it("rejects a report received before it was published", () => {
    expect(() =>
      decode((value) => {
        value.feed.stories[0]!.reports[0]!.receivedAt =
          "2026-08-13T13:26:00.000Z";
      }),
    ).toThrow(/receivedAt/);
  });

  it("rejects a report received after the snapshot cutoff", () => {
    expect(() =>
      decode((value) => {
        value.feed.stories[0]!.reports[0]!.receivedAt =
          "2026-08-13T13:30:01.000Z";
      }),
    ).toThrow(/cutoff/);
  });

  it("rejects a timestamp without a timezone", () => {
    expect(() =>
      decode((value) => {
        value.feed.stories[0]!.reports[0]!.availableAt = "2026-08-13 13:27:00";
      }),
    ).toThrow(/ISO timestamp/);
  });

  it("rejects a reliability outside the unit interval", () => {
    expect(() =>
      decode((value) => {
        value.feed.stories[0]!.reports[0]!.reliability = 1.2;
      }),
    ).toThrow(/reliability/);
  });

  it("rejects a story that carries no report at all", () => {
    expect(() =>
      decode((value) => {
        value.feed.stories[1]!.reports = [];
      }),
    ).toThrow(/report/);
  });

  it("rejects two stories sharing one id", () => {
    expect(() =>
      decode((value) => {
        value.feed.stories[1]!.id = "story-guidance";
      }),
    ).toThrow(/duplicate/);
  });

  it("rejects an unsupported claim status", () => {
    expect(() =>
      decode((value) => {
        value.feed.stories[0]!.claimStatus = "confirmed-ish";
      }),
    ).toThrow(/claimStatus/);
  });

  it("rejects a disconnected feed that still carries stories", () => {
    expect(() =>
      decode((value) => {
        value.feed.status = "not-connected";
        value.feed.reason = "尚未配置新闻源凭据";
      }),
    ).toThrow(/not-connected/);
  });

  it("rejects a disconnected feed with no stated reason", () => {
    expect(() =>
      decode((value) => {
        value.feed.status = "not-connected";
        value.feed.stories = [];
        value.feed.reason = null;
      }),
    ).toThrow(/reason/);
  });

  it("rejects an unavailable interpretation with no stated reason", () => {
    expect(() =>
      decode((value) => {
        value.interpretation.status = "unavailable";
        value.interpretation.claims = [];
      }),
    ).toThrow(/reason/);
  });

  it("rejects an unavailable interpretation that still carries conclusions", () => {
    expect(() =>
      decode((value) => {
        value.interpretation.status = "unavailable";
        value.interpretation.reason = "解读模型未响应";
      }),
    ).toThrow(/unavailable/);
  });

  it("rejects a conclusion that cites nothing", () => {
    expect(() =>
      decode((value) => {
        value.interpretation.claims[0]!.evidenceIds = [];
      }),
    ).toThrow(/evidenceIds/);
  });

  it("rejects a conclusion citing evidence the payload never carried", () => {
    expect(() =>
      decode((value) => {
        value.interpretation.claims[0]!.evidenceIds = ["story-missing"];
      }),
    ).toThrow(/story-missing/);
  });

  it("rejects an evidence window that expires before it opens", () => {
    expect(() =>
      decode((value) => {
        value.interpretation.evidenceValidUntil = "2026-08-13T13:28:00.000Z";
      }),
    ).toThrow(/evidenceValidUntil/);
  });

  it("rejects an interpretation generated after the snapshot cutoff", () => {
    expect(() =>
      decode((value) => {
        value.interpretation.generatedAt = "2026-08-13T13:30:30.000Z";
      }),
    ).toThrow(/generatedAt/);
  });
});
