import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { marketBriefFixture } from "@/data/__tests__/marketBrief.fixture";

import { MarketBriefCard } from "../MarketBriefCard";

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
