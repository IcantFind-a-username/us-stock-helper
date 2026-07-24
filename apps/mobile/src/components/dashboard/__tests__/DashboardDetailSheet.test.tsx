import { expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";

import { DashboardDetailSheet } from "../DashboardDetailSheet";

it("hides detail until opened and closes through a 44-point action", async () => {
  const onClose = jest.fn();
  const hidden = await render(
    <DashboardDetailSheet
      citations={[]}
      onClose={onClose}
      sections={[{ label: "最强反证", body: "市场广度尚未确认" }]}
      title="市场完整依据"
      visible={false}
    />,
  );
  expect(hidden.queryByText("最强反证")).toBeNull();

  const visible = await render(
    <DashboardDetailSheet
      citations={[]}
      onClose={onClose}
      sections={[{ label: "最强反证", body: "市场广度尚未确认" }]}
      title="市场完整依据"
      visible
    />,
  );
  expect(visible.getByText("最强反证")).toBeTruthy();
  fireEvent.press(visible.getByRole("button", { name: "关闭市场完整依据" }));
  expect(onClose).toHaveBeenCalledTimes(1);
});
