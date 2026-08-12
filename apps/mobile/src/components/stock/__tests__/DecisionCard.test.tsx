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

  expect(view.getByTestId("decision-score")).toHaveTextContent(/72.5/);
  // A score without its coverage reads as a complete verdict; four of the
  // eight factors have no feed yet.
  expect(view.getByTestId("decision-coverage")).toHaveTextContent(/因子覆盖 70%/);
  expect(view.getByTestId("decision-missing-factors")).toHaveTextContent(/macro/);
});

it("renders the three scenarios with their disclaimer", async () => {
  const view = await render(<DecisionCard decision={decision()} />);

  const scenarios = view.getByTestId("decision-scenarios");
  expect(scenarios).toHaveTextContent(/下行 20%/);
  expect(scenarios).toHaveTextContent(/基准 40%/);
  expect(scenarios).toHaveTextContent(/上行 40%/);
  expect(scenarios).toHaveTextContent(/not promised prices/);
});

it("says the forecast is unavailable rather than omitting the section", async () => {
  const view = await render(
    <DecisionCard
      decision={decision((value) => {
        value.forecast = null;
        value.riskPlan = null;
        value.notes = ["Realized volatility could not be measured."];
      })}
    />,
  );

  // Dropping the section silently would let the reader assume it was simply
  // not part of this screen.
  expect(view.getByTestId("decision-no-forecast")).toBeTruthy();
  expect(view.queryByTestId("decision-scenarios")).toBeNull();
  expect(view.getByTestId("decision-card")).toHaveTextContent(/volatility/);
});

it("shows the plan's own warning that it cannot trade", async () => {
  const view = await render(<DecisionCard decision={decision()} />);

  expect(view.getByTestId("decision-plan")).toHaveTextContent(
    /cannot submit, route, or execute an order/,
  );
  expect(view.getByTestId("decision-plan")).toHaveTextContent(/仓位上限 10%/);
});

it("renders an unavailable decision without inventing a score", async () => {
  const view = await render(
    <DecisionCard
      decision={decision((value) => {
        value.status = "unavailable";
        value.score = null;
        value.forecast = null;
        value.riskPlan = null;
        value.notes = ["No completed candles were available."];
      })}
    />,
  );

  expect(view.getByText("暂不可用")).toBeTruthy();
  expect(view.queryByTestId("decision-coverage")).toBeNull();
  expect(view.queryByTestId("decision-score")).toBeNull();
});
