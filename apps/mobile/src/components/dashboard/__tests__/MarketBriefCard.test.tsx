import { describe, expect, it } from "@jest/globals";
import { render, userEvent, within } from "@testing-library/react-native";

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

/**
 * 2026-08-15 Task 6: breadth and sector are the two market-brief drivers
 * with an actual computed state (自选广度 label, sector leader's excess
 * return), so their rows gain a tap-to-expand plain-language reading. The
 * other seven categories stay a plain missingReason line -- there is no
 * state to classify for a source that was never wired.
 */
describe("plain-language readings on the breadth and sector driver rows", () => {
  it("shows a collapsed plain-language headline for the sourced breadth driver", async () => {
    const base = marketBriefFixture();
    const brief = {
      ...base,
      driverCoverage: withSourcedBreadthAndSector(base.driverCoverage),
    };

    const view = await render(
      <MarketBriefCard status="live" brief={brief} error={null} onRetry={() => {}} />,
    );

    expect(
      view.getByText("自选列表里大多数股票都站上了自己的50日均线，参与上涨的股票较多。"),
    ).toBeTruthy();
    // Layer 2/3 stay collapsed until tapped.
    expect(view.queryByTestId("plain-reading-explanation")).toBeNull();
  });

  it("reveals the breadth reading's explanation and numbers layers on tap", async () => {
    const base = marketBriefFixture();
    const brief = {
      ...base,
      driverCoverage: withSourcedBreadthAndSector(base.driverCoverage),
    };

    const view = await render(
      <MarketBriefCard status="live" brief={brief} error={null} onRetry={() => {}} />,
    );

    const breadthCard = view.getByTestId("plain-reading-card-breadth");
    await userEvent.setup().press(within(breadthCard).getByRole("button"));

    expect(view.getByTestId("plain-reading-explanation")).toHaveTextContent(
      /50日均线/,
    );
    expect(view.getByTestId("plain-reading-numbers")).toHaveTextContent(/\+0\.20/);
  });

  it("shows a collapsed plain-language headline for the sourced sector driver", async () => {
    const base = marketBriefFixture();
    const brief = {
      ...base,
      driverCoverage: withSourcedBreadthAndSector(base.driverCoverage),
    };

    const view = await render(
      <MarketBriefCard status="live" brief={brief} error={null} onRetry={() => {}} />,
    );

    expect(view.getByText("当前领先的板块跑赢了基准，相对走势偏强。")).toBeTruthy();
  });

  it("reads an unavailable breadth driver's plain-language state too", async () => {
    const brief = marketBriefFixture(); // default fixture: breadth/sector unsourced

    const view = await render(
      <MarketBriefCard status="live" brief={brief} error={null} onRetry={() => {}} />,
    );

    expect(
      view.getByText("自选广度暂不可用：历史K线不够计算50日均线。"),
    ).toBeTruthy();
    expect(
      view.getByText("板块强弱暂不可用：样本不足或历史数据不够计算相对强弱。"),
    ).toBeTruthy();
  });

  it("never renders a plain-language reading card for the seven unsourced drivers", async () => {
    const brief = marketBriefFixture();

    const view = await render(
      <MarketBriefCard status="live" brief={brief} error={null} onRetry={() => {}} />,
    );

    // Only breadth + sector get a reading card, even though all nine rows render.
    expect(view.getAllByTestId(/^plain-reading-card-/)).toHaveLength(2);
  });
});
