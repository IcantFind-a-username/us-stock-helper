import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "@jest/globals";

import {
  chartStatusLabel,
  factorLabel,
  gateLabel,
  intervalLabel,
  planActionLabel,
  scenarioLabel,
  scoreDirectionLabel,
  serviceTextLabel,
  snapshotSourceLabel,
} from "../serverVocabulary";

/**
 * Anything the reader is shown must be readable to a Chinese reader.
 *
 * A run of three or more lowercase ASCII letters is the signature of the two
 * things this layer exists to remove: an English sentence, and a raw server
 * identifier such as `stale_data`. Short tokens the reader does understand —
 * "K 线", "MA5", "v1", "70%" — survive the check on purpose.
 */
function expectReadableChinese(label: string) {
  // Emptiness is checked here rather than at each call site: a blank
  // translation satisfies "contains no latin letters" while erasing the term
  // from a list the reader is counting on being complete, and a guard that
  // only some callers remember to apply is the one that gets forgotten.
  expect(label.trim().length).toBeGreaterThan(0);
  expect(label).not.toMatch(/[a-z]{3,}/);
}

/** Every factor the scoring service can report as unavailable. */
const FACTORS = [
  "technical_trend",
  "momentum",
  "pattern",
  "market_sentiment",
  "macro",
  "geopolitics",
  "institutional_flow",
  "fundamentals",
];

/**
 * Every HardGate the decision engine can block on, paired with the exact
 * words it must reach the screen as.
 *
 * A gate is the engine refusing to treat a score as actionable. Listing the
 * identifiers alone let a translation say the opposite of what the engine
 * meant — "证据一致" for conflicting_evidence passed every check — so the
 * expected wording is pinned here rather than merely being readable Chinese.
 */
const GATES: [string, string][] = [
  ["stale_data", "数据陈旧"],
  ["insufficient_evidence", "证据不足"],
  ["conflicting_evidence", "证据冲突"],
  ["unverified_rumor", "未证实传闻"],
  ["low_liquidity", "流动性不足"],
  ["borrow_unavailable", "无券可借"],
  ["borrow_data_stale", "融券数据陈旧"],
];

/**
 * Fixed sentences the services emit. They are the service's own semantic
 * content and stay English on the wire; only what reaches the screen turns.
 */
const KNOWN_SENTENCES = [
  "Analysis only: this plan cannot submit, route, or execute an order.",
  "Scenario ranges are uncertain and require independent confirmation before any decision.",
  "Forecast calibration status is uncalibrated.",
  "Scenarios are uncertain analytical ranges, not promised prices.",
  "Realized volatility could not be measured, so no scenario range is offered.",
  "No completed candles were available at the decision cutoff.",
  "Capital-flow participation is unavailable for this snapshot.",
  "unsupported interval in v1",
  "unsupported intraday cadence",
  "mixed session flow points",
  "incomplete minute coverage",
  "zero activity denominator",
  "no price variation in the observed window",
];

describe("factor names", () => {
  it("gives every scored factor a Chinese name", () => {
    for (const factor of FACTORS) {
      expectReadableChinese(factorLabel(factor));
    }
    expect(factorLabel("fundamentals")).toBe("基本面");
    expect(factorLabel("geopolitics")).toBe("地缘政治");
    expect(factorLabel("institutional_flow")).toBe("机构资金");
    expect(factorLabel("macro")).toBe("宏观");
  });

  it("shows a factor it has no name for rather than dropping it", () => {
    // A factor the service adds later must still reach the reader. Unreadable
    // beats invisible: an omitted factor reads as a factor that was scored.
    expect(factorLabel("options_skew")).toBe("options_skew");
  });

  it("names the adviser soft factor's card title in Chinese", () => {
    // scoring.py appends "adviser" as a ninth FactorContribution outside the
    // FeatureSet the other eight names come from; it rendered as the bare
    // identifier "adviser" on the stock page until this entry existed
    // (2026-08-15 served-copy sweep, Franz's real-mode QA).
    expect(factorLabel("adviser")).toBe("顾问软因子");
  });
});

describe("hard gates", () => {
  it("names every gate exactly, never its opposite", () => {
    for (const [gate, expected] of GATES) {
      expect(gateLabel(gate)).toBe(expected);
    }
  });

  it("shows an unknown gate rather than dropping it", () => {
    expect(gateLabel("earnings_blackout")).toBe("earnings_blackout");
  });
});

describe("enumerations rendered on the decision card", () => {
  it("names every plan action, direction and scenario in Chinese", () => {
    for (const action of ["long", "short", "watch", "avoid"]) {
      expectReadableChinese(planActionLabel(action));
    }
    for (const direction of ["bullish", "bearish", "neutral"]) {
      expectReadableChinese(scoreDirectionLabel(direction));
    }
    for (const kind of ["bear", "base", "bull"]) {
      expectReadableChinese(scenarioLabel(kind));
    }
  });

  it("passes an unrecognised value through", () => {
    expect(planActionLabel("hedge")).toBe("hedge");
    expect(scoreDirectionLabel("mixed")).toBe("mixed");
    expect(scenarioLabel("tail")).toBe("tail");
  });
});

describe("service sentences", () => {
  it("translates every sentence the services are known to emit", () => {
    for (const sentence of KNOWN_SENTENCES) {
      const translated = serviceTextLabel(sentence);
      expect(translated).not.toBe(sentence);
      expectReadableChinese(translated);
    }
  });

  it("shows a sentence it does not know, word for word", () => {
    // The services own their wording and may add to it at any time. Text the
    // reader cannot parse is still better than a line that silently vanishes.
    const unknown = "Borrow availability was checked against a stale quote.";

    expect(serviceTextLabel(unknown)).toBe(unknown);
  });

  it("keeps the numbers a sentence carries", () => {
    const coverage = serviceTextLabel(
      "Scored on 70% of the factor weight; the rest has no source yet.",
    );
    expect(coverage).toContain("70%");
    expectReadableChinese(coverage);

    const stale = serviceTextLabel(
      "3 cited item(s) are older than the configured freshness window and are marked stale.",
    );
    expect(stale).toContain("3");
    expectReadableChinese(stale);

    const sample = serviceTextLabel("insufficient sample: 12 of 20 returns");
    expect(sample).toContain("12");
    expect(sample).toContain("20");
    expectReadableChinese(sample);
  });

  it("translates the gate identifiers embedded in a warning", () => {
    // The warning is assembled by the server out of raw gate values, so the
    // sentence and the identifiers inside it need the same table.
    const warning = serviceTextLabel(
      "Hard gate active: stale_data, insufficient_evidence",
    );

    expect(warning).toContain("数据陈旧");
    expect(warning).toContain("证据不足");
    expectReadableChinese(warning);
  });

  it("keeps an unknown gate visible inside a warning it does know", () => {
    const warning = serviceTextLabel("Hard gate active: stale_data, quiet_period");

    expect(warning).toContain("数据陈旧");
    expect(warning).toContain("quiet_period");
  });

  it("translates a factor-unavailable note into the factor name and the reason", () => {
    // The exact note Franz's 2026-08-15 real-mode QA reported as unreadable
    // code-log English on the stock page.
    const geopolitics = serviceTextLabel(
      "geopolitics unavailable (no_qualified_source).",
    );
    expect(geopolitics).toContain("地缘政治");
    expect(geopolitics).toContain("无合规数据源");
    expectReadableChinese(geopolitics);

    const institutionalFlow = serviceTextLabel(
      "institutional_flow unavailable (no_qualified_source).",
    );
    expect(institutionalFlow).toContain("机构资金");
    expect(institutionalFlow).toContain("无合规数据源");
    expectReadableChinese(institutionalFlow);
  });

  it("keeps an unknown factor-unavailable reason code visible", () => {
    const note = serviceTextLabel("macro unavailable (rate_limited).");

    expect(note).toContain("宏观");
    expect(note).toContain("rate_limited");
  });
});

describe("snapshot provenance", () => {
  it("names candle intervals and demo snapshots in Chinese", () => {
    expect(intervalLabel("5m")).toBe("5 分钟");
    expect(intervalLabel("day")).toBe("日线");
    for (const interval of ["demo-short", "demo-swing", "demo-long"]) {
      expectReadableChinese(intervalLabel(interval));
    }
  });

  it("passes an unknown interval through", () => {
    expect(intervalLabel("4h")).toBe("4h");
  });

  it("names every chart data status in Chinese", () => {
    // The chart eyebrow used to print these upper-cased: "5m · STALE".
    for (const status of ["demo", "live", "stale"]) {
      expectReadableChinese(chartStatusLabel(status));
    }
    expect(chartStatusLabel("stale")).toBe("缓存数据");
  });

  it("says a fixture snapshot is demo data while keeping the provider's name", () => {
    expect(snapshotSourceLabel("fixture")).toBe("演示数据");
    // moomoo is the provider's name, not an identifier to translate.
    expect(snapshotSourceLabel("moomoo")).toBe("moomoo");
  });
});

describe("one table, one place", () => {
  function sourceFiles(directory: string): string[] {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) {
        return entry.name === "__tests__" ? [] : sourceFiles(path);
      }
      return /\.tsx?$/.test(entry.name) && !/\.fixture\.ts$/.test(entry.name)
        ? [path]
        : [];
    });
  }

  it("keeps every server identifier translated in exactly one module", () => {
    // A second copy of the table drifts from the first, and the reader then
    // sees the same gate named two different ways on two screens.
    const root = join(__dirname, "..", "..");
    const vocabulary = join(root, "i18n", "serverVocabulary.ts");
    const offenders = sourceFiles(root)
      .filter((path) => path !== vocabulary)
      .filter((path) => {
        const source = readFileSync(path, "utf8");
        return (
          source.includes("stale_data") ||
          source.includes("institutional_flow") ||
          source.includes("Analysis only:")
        );
      });

    expect(offenders).toEqual([]);
  });
});
