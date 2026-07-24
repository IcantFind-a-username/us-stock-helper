import { expect, it } from "@jest/globals";

import type { PlanSide, RiskPreference } from "@/domain/models";
import { tradePlanFixtures } from "@/fixtures/advisers";

import { evaluateTradePlanSafety, selectTradePlan } from "../plan";

const cases: [PlanSide, RiskPreference, string][] = [
  ["long", "conservative", "NVDA-long-conservative"],
  ["long", "balanced", "NVDA-long-balanced"],
  ["long", "aggressive", "NVDA-long-aggressive"],
  ["short", "conservative", "NVDA-short-conservative"],
  ["short", "balanced", "NVDA-short-balanced"],
  ["short", "aggressive", "NVDA-short-aggressive"],
];

it.each(cases)("selects the exact %s %s fixture without mutating objective facts", (side, preference, id) => {
  const plan = selectTradePlan(tradePlanFixtures, side, preference);

  expect(plan.id).toBe(id);
  expect(plan.objectiveScore).toBe(72);
  expect(plan.confidence).toBe(0.68);
  expect(plan.maximumLeverage).toBe(1.5);
  expect(plan.shortRisk === null).toBe(side === "long");
});

it("fails closed when the requested deterministic plan is missing", () => {
  expect(() => selectTradePlan([], "long", "balanced")).toThrow(
    "Missing trade plan for long/balanced",
  );
});

it("fails closed for stale, future-dated, or unavailable short borrow checks", () => {
  const plan = selectTradePlan(tradePlanFixtures, "short", "balanced");
  const decisionTime = "2026-07-24T11:50:02-04:00";

  expect(evaluateTradePlanSafety(plan, decisionTime)).toEqual({
    allowed: true,
    reasons: [],
  });
  expect(
    evaluateTradePlanSafety(
      {
        ...plan,
        shortRisk: { ...plan.shortRisk!, checkedAt: "2026-07-24T10:00:00-04:00" },
      },
      decisionTime,
    ),
  ).toEqual({
    allowed: false,
    reasons: ["借券检查已超过 15 分钟"],
  });
  expect(
    evaluateTradePlanSafety(
      {
        ...plan,
        shortRisk: { ...plan.shortRisk!, checkedAt: "2026-07-24T12:00:00-04:00" },
      },
      decisionTime,
    ),
  ).toEqual({
    allowed: false,
    reasons: ["借券检查来自决策时点之后"],
  });
  expect(
    evaluateTradePlanSafety(
      {
        ...plan,
        shortRisk: { ...plan.shortRisk!, borrowAvailable: false },
      },
      decisionTime,
    ),
  ).toEqual({
    allowed: false,
    reasons: ["未确认可借券"],
  });
});
