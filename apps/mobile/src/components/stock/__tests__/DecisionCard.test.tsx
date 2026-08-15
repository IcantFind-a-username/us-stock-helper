import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { decodeDecisionEnvelope } from "@/data/analysisGateway";
import { decisionFixture } from "@/data/__tests__/decision.fixture";

import { DecisionCard } from "../DecisionCard";

const now = new Date("2026-07-25T16:00:10.000Z");

function decision(mutate: (value: ReturnType<typeof decisionFixture>) => void = () => {}) {
  const value = decisionFixture();
  mutate(value);
  return decodeDecisionEnvelope(value, { now });
}

it("shows the score together with how much of the picture it had", async () => {
  const view = await render(<DecisionCard decision={decision()} />);

  expect(view.getByTestId("decision-interval")).toHaveTextContent(/日线/);
  expect(view.getByTestId("decision-score")).toHaveTextContent(/72.5/);
  // A score without its coverage reads as a complete verdict; four of the
  // eight factors have no feed yet.
  expect(view.getByTestId("decision-coverage")).toHaveTextContent(/因子覆盖 70%/);
});

it("shows every measured factor instead of leaving fundamentals in a dark card", async () => {
  const view = await render(
    <DecisionCard
      decision={decision((value) => {
        const score = value.score as Record<string, unknown>;
        score.unavailableFactors = ["geopolitics", "institutional_flow"];
        score.factorCoverage = 0.8;
        score.contributions = [
          {
            name: "fundamentals",
            rawValue: 0.64,
            weight: 0.14,
            points: 4.2,
            explanation: "SEC XBRL filing snapshot.",
          },
          {
            name: "macro",
            rawValue: 0.3,
            weight: 0.1,
            points: 1.5,
            explanation: "Treasury yield curve snapshot.",
          },
        ];
      })}
    />,
  );

  const factors = view.getByTestId("decision-factor-breakdown");
  expect(factors).toHaveTextContent(/基本面/);
  expect(factors).toHaveTextContent(/宏观/);
  expect(factors).toHaveTextContent(/贡献 \+4\.20/);
  expect(factors).toHaveTextContent(/权重 14%/);
});

it("names the unscored factors in Chinese instead of printing field names", async () => {
  const view = await render(<DecisionCard decision={decision()} />);

  const missing = view.getByTestId("decision-missing-factors");
  expect(missing).toHaveTextContent(/基本面/);
  expect(missing).toHaveTextContent(/地缘政治/);
  expect(missing).toHaveTextContent(/机构资金/);
  expect(missing).toHaveTextContent(/宏观/);
  expect(missing).not.toHaveTextContent(/institutional_flow/);
  expect(missing).not.toHaveTextContent(/fundamentals/);
});

it("keeps a factor it has no Chinese name for", async () => {
  const view = await render(
    <DecisionCard
      decision={decision((value) => {
        const score = value.score as Record<string, unknown>;
        score.unavailableFactors = ["options_skew"];
      })}
    />,
  );

  // The reader must learn the factor went unscored even when this app has
  // never heard of it.
  expect(view.getByTestId("decision-missing-factors")).toHaveTextContent(
    /options_skew/,
  );
});

it("renders the three scenarios with their disclaimer", async () => {
  const view = await render(<DecisionCard decision={decision()} />);

  const scenarios = view.getByTestId("decision-scenarios");
  expect(scenarios).toHaveTextContent(/下行 20%/);
  expect(scenarios).toHaveTextContent(/基准 40%/);
  expect(scenarios).toHaveTextContent(/上行 40%/);
  expect(scenarios).toHaveTextContent(/不是承诺的价格/);
  expect(scenarios).not.toHaveTextContent(/not promised prices/);
});

it("says the forecast is unavailable rather than omitting the section", async () => {
  const view = await render(
    <DecisionCard
      decision={decision((value) => {
        value.forecast = null;
        value.riskPlan = null;
        value.notes = [
          "Realized volatility could not be measured, so no scenario range is offered.",
        ];
      })}
    />,
  );

  // Dropping the section silently would let the reader assume it was simply
  // not part of this screen.
  expect(view.getByTestId("decision-no-forecast")).toBeTruthy();
  expect(view.queryByTestId("decision-scenarios")).toBeNull();
  expect(view.getByTestId("decision-card")).toHaveTextContent(/波动率/);
});

it("shows the plan's own warning that it cannot trade, in Chinese", async () => {
  const view = await render(<DecisionCard decision={decision()} />);

  const plan = view.getByTestId("decision-plan");
  expect(plan).toHaveTextContent(/不会提交、路由或执行任何委托/);
  expect(plan).not.toHaveTextContent(/cannot submit, route, or execute an order/);
  expect(plan).toHaveTextContent(/仓位上限 10%/);
});

it("translates the note about partial factor coverage", async () => {
  const view = await render(<DecisionCard decision={decision()} />);

  const card = view.getByTestId("decision-card");
  expect(card).toHaveTextContent(/70% 的因子权重/);
  expect(card).not.toHaveTextContent(/the rest has no source yet/);
});

it("shows a note and a warning it cannot translate, word for word", async () => {
  const view = await render(
    <DecisionCard
      decision={decision((value) => {
        value.notes = ["Borrow availability was checked against a stale quote."];
        const riskPlan = value.riskPlan as Record<string, unknown>;
        riskPlan.warnings = ["Position sizing assumes a cash account."];
      })}
    />,
  );

  // The services keep adding wording. Swallowing what this app has no
  // translation for would hide the service's own caveats from the reader.
  expect(view.getByTestId("decision-card")).toHaveTextContent(
    /Borrow availability was checked against a stale quote\./,
  );
  expect(view.getByTestId("decision-plan")).toHaveTextContent(
    /Position sizing assumes a cash account\./,
  );
});

it("names the gates inside the plan's hard-gate warning in Chinese", async () => {
  const view = await render(
    <DecisionCard
      decision={decision((value) => {
        const riskPlan = value.riskPlan as Record<string, unknown>;
        riskPlan.warnings = ["Hard gate active: stale_data, insufficient_evidence"];
      })}
    />,
  );

  const plan = view.getByTestId("decision-plan");
  expect(plan).toHaveTextContent(/数据陈旧/);
  expect(plan).toHaveTextContent(/证据不足/);
  expect(plan).not.toHaveTextContent(/Hard gate active/);
});

it("renders an unavailable decision without inventing a score", async () => {
  const view = await render(
    <DecisionCard
      decision={decision((value) => {
        value.status = "unavailable";
        value.score = null;
        value.forecast = null;
        value.riskPlan = null;
        value.notes = ["No completed candles were available at the decision cutoff."];
      })}
    />,
  );

  expect(view.getByText("暂不可用")).toBeTruthy();
  expect(view.getByTestId("decision-card")).toHaveTextContent(/已完成 K 线/);
  expect(view.queryByTestId("decision-coverage")).toBeNull();
  expect(view.queryByTestId("decision-score")).toBeNull();
});

it("says the conclusion was blocked instead of showing it like any other", async () => {
  const view = await render(
    <DecisionCard
      decision={decision((value) => {
        const score = value.score as Record<string, unknown>;
        score.actionable = false;
        score.blockedBy = ["stale_data", "insufficient_evidence"];
        // A blocked score with no forecast loses the risk plan too, and the
        // plan's warnings were the only place the gate was ever written down.
        value.forecast = null;
        value.riskPlan = null;
        value.notes = ["Realized volatility could not be measured."];
      })}
    />,
  );

  const card = view.getByTestId("decision-card");
  expect(card).toHaveTextContent(/不可行动/);
  expect(card).toHaveTextContent(/数据陈旧/);
  expect(card).toHaveTextContent(/证据不足/);
});

it("does not cry blocked when nothing is blocking", async () => {
  const view = await render(<DecisionCard decision={decision()} />);

  expect(view.queryByTestId("decision-blocked")).toBeNull();
});

it("says nothing about an adviser when no council ran for this response", async () => {
  // decisionFixture()'s default: adviserCouncil is not-requested and
  // adviserAdjustment is null. A watchlist-style score with no council input
  // must not read as if an adviser had a say.
  const view = await render(<DecisionCard decision={decision()} />);

  expect(view.queryByTestId("decision-adviser-fold")).toBeNull();
});

it("shows the baseline-vs-adjusted split only once the council actually ran", async () => {
  const view = await render(
    <DecisionCard
      decision={decision((value) => {
        (value.score as Record<string, unknown>).value = 75.5;
        value.adviserAdjustment = 3;
        value.adviserCouncil = {
          status: "available",
          reason: null,
          value: {
            summary: "各框架都读到同一条指引上调。",
            opinions: [
              {
                frameworkId: "technical",
                displayName: "技术结构框架",
                stance: "bullish",
                blindSpot: "对基本面突变无感。",
                conclusions: [
                  {
                    statement: "指引上调支持偏多的解读。",
                    confidence: "medium",
                    citations: [
                      {
                        evidenceId: "a",
                        quote: "raises full-year revenue guidance",
                        url: "https://reuters.example/a",
                        publisher: "reuters",
                        availableAt: "2026-07-25T15:41:00Z",
                        isCounterEvidence: false,
                      },
                    ],
                    counterEvidence: [],
                  },
                ],
              },
            ],
            baselineScore: 72.5,
            adjustedScore: 75.5,
            scoreAdjustment: 3,
            objectiveDirection: "bullish",
            actionable: true,
            blockedBy: [] as string[],
            disclaimer:
              "顾问观点是分析建议，不是操作指令；其影响有上限，且任一硬门未通过时一律作废。",
          },
        };
      })}
    />,
  );

  const fold = view.getByTestId("decision-adviser-fold");
  expect(fold).toHaveTextContent(/72\.5/);
  expect(fold).toHaveTextContent(/\+3\.0/);
});
