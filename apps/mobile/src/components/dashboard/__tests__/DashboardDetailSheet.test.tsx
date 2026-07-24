import { expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { DashboardDetailSheet } from "../DashboardDetailSheet";

it("hides detail until opened and closes through a 44-point action", async () => {
  const onClose = jest.fn();
  const citations = [
    {
      id: "market-breadth",
      title: "市场广度日报",
      publisher: "Demo Research",
      url: "https://example.com/market-breadth",
      publishedAt: "2026-07-24T09:00:00Z",
      firstSeenAt: "2026-07-24T09:01:00Z",
      kind: "fact" as const,
    },
  ];
  const hidden = await render(
    <DashboardDetailSheet
      citations={citations}
      onClose={onClose}
      sections={[{ label: "最强反证", body: "市场广度尚未确认" }]}
      title="市场完整依据"
      visible={false}
    />,
  );
  expect(hidden.queryByText("最强反证")).toBeNull();

  const visible = await render(
    <DashboardDetailSheet
      citations={citations}
      onClose={onClose}
      sections={[{ label: "最强反证", body: "市场广度尚未确认" }]}
      title="市场完整依据"
      visible
    />,
  );
  expect(visible.getByText("最强反证")).toBeTruthy();
  expect(visible.getByText("市场广度日报")).toBeTruthy();

  const closeButton = visible.getByRole("button", { name: "关闭市场完整依据" });
  const closeStyle = StyleSheet.flatten(closeButton.props.style);
  expect(closeStyle.minHeight).toBeGreaterThanOrEqual(44);
  expect(closeStyle.minWidth).toBeGreaterThanOrEqual(44);

  fireEvent.press(closeButton);
  expect(onClose).toHaveBeenCalledTimes(1);
});
