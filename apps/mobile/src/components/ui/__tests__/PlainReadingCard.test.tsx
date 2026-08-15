import { expect, it } from "@jest/globals";
import { render, userEvent } from "@testing-library/react-native";

import { PlainReadingCard } from "../PlainReadingCard";

const NUMBERS = {
  value: "62%",
  sampleSize: "样本为当前自选列表（5 只）。",
  invalidation: "当自选列表为空时，这个结论会变为不可用。",
};

it("always shows the one-sentence headline (layer 1)", async () => {
  const view = await render(
    <PlainReadingCard
      headline="自选列表里大多数股票都站上了自己的50日均线。"
      explanation="展开解释文字。"
      numbers={NUMBERS}
    />,
  );

  expect(
    view.getByText("自选列表里大多数股票都站上了自己的50日均线。"),
  ).toBeTruthy();
});

it("hides the explanation and numbers layers until expanded", async () => {
  const view = await render(
    <PlainReadingCard
      headline="标题。"
      explanation="展开解释文字，带一个生活化的类比。"
      numbers={NUMBERS}
    />,
  );

  expect(view.queryByText("展开解释文字，带一个生活化的类比。")).toBeNull();
  expect(view.queryByText(/62%/)).toBeNull();
});

it("reveals layer 2 (explanation) and layer 3 (numbers) on tap", async () => {
  const view = await render(
    <PlainReadingCard
      headline="标题。"
      explanation="展开解释文字，带一个生活化的类比。"
      numbers={NUMBERS}
    />,
  );

  await userEvent.setup().press(view.getByRole("button"));

  expect(view.getByText("展开解释文字，带一个生活化的类比。")).toBeTruthy();
  expect(view.getByText(/62%/)).toBeTruthy();
  expect(view.getByText(/样本为当前自选列表（5 只）/)).toBeTruthy();
  expect(view.getByText(/当自选列表为空时/)).toBeTruthy();
});

it("toggles closed again on a second tap", async () => {
  const view = await render(
    <PlainReadingCard
      headline="标题。"
      explanation="展开解释文字。"
      numbers={NUMBERS}
    />,
  );
  const user = userEvent.setup();

  await user.press(view.getByRole("button"));
  expect(view.queryByText("展开解释文字。")).toBeTruthy();

  await user.press(view.getByRole("button"));
  expect(view.queryByText("展开解释文字。")).toBeNull();
});

it("reports its expanded state for accessibility", async () => {
  const view = await render(
    <PlainReadingCard
      headline="标题。"
      explanation="展开解释文字。"
      numbers={NUMBERS}
    />,
  );

  const button = view.getByRole("button");
  expect(button.props.accessibilityState).toMatchObject({ expanded: false });

  await userEvent.setup().press(button);
  expect(view.getByRole("button").props.accessibilityState).toMatchObject({
    expanded: true,
  });
});

it("renders an optional supplementary note in the numbers layer when provided", async () => {
  const view = await render(
    <PlainReadingCard
      headline="标题。"
      explanation="展开解释文字。"
      numbers={{ ...NUMBERS, note: "最近一次数满 9 的九转方向是上涨。" }}
    />,
  );

  await userEvent.setup().press(view.getByRole("button"));

  expect(view.getByText(/最近一次数满 9 的九转方向是上涨/)).toBeTruthy();
});

it("does not render a note line when none is provided", async () => {
  const view = await render(
    <PlainReadingCard
      headline="标题。"
      explanation="展开解释文字。"
      numbers={NUMBERS}
    />,
  );

  await userEvent.setup().press(view.getByRole("button"));

  expect(view.queryByTestId("plain-reading-note")).toBeNull();
});
