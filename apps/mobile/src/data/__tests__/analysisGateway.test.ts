import { describe, expect, it } from "@jest/globals";

import { decodeDecisionEnvelope } from "../analysisGateway";

import { decisionFixture } from "./decision.fixture";

const now = new Date("2026-07-25T16:00:10.000Z");

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
