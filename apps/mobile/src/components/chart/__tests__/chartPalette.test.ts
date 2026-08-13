import { expect, it } from "@jest/globals";

import { chartPalette } from "../chartPalette";

/** WCAG relative luminance, the definition the contrast ratio is built on. */
const luminance = (hex: string) => {
  const channels = [1, 3, 5]
    .map((start) => parseInt(hex.slice(start, start + 2), 16) / 255)
    .map((channel) =>
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
    );
  return (
    0.2126 * channels[0]! + 0.7152 * channels[1]! + 0.0722 * channels[2]!
  );
};

const contrast = (left: string, right: string) => {
  const [lighter, darker] = [luminance(left), luminance(right)].sort(
    (first, second) => second - first,
  );
  return (lighter! + 0.05) / (darker! + 0.05);
};

it("keeps a candle body dark enough to hold its colour against the card", () => {
  // A four-point body is a small mark, and a small mark needs 3:1 against its
  // background to still read as the colour it was drawn in. The page's own
  // green measures 2.4:1 there, which is why the chart does not borrow it.
  expect(contrast(chartPalette.up, chartPalette.surface)).toBeGreaterThanOrEqual(
    3,
  );
  expect(
    contrast(chartPalette.down, chartPalette.surface),
  ).toBeGreaterThanOrEqual(3);
});

it("keeps the ruling behind the bars rather than beside them", () => {
  // The grid is read against, never read: a full set of horizontal and vertical
  // rules at the border's own weight competes with the candles for attention.
  expect(contrast(chartPalette.grid, chartPalette.surface)).toBeLessThan(1.3);
  expect(contrast(chartPalette.axisLine, chartPalette.surface)).toBeGreaterThan(
    contrast(chartPalette.grid, chartPalette.surface),
  );
});
