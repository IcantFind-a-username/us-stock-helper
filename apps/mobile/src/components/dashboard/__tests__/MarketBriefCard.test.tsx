import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { marketBriefFixture } from "@/data/__tests__/marketBrief.fixture";
import type { MarketBriefDriverCoverage } from "@/domain/models";

import { MarketBriefCard } from "../MarketBriefCard";

/**
 * 2026-08-15 quant-foundations Task 5: `breadth` and `sector` are now
 * sourced by the server (breadth-v1 / sector-rs-v1). `MarketBriefCard`
 * itself needed no change for this -- driverCoverage already renders any
 * `available: true` entry's `conclusion`/`actionScore` generically -- so
 * this proves that generic path actually carries the two newly-sourced
 * categories' own scope label (自选广度（N 只）, never 市场广度) through
 * to the screen, rather than re-testing the renderer's existing behaviour.
 */
function withSourcedBreadthAndSector(
  driverCoverage: MarketBriefDriverCoverage[],
): MarketBriefDriverCoverage[] {
  return driverCoverage.map((entry) => {
    if (entry.category === "breadth") {
      return {
        category: "breadth",
        available: true,
        conclusion: "自选广度（5 只）· 多数走强 · 60% 收于50日均线上方",
        actionScore: 0.2,
        missingReason: null,
      };
    }
    if (entry.category === "sector") {
      return {
        category: "sector",
        available: true,
        conclusion: "板块强弱（21日，对比 SPY）· 领涨 XLK 超额收益 +9.1%",
        actionScore: 0.091,
        missingReason: null,
      };
    }
    return entry;
  });
}

it("renders the breadth driver's conclusion, score and 自选广度 scope label once sourced", async () => {
  const base = marketBriefFixture();
  const brief = {
    ...base,
    driverCoverage: withSourcedBreadthAndSector(base.driverCoverage),
  };

  const view = await render(
    <MarketBriefCard status="live" brief={brief} error={null} onRetry={() => {}} />,
  );

  expect(
    view.getByText("自选广度（5 只）· 多数走强 · 60% 收于50日均线上方 · +0.20"),
  ).toBeTruthy();
});

it("renders the sector driver's conclusion and score once sourced", async () => {
  const base = marketBriefFixture();
  const brief = {
    ...base,
    driverCoverage: withSourcedBreadthAndSector(base.driverCoverage),
  };

  const view = await render(
    <MarketBriefCard status="live" brief={brief} error={null} onRetry={() => {}} />,
  );

  expect(
    view.getByText("板块强弱（21日，对比 SPY）· 领涨 XLK 超额收益 +9.1% · +0.09"),
  ).toBeTruthy();
});

it("never renders 市场广度 as the breadth driver's own scope claim", async () => {
  // The row's fixed category chrome still reads "市场广度" (see
  // CATEGORY_LABELS below) -- that label names the topic, not a coverage
  // claim. The coverage claim lives entirely in the server-composed
  // conclusion text, which must say 自选广度, never imply full-market reach.
  const base = marketBriefFixture();
  const brief = {
    ...base,
    driverCoverage: withSourcedBreadthAndSector(base.driverCoverage),
  };

  const view = await render(
    <MarketBriefCard status="live" brief={brief} error={null} onRetry={() => {}} />,
  );

  const breadthValue = view.getByText(/自选广度（5 只）/);
  expect(breadthValue).not.toHaveTextContent("市场广度");
});

it("renders a note from the brief", async () => {
  const brief = marketBriefFixture({
    notes: [
      "有 1 条证据在决策截点之后才可用，未纳入本次结论：future-1",
    ],
  });

  const view = await render(
    <MarketBriefCard
      status="live"
      brief={brief}
      error={null}
      onRetry={() => {}}
    />,
  );

  expect(view.getByText(/有 1 条证据/)).toBeTruthy();
});

it("does not render notes section when notes array is empty", async () => {
  const brief = marketBriefFixture({ notes: [] });

  const view = await render(
    <MarketBriefCard
      status="live"
      brief={brief}
      error={null}
      onRetry={() => {}}
    />,
  );

  expect(view.queryByText(/有 1 条证据/)).toBeNull();
});

it("translates a note carrying a factor-unavailable identifier into Chinese", async () => {
  // Defense in depth (2026-08-15 served-copy sweep): `notes` used to render
  // straight through with no translation pass, so an English sentence a
  // future server change adds here would have reached this screen raw.
  const brief = marketBriefFixture({
    notes: ["geopolitics unavailable (no_qualified_source)."],
  });

  const view = await render(
    <MarketBriefCard
      status="live"
      brief={brief}
      error={null}
      onRetry={() => {}}
    />,
  );

  expect(view.getByTestId("market-brief-note")).toHaveTextContent(/地缘政治/);
  expect(view.getByTestId("market-brief-note")).not.toHaveTextContent(
    /unavailable/,
  );
});

it("runs the unavailable brief's own reason through the vocabulary layer", async () => {
  // `reason` used to render straight through with no translation pass at
  // all. It is always server-composed Chinese today, but the whole point of
  // this layer (per its own file header) is that a channel goes through it
  // regardless of what currently happens to be in the string -- proven here
  // with a sentence the table does know, standing in for a future English
  // one the untranslated render would have shown raw.
  const brief = marketBriefFixture({
    status: "unavailable",
    reason: "Analysis only: this plan cannot submit, route, or execute an order.",
    dataHealth: null,
    sentiment: null,
    citations: [],
  });

  const view = await render(
    <MarketBriefCard
      status="unavailable"
      brief={brief}
      error={null}
      onRetry={() => {}}
    />,
  );

  expect(view.getByTestId("market-brief-unavailable-reason")).toHaveTextContent(
    /不会提交、路由或执行任何委托/,
  );
});
