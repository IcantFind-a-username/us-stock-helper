import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { toDemoChartSnapshot } from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";

import { IndicatorStrip } from "../IndicatorStrip";
import { PatternCard } from "../PatternCard";

it("renders factual MACD around a zero axis and maps the separate trend honestly", async () => {
  const stock = fixtureRepository.getStock("PLTR", "short");
  const chart = toDemoChartSnapshot(stock);
  const view = await render(
    <>
      <IndicatorStrip
        macd={chart.indicators.macd}
        rsi={chart.indicators.rsi}
      />
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
  expect(view.getByText("多头")).toBeTruthy();
  expect(view.getByText(/偏空.*46/)).toBeTruthy();
});
