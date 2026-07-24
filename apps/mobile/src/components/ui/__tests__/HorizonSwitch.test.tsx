import { expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";

import { HorizonSwitch } from "../HorizonSwitch";

it("selects a horizon without changing the labels", async () => {
  const onChange = jest.fn();
  const view = await render(<HorizonSwitch value="short" onChange={onChange} />);

  fireEvent.press(view.getByText("波段 · 1–8周"));

  expect(onChange).toHaveBeenCalledWith("swing");
  expect(view.getByText("短线 · 0–5日")).toBeTruthy();
});
