import { expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { dashboardFixtures } from "@/fixtures/dashboard";

import { MarketRegimeHero } from "../MarketRegimeHero";

it("shows one decision frame and collapses the full research packet", async () => {
  const onOpenDetail = jest.fn();
  const view = await render(
    <MarketRegimeHero
      advice={dashboardFixtures.short.marketAdvice}
      conclusion={dashboardFixtures.short.marketConclusion}
      drivers={dashboardFixtures.short.marketDrivers}
      onOpenDetail={onOpenDetail}
      rationale={dashboardFixtures.short.marketRationale}
      score={dashboardFixtures.short.marketScore}
      updatedAt={dashboardFixtures.short.updatedAt}
    />,
  );

  expect(view.getByText("谨慎偏多")).toBeTruthy();
  expect(view.getByLabelText("市场评分 61")).toBeTruthy();
  expect(view.getAllByTestId("market-driver-chip")).toHaveLength(4);
  expect(view.queryByText("宏观、信用、能源与商品")).toBeNull();

  fireEvent.press(view.getByRole("button", { name: "查看完整依据" }));
  expect(onOpenDetail).toHaveBeenCalledTimes(1);
});

it("keeps dense hero copy readable on a real phone", async () => {
  const view = await render(
    <MarketRegimeHero
      advice={dashboardFixtures.short.marketAdvice}
      conclusion={dashboardFixtures.short.marketConclusion}
      drivers={dashboardFixtures.short.marketDrivers}
      onOpenDetail={jest.fn()}
      rationale={dashboardFixtures.short.marketRationale}
      score={dashboardFixtures.short.marketScore}
      updatedAt={dashboardFixtures.short.updatedAt}
    />,
  );

  const metadata = [
    view.getByText(/市场情绪结论/),
    view.getByText("今日建议"),
    view.getByText("新闻与社交情绪 +22"),
    view.getByText("查看依据 ›"),
  ];
  metadata.forEach((node) => {
    expect(StyleSheet.flatten(node.props.style).fontSize).toBeGreaterThanOrEqual(11);
  });
  expect(
    StyleSheet.flatten(view.getByText(dashboardFixtures.short.marketRationale).props.style)
      .fontSize,
  ).toBeGreaterThanOrEqual(12);
  expect(
    StyleSheet.flatten(view.getByText(dashboardFixtures.short.marketAdvice).props.style)
      .fontSize,
  ).toBeGreaterThanOrEqual(12);
});
