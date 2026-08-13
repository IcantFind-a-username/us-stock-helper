import { describe, expect, it } from "@jest/globals";

import { shanghaiGreeting } from "../greeting";

describe("shanghaiGreeting", () => {
  it.each([
    ["2026-08-13T17:45:00.000Z", "夜深了，Franz"],
    ["2026-08-13T22:00:00.000Z", "早上好，Franz"],
    ["2026-08-14T04:00:00.000Z", "中午好，Franz"],
    ["2026-08-14T07:00:00.000Z", "下午好，Franz"],
    ["2026-08-14T12:00:00.000Z", "晚上好，Franz"],
  ])("uses Shanghai time for %s", (instant, expected) => {
    expect(shanghaiGreeting(new Date(instant), "Franz")).toBe(expected);
  });

  it("does not depend on the host date when Shanghai is already after midnight", () => {
    expect(
      shanghaiGreeting(new Date("2026-08-13T17:45:00.000Z"), "Franz"),
    ).toBe("夜深了，Franz");
  });
});
