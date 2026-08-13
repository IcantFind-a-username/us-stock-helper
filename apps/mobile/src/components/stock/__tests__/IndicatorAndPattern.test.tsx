import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { fixtureRepository } from "@/fixtures/repository";

import { PatternCard } from "../PatternCard";

// The MACD zero axis and the RSI reference lines moved into the chart's own
// subcharts, where they sit on the same x axis as the candles; they are covered
// by the PriceChart tests. What is left here is the separate trend read.
it("maps the separate trend honestly", async () => {
  const stock = fixtureRepository.getStock("PLTR", "short");
  const view = await render(
    <PatternCard
      dragonTrend={stock.dragonTrend}
      fundamentals={stock.fundamentals}
      magicNine={stock.magicNine}
      patterns={stock.patterns}
    />,
  );

  expect(view.getByText(/偏空.*46/)).toBeTruthy();
});
