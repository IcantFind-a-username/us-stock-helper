import type { PlanSide, RiskPreference, TradePlan } from "./models";

export function selectTradePlan(
  plans: TradePlan[],
  side: PlanSide,
  preference: RiskPreference,
  horizon: TradePlan["horizon"] = "short",
): TradePlan {
  const selected = plans.find(
    (plan) =>
      plan.side === side &&
      plan.preference === preference &&
      plan.horizon === horizon,
  );
  if (!selected) {
    throw new Error(`Missing trade plan for ${side}/${preference}`);
  }
  return selected;
}

export function evaluateTradePlanSafety(
  plan: TradePlan,
  decisionTime: string,
): { allowed: boolean; reasons: string[] } {
  const reasons: string[] = [];
  if (plan.leverage > plan.maximumLeverage) reasons.push("建议杠杆超过硬上限");
  if (plan.side !== "short") return { allowed: reasons.length === 0, reasons };
  if (!plan.shortRisk?.borrowAvailable) reasons.push("未确认可借券");

  const checkedAt = Date.parse(plan.shortRisk?.checkedAt ?? "");
  const decisionAt = Date.parse(decisionTime);
  if (!Number.isFinite(checkedAt) || !Number.isFinite(decisionAt)) {
    reasons.push("借券检查时间无效");
  } else if (checkedAt > decisionAt) {
    reasons.push("借券检查来自决策时点之后");
  } else if (decisionAt - checkedAt > 15 * 60 * 1_000) {
    reasons.push("借券检查已超过 15 分钟");
  }

  return { allowed: reasons.length === 0, reasons };
}
