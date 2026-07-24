import { expect, it } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";
import { Button, Text } from "react-native";

import { AppStateProvider, useAppState } from "../AppStateProvider";

function Probe() {
  const { horizon, setHorizon } = useAppState();

  return (
    <>
      <Text>{horizon}</Text>
      <Button title="swing" onPress={() => setHorizon("swing")} />
    </>
  );
}

it("defaults to short and switches horizons", async () => {
  const view = await render(
    <AppStateProvider>
      <Probe />
    </AppStateProvider>,
  );

  expect(view.getByText("short")).toBeTruthy();
  fireEvent.press(view.getByText("swing"));
  expect(view.getByText("swing")).toBeTruthy();
});
