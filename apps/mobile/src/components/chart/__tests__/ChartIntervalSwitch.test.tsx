import { expect, it, jest } from "@jest/globals";
import { render, userEvent } from "@testing-library/react-native";

import { ChartIntervalSwitch } from "../ChartIntervalSwitch";

it("defaults the selected period accessibly and emits an explicit interval", async () => {
  const onChange = jest.fn();
  const view = await render(
    <ChartIntervalSwitch onChange={onChange} value="day" />,
  );

  expect(view.getByRole("tab", { name: "日K" }).props.accessibilityState).toEqual({
    selected: true,
  });

  await userEvent.setup().press(view.getByRole("tab", { name: "5分" }));
  expect(onChange).toHaveBeenCalledWith("5m");
});

it("keeps every period target at the minimum iPhone touch height", async () => {
  const view = await render(
    <ChartIntervalSwitch onChange={() => {}} value="day" />,
  );

  for (const label of ["日K", "60分", "15分", "5分"]) {
    const tab = view.getByRole("tab", { name: label });
    const style = [tab.props.style].flat(Infinity) as { minHeight?: number }[];
    expect(Math.max(...style.map((item) => item?.minHeight ?? 0))).toBeGreaterThanOrEqual(44);
  }
});
