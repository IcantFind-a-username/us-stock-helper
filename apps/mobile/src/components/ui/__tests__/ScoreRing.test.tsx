import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { clampScore, ScoreRing } from "../ScoreRing";

it("clamps the market score and exposes it accessibly", async () => {
  expect(clampScore(-20)).toBe(0);
  expect(clampScore(61)).toBe(61);
  expect(clampScore(140)).toBe(100);

  const view = await render(<ScoreRing score={61} />);
  expect(view.getByLabelText("市场评分 61")).toBeTruthy();
  expect(view.getByText("61")).toBeTruthy();
});
