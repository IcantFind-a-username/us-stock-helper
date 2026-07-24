import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { fixtureRepository } from "@/fixtures/repository";

import { IndicatorStrip } from "../IndicatorStrip";
import { PatternCard } from "../PatternCard";

it("renders bearish MACD around a zero axis and maps trend direction honestly", async () => {
  const stock = fixtureRepository.getStock("PLTR", "short");
  const view = await render(
    <>
      <IndicatorStrip macd={stock.indicators.macd} rsi={stock.indicators.rsi} />
      <PatternCard
        dragonTrend={stock.dragonTrend}
        fundamentals={stock.fundamentals}
        magicNine={stock.magicNine}
        patterns={stock.patterns}
      />
    </>,
  );

  expect(view.getByTestId("macd-zero-axis")).toBeTruthy();
  expect(view.getByTestId("rsi-threshold-30")).toBeTruthy();
  expect(view.getByTestId("rsi-threshold-70")).toBeTruthy();
  expect(view.getByText(/看跌背离/)).toBeTruthy();
  expect(view.getByText(/偏空.*46/)).toBeTruthy();
});
