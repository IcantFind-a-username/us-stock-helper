import { expect, it } from "@jest/globals";

import { tabRoutes } from "../(tabs)/_layout";

it("registers the five product tabs with their Chinese labels and symbols", () => {
  expect(tabRoutes).toEqual([
    ["index", "首页", "home-outline"],
    ["discover", "发现", "scan-outline"],
    ["alerts", "提醒", "flash-outline"],
    ["journal", "复盘", "document-text-outline"],
    ["agent", "Agent", "sparkles-outline"],
  ]);
});
