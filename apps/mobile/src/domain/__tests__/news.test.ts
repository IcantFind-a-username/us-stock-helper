import { describe, expect, it } from "@jest/globals";

import {
  evidenceMarker,
  formatAbsoluteUtc,
  formatRelativeTime,
  isEvidenceExpired,
  orderStoriesByRecency,
  type NewsInterpretationSection,
  type NewsStory,
} from "../news";

function story(
  id: string,
  availableAt: string,
  receivedAt: string = availableAt,
): NewsStory {
  return {
    id,
    headline: `headline ${id}`,
    claimStatus: "reported",
    availableAt,
    receivedAt,
    sources: [
      {
        publisherId: id,
        publisher: id,
        url: `https://example.com/${id}`,
        reliability: 0.5,
        availableAt,
        receivedAt,
      },
    ],
    sourceCount: 1,
    omittedSourceCount: 0,
  };
}

describe("news ordering", () => {
  it("puts the most recently published story first", () => {
    const ordered = orderStoriesByRecency([
      story("old", "2026-08-13T12:00:00.000Z"),
      story("new", "2026-08-13T13:27:00.000Z"),
      story("mid", "2026-08-13T13:10:00.000Z"),
    ]);

    expect(ordered.map((item) => item.id)).toEqual(["new", "mid", "old"]);
  });

  it("breaks a publication tie with the later receipt", () => {
    const ordered = orderStoriesByRecency([
      story("earlier-receipt", "2026-08-13T13:00:00.000Z", "2026-08-13T13:00:10.000Z"),
      story("later-receipt", "2026-08-13T13:00:00.000Z", "2026-08-13T13:04:00.000Z"),
    ]);

    expect(ordered.map((item) => item.id)).toEqual([
      "later-receipt",
      "earlier-receipt",
    ]);
  });

  it("orders identical timestamps deterministically by id", () => {
    const timestamp = "2026-08-13T13:00:00.000Z";
    const ordered = orderStoriesByRecency([
      story("b", timestamp),
      story("a", timestamp),
    ]);

    expect(ordered.map((item) => item.id)).toEqual(["a", "b"]);
  });

  it("does not mutate the caller's list", () => {
    const stories = [
      story("old", "2026-08-13T12:00:00.000Z"),
      story("new", "2026-08-13T13:27:00.000Z"),
    ];

    orderStoriesByRecency(stories);

    expect(stories.map((item) => item.id)).toEqual(["old", "new"]);
  });
});

describe("relative time", () => {
  const now = new Date("2026-08-13T13:30:00.000Z");

  it("reads the elapsed time from the publication moment", () => {
    expect(formatRelativeTime("2026-08-13T13:29:31.000Z", now)).toBe("刚刚");
    expect(formatRelativeTime("2026-08-13T13:27:00.000Z", now)).toBe("3 分钟前");
    expect(formatRelativeTime("2026-08-13T11:30:00.000Z", now)).toBe("2 小时前");
    expect(formatRelativeTime("2026-08-10T13:30:00.000Z", now)).toBe("3 天前");
  });

  it("rounds down so a story never looks older than it is", () => {
    expect(formatRelativeTime("2026-08-13T13:26:01.000Z", now)).toBe("3 分钟前");
  });

  it("refuses to invent a relative time it cannot compute", () => {
    // A publication moment after the reader's clock is a contradiction, not a
    // "just now": pretending otherwise hides a skewed clock or a bad feed.
    expect(formatRelativeTime("2026-08-13T13:31:00.000Z", now)).toBeNull();
    expect(formatRelativeTime("not-a-timestamp", now)).toBeNull();
  });
});

describe("absolute time", () => {
  it("states the timestamp in UTC so two readers see one moment", () => {
    expect(formatAbsoluteUtc("2026-08-13T13:27:00.000Z")).toBe(
      "2026-08-13 13:27:00 UTC",
    );
    expect(formatAbsoluteUtc("2026-08-13T13:27:00+02:00")).toBe(
      "2026-08-13 11:27:00 UTC",
    );
  });

  it("returns null for a timestamp it cannot parse", () => {
    expect(formatAbsoluteUtc("not-a-timestamp")).toBeNull();
  });
});

describe("evidence expiry", () => {
  const live: NewsInterpretationSection = {
    status: "available",
    model: "analysis-llm-v3",
    generatedAt: "2026-08-13T13:29:00.000Z",
    evidenceValidUntil: "2026-08-13T13:45:00.000Z",
    claims: [],
    withheldClaimCount: 0,
  };

  it("holds while the evidence window is open", () => {
    expect(isEvidenceExpired(live, new Date("2026-08-13T13:45:00.000Z"))).toBe(
      false,
    );
  });

  it("expires once the window has closed", () => {
    expect(isEvidenceExpired(live, new Date("2026-08-13T13:45:01.000Z"))).toBe(
      true,
    );
  });

  it("treats an unusable window as expired rather than as valid", () => {
    // Vouching for a conclusion whose validity cannot be read is the one
    // failure mode worth avoiding here.
    expect(
      isEvidenceExpired(
        { ...live, evidenceValidUntil: "not-a-timestamp" },
        new Date("2026-08-13T13:30:00.000Z"),
      ),
    ).toBe(true);
  });

  it("says nothing about an interpretation that never arrived", () => {
    expect(
      isEvidenceExpired(
        { status: "unavailable", reason: "解读模型未响应" },
        new Date("2026-08-13T13:30:00.000Z"),
      ),
    ).toBe(false);
  });
});

describe("evidence markers", () => {
  it("numbers evidence so a conclusion can point at it", () => {
    expect(evidenceMarker(0)).toBe("①");
    expect(evidenceMarker(19)).toBe("⑳");
  });

  it("keeps numbering past the circled glyphs", () => {
    expect(evidenceMarker(20)).toBe("[21]");
  });
});
