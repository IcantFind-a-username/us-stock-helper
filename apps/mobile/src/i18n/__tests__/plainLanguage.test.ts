import { describe, expect, it } from "@jest/globals";

import type { CompletedTdSetup, MagicNineSnapshot, MarketBriefDriverCoverage } from "@/domain/models";

import {
  BANNED_VERBS,
  PLAIN_LANGUAGE_VERSION,
  classifyBreadthDriver,
  classifyMagicNineLastCompleted,
  classifyMagicNineProgress,
  classifySectorDriver,
  magicNineLastCompletedReading,
  magicNineProgressReading,
  reading,
  readBreadthDriver,
  readSectorDriver,
} from "../plainLanguage";

const BASE_METADATA = {
  source: "analysis-core" as const,
  asOf: "2026-08-15T16:00:00.000Z",
  availableAt: "2026-08-15T16:00:00.000Z",
  methodVersion: "td-setup-close-4-v2",
};

function magicNine(overrides: Partial<MagicNineSnapshot>): MagicNineSnapshot {
  return {
    ...BASE_METADATA,
    direction: null,
    count: 0,
    series: null,
    completed: false,
    perfected: null,
    confirmedAtIndex: null,
    lastCompleted: null,
    qualityStatus: "live",
    ...overrides,
  };
}

function driverEntry(
  overrides: Partial<MarketBriefDriverCoverage>,
): MarketBriefDriverCoverage {
  return {
    category: "breadth",
    available: true,
    conclusion: "自选广度（5 只）· 多数走强 · 60% 收于50日均线上方",
    actionScore: 0.2,
    missingReason: null,
    ...overrides,
  };
}

describe("plainLanguage version and safety guard", () => {
  it("stamps the same version as the server vocabulary", () => {
    expect(PLAIN_LANGUAGE_VERSION).toBe("plain-language-v1");
  });

  it("lists the five banned verbs", () => {
    expect(new Set(BANNED_VERBS)).toEqual(
      new Set(["买入", "卖出", "加仓", "抄底", "梭哈"]),
    );
  });

  it("throws when constructing a reading with a banned verb in the headline", () => {
    for (const verb of BANNED_VERBS) {
      expect(() => reading(`现在应该${verb}。`, "解释。")).toThrow();
    }
  });

  it("throws when constructing a reading with a banned verb in the explanation", () => {
    expect(() => reading("标题。", "展开解释里建议梭哈。")).toThrow();
  });
});

describe("breadth driver readings", () => {
  it("classifies strong/weak/mixed by the same thresholds as the server", () => {
    expect(
      classifyBreadthDriver(driverEntry({ actionScore: 0.2 })),
    ).toBe("breadth-strong");
    expect(
      classifyBreadthDriver(driverEntry({ actionScore: 0.1 })),
    ).toBe("breadth-strong");
    expect(
      classifyBreadthDriver(driverEntry({ actionScore: 0.099999 })),
    ).toBe("breadth-mixed");
    expect(
      classifyBreadthDriver(driverEntry({ actionScore: -0.1 })),
    ).toBe("breadth-weak");
    expect(
      classifyBreadthDriver(driverEntry({ actionScore: 0 })),
    ).toBe("breadth-mixed");
  });

  it("classifies an unavailable entry", () => {
    expect(
      classifyBreadthDriver(
        driverEntry({ available: false, conclusion: null, actionScore: null, missingReason: "x" }),
      ),
    ).toBe("breadth-unavailable");
  });

  it("returns a full PlainReading + numbers layer for every state", () => {
    for (const entry of [
      driverEntry({ actionScore: 0.2 }),
      driverEntry({ actionScore: -0.2 }),
      driverEntry({ actionScore: 0 }),
      driverEntry({ available: false, conclusion: null, actionScore: null, missingReason: "x" }),
    ]) {
      const result = readBreadthDriver(entry);
      expect(result.headline.length).toBeGreaterThan(0);
      expect(result.explanation.length).toBeGreaterThan(0);
      expect(result.numbers.value.length).toBeGreaterThan(0);
      expect(result.numbers.sampleSize.length).toBeGreaterThan(0);
      expect(result.numbers.invalidation.length).toBeGreaterThan(0);
    }
  });
});

describe("sector driver readings", () => {
  it("classifies leading/lagging/unavailable", () => {
    expect(
      classifySectorDriver(
        driverEntry({ category: "sector", actionScore: 0.05 }),
      ),
    ).toBe("sector-rs-leading");
    expect(
      classifySectorDriver(
        driverEntry({ category: "sector", actionScore: -0.01 }),
      ),
    ).toBe("sector-rs-lagging");
    expect(
      classifySectorDriver(
        driverEntry({ category: "sector", actionScore: 0 }),
      ),
    ).toBe("sector-rs-lagging");
    expect(
      classifySectorDriver(
        driverEntry({
          category: "sector",
          available: false,
          conclusion: null,
          actionScore: null,
          missingReason: "x",
        }),
      ),
    ).toBe("sector-rs-unavailable");
  });

  it("returns a full reading for every state", () => {
    for (const entry of [
      driverEntry({ category: "sector", actionScore: 0.05 }),
      driverEntry({ category: "sector", actionScore: -0.01 }),
      driverEntry({
        category: "sector",
        available: false,
        conclusion: null,
        actionScore: null,
        missingReason: "x",
      }),
    ]) {
      const result = readSectorDriver(entry);
      expect(result.headline.length).toBeGreaterThan(0);
      expect(result.explanation.length).toBeGreaterThan(0);
    }
  });
});

describe("magic nine progress readings", () => {
  it("classifies unavailable and no-active-run", () => {
    expect(
      classifyMagicNineProgress(magicNine({ qualityStatus: "unavailable" })),
    ).toBe("magic-nine-unavailable");
    expect(
      classifyMagicNineProgress(magicNine({ direction: null, count: 0 })),
    ).toBe("magic-nine-no-active-run");
  });

  it("classifies every direction and in-progress count bucket", () => {
    const bucketByCount: Record<number, string> = {
      1: "early", 2: "early", 3: "early",
      4: "mid", 5: "mid", 6: "mid",
      7: "late", 8: "late",
    };
    for (const direction of ["bullish", "bearish"] as const) {
      for (const [countText, bucket] of Object.entries(bucketByCount)) {
        const count = Number(countText);
        const snapshot = magicNine({ direction, count, completed: false });
        expect(classifyMagicNineProgress(snapshot)).toBe(
          `magic-nine-${direction}-${bucket}`,
        );
        const result = magicNineProgressReading(snapshot);
        expect(result.headline).toContain(String(count));
      }
    }
  });

  it("matches Franz's example: bearish count 2", () => {
    const snapshot = magicNine({ direction: "bearish", count: 2, completed: false });
    const result = magicNineProgressReading(snapshot);
    expect(result.headline).toContain("2");
    expect(result.headline).toContain("9");
    expect(result.headline).toContain("下跌");
  });

  it("classifies every direction and perfection state at completion", () => {
    for (const direction of ["bullish", "bearish"] as const) {
      for (const perfected of [true, false, null] as const) {
        const suffix =
          perfected === true ? "perfected" : perfected === false ? "unperfected" : "unknown";
        const snapshot = magicNine({
          direction,
          count: 9,
          completed: true,
          perfected,
        });
        expect(classifyMagicNineProgress(snapshot)).toBe(
          `magic-nine-${direction}-complete-${suffix}`,
        );
        const result = magicNineProgressReading(snapshot);
        expect(result.headline.length).toBeGreaterThan(0);
      }
    }
  });

  it("throws on an unrecognized direction rather than falling back", () => {
    expect(() =>
      classifyMagicNineProgress(magicNine({ direction: "sideways", count: 3 })),
    ).toThrow();
  });
});

describe("magic nine last-completed readings", () => {
  function lastCompleted(overrides: Partial<CompletedTdSetup>): CompletedTdSetup {
    return {
      direction: "bullish",
      confirmedAtIndex: 10,
      perfected: true,
      barsSince: 3,
      ...overrides,
    };
  }

  it("classifies null and every direction x perfection combination", () => {
    // CompletedTdSetup.perfected is a plain boolean on the wire (unlike the
    // in-progress snapshot's nullable `perfected`, a completed run's 完美
    // comparison always ran) -- so only true/false are reachable here.
    expect(classifyMagicNineLastCompleted(null)).toBe(
      "magic-nine-last-completed-none",
    );
    for (const direction of ["bullish", "bearish"] as const) {
      for (const perfected of [true, false] as const) {
        const suffix = perfected ? "perfected" : "unperfected";
        expect(
          classifyMagicNineLastCompleted(lastCompleted({ direction, perfected })),
        ).toBe(`magic-nine-last-completed-${direction}-${suffix}`);
        const result = magicNineLastCompletedReading(
          lastCompleted({ direction, perfected }),
        );
        expect(result.headline.length).toBeGreaterThan(0);
      }
    }
  });
});
