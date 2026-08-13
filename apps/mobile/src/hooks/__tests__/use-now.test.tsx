import { afterEach, beforeEach, expect, it, jest } from "@jest/globals";
import { act, render } from "@testing-library/react-native";
import { Text } from "react-native";

import { useNow } from "../use-now";

function Clock() {
  return <Text testID="clock">{useNow(15_000).toISOString()}</Text>;
}

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date("2026-08-13T13:30:05.000Z"));
});

afterEach(() => {
  jest.useRealTimers();
});

it("advances while the screen stays mounted", async () => {
  const view = await render(<Clock />);
  expect(view.getByTestId("clock")).toHaveTextContent(
    "2026-08-13T13:30:05.000Z",
  );

  await act(async () => {
    jest.advanceTimersByTime(60_000);
  });

  expect(view.getByTestId("clock")).toHaveTextContent(
    "2026-08-13T13:31:05.000Z",
  );
});

it("stops ticking once the screen is gone", async () => {
  const view = await render(<Clock />);
  const clearInterval = jest.spyOn(globalThis, "clearInterval");

  await view.unmount();

  expect(clearInterval).toHaveBeenCalled();
  clearInterval.mockRestore();
});
