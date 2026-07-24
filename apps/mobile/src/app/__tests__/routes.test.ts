import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";
import { createElement, Fragment } from "react";

import { tabRoutes } from "../(tabs)/_layout";
import AgentRoute from "../(tabs)/agent";
import AlertsRoute from "../(tabs)/alerts";
import DiscoverRoute from "../(tabs)/discover";
import DashboardRoute from "../(tabs)/index";
import JournalRoute from "../(tabs)/journal";
import AdvisersRoute from "../stocks/[symbol]/advisers";
import ChartRoute from "../stocks/[symbol]/chart";
import StockDetailRoute from "../stocks/[symbol]/index";
import { AdvisersScreen } from "@/screens/AdvisersScreen";
import { AgentScreen } from "@/screens/AgentScreen";
import { AlertsScreen } from "@/screens/AlertsScreen";
import { DashboardScreen } from "@/screens/DashboardScreen";
import { DiscoverScreen } from "@/screens/DiscoverScreen";
import { FullChartScreen } from "@/screens/FullChartScreen";
import { JournalScreen } from "@/screens/JournalScreen";
import { StockDetailScreen } from "@/screens/StockDetailScreen";

it("registers the five product tabs with their Chinese labels and symbols", () => {
  expect(tabRoutes).toEqual([
    ["index", "首页", "home-outline"],
    ["discover", "发现", "scan-outline"],
    ["alerts", "提醒", "flash-outline"],
    ["journal", "复盘", "document-text-outline"],
    ["agent", "Agent", "sparkles-outline"],
  ]);
});

it("keeps each tab and stock route as a thin screen export", () => {
  expect(DashboardRoute).toBe(DashboardScreen);
  expect(DiscoverRoute).toBe(DiscoverScreen);
  expect(AlertsRoute).toBe(AlertsScreen);
  expect(JournalRoute).toBe(JournalScreen);
  expect(AgentRoute).toBe(AgentScreen);
  expect(StockDetailRoute).toBe(StockDetailScreen);
  expect(ChartRoute).toBe(FullChartScreen);
  expect(AdvisersRoute).toBe(AdvisersScreen);
});

it("discloses demo and non-live status on every temporary route", async () => {
  const view = await render(
    createElement(
      Fragment,
      null,
      createElement(DashboardRoute),
      createElement(DiscoverRoute),
      createElement(AlertsRoute),
      createElement(JournalRoute),
      createElement(AgentRoute),
      createElement(StockDetailRoute),
      createElement(ChartRoute),
      createElement(AdvisersRoute),
    ),
  );

  expect(view.getAllByText("演示数据 · 非实时建议")).toHaveLength(8);
});
