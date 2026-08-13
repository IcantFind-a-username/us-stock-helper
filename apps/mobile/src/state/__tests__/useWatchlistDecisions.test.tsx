import { expect, it, jest } from "@jest/globals";
import { act, render, waitFor } from "@testing-library/react-native";
import { Text, View } from "react-native";

import {
  AnalysisRequestError,
  decodeDecisionEnvelope,
  type AnalysisSource,
} from "@/data/analysisGateway";
import { decisionFixture } from "@/data/__tests__/decision.fixture";
import { MarketDataError, type MarketRepository } from "@/data/marketRepository";
import type { Decision, Horizon } from "@/domain/models";

import { MarketDataProvider, useWatchlistDecisions } from "../MarketDataProvider";

const idleRepository = {
  peekStockSnapshot: () => null,
  getStockSnapshot: async () => {
    throw new MarketDataError("configuration", "not used in these tests");
  },
  peekWatchlist: () => null,
  getWatchlist: async () => {
    throw new MarketDataError("configuration", "not used in these tests");
  },
} satisfies MarketRepository;

function liveDecision(symbol: string, value: number, horizon: Horizon = "short") {
  const payload = decisionFixture();
  payload.symbol = symbol;
  payload.horizon = horizon;
  (payload.score as Record<string, unknown>).value = value;
  return decodeDecisionEnvelope(payload);
}

function unscoredDecision(symbol: string, horizon: Horizon = "short") {
  const payload = decisionFixture();
  payload.symbol = symbol;
  payload.horizon = horizon;
  payload.status = "unavailable";
  payload.score = null;
  payload.notes = ["没有任何来源覆盖该标的的因子。"];
  return decodeDecisionEnvelope(payload);
}

function DecisionProbe({
  symbols,
  horizon = "short",
}: {
  symbols: string[];
  horizon?: Horizon;
}) {
  const decisions = useWatchlistDecisions(symbols, horizon);
  return (
    <View>
      {symbols.map((symbol) => {
        const entry = decisions[symbol];
        return (
          <Text key={symbol} testID={`decision-${symbol}`}>
            {entry === undefined
              ? "missing"
              : `${entry.status}|${
                  entry.score === null ? "none" : entry.score.value
                }|${entry.error?.category ?? "none"}`}
          </Text>
        );
      })}
    </View>
  );
}

function renderProbe({
  analysis,
  symbols,
  horizon = "short",
  demoMode = false,
  decisionConcurrency,
}: {
  analysis: AnalysisSource;
  symbols: string[];
  horizon?: Horizon;
  demoMode?: boolean;
  decisionConcurrency?: number;
}) {
  return render(
    <MarketDataProvider
      analysis={analysis}
      development
      initialDemoMode={demoMode}
      repository={idleRepository}
      {...(decisionConcurrency === undefined ? {} : { decisionConcurrency })}>
      <DecisionProbe horizon={horizon} symbols={symbols} />
    </MarketDataProvider>,
  );
}

it("scores every requested symbol against the current horizon", async () => {
  const asked: { symbol: string; horizon: Horizon }[] = [];
  const resolvers = new Map<string, () => void>();
  const analysis: AnalysisSource = {
    getDecision: (symbol, horizon) => {
      asked.push({ symbol, horizon });
      return new Promise<Decision>((resolve) => {
        resolvers.set(symbol, () =>
          resolve(liveDecision(symbol, symbol === "NVDA" ? 72.5 : 41, horizon)),
        );
      });
    },
  };
  const view = await renderProbe({ analysis, symbols: ["NVDA", "TSLA"] });

  // An unanswered request is pending, which the row must not read as a verdict.
  expect(view.getByTestId("decision-NVDA").props.children).toBe(
    "loading|none|none",
  );
  expect(view.getByTestId("decision-TSLA").props.children).toBe(
    "loading|none|none",
  );

  await act(async () => {
    resolvers.forEach((resolve) => resolve());
  });

  await waitFor(() =>
    expect(view.getByTestId("decision-NVDA").props.children).toBe(
      "scored|72.5|none",
    ),
  );
  expect(view.getByTestId("decision-TSLA").props.children).toBe(
    "scored|41|none",
  );
  expect(asked).toEqual([
    { symbol: "NVDA", horizon: "short" },
    { symbol: "TSLA", horizon: "short" },
  ]);
});

it("never keeps more decision requests in flight than the configured limit", async () => {
  const started: string[] = [];
  const resolvers = new Map<string, (decision: Decision) => void>();
  const analysis: AnalysisSource = {
    getDecision: (symbol) => {
      started.push(symbol);
      return new Promise<Decision>((resolve) => {
        resolvers.set(symbol, resolve);
      });
    },
  };
  const symbols = Array.from({ length: 8 }, (_, index) => `SYM${index}`);
  const view = await renderProbe({ analysis, symbols, decisionConcurrency: 3 });

  await waitFor(() => expect(started).toHaveLength(3));
  expect(view.getByTestId("decision-SYM7").props.children).toBe(
    "loading|none|none",
  );

  await act(async () => {
    const resolve = resolvers.get("SYM0");
    resolvers.delete("SYM0");
    resolve?.(liveDecision("SYM0", 60));
  });
  expect(started).toEqual(["SYM0", "SYM1", "SYM2", "SYM3"]);

  await act(async () => {
    // Draining answer by answer is what proves the queue keeps handing work to
    // the freed worker until the last symbol has been asked about.
    while (resolvers.size > 0) {
      [...resolvers.entries()].forEach(([symbol, resolve]) => {
        resolvers.delete(symbol);
        resolve(liveDecision(symbol, 57));
      });
      await Promise.resolve();
      await Promise.resolve();
    }
  });

  expect(started).toEqual(symbols);
  await waitFor(() =>
    expect(view.getByTestId("decision-SYM7").props.children).toBe(
      "scored|57|none",
    ),
  );
});

it("separates a failed request from a chain that declined to score", async () => {
  const analysis: AnalysisSource = {
    getDecision: async (symbol, horizon) => {
      if (symbol === "DOWN") {
        throw new AnalysisRequestError("offline", "analysis service is unavailable");
      }
      if (symbol === "BLANK") return unscoredDecision(symbol, horizon);
      return liveDecision(symbol, 72.5, horizon);
    },
  };
  const view = await renderProbe({ analysis, symbols: ["NVDA", "DOWN", "BLANK"] });

  await waitFor(() =>
    expect(view.getByTestId("decision-DOWN").props.children).toBe(
      "unavailable|none|offline",
    ),
  );
  expect(view.getByTestId("decision-BLANK").props.children).toBe(
    "unscored|none|none",
  );
  expect(view.getByTestId("decision-NVDA").props.children).toBe(
    "scored|72.5|none",
  );
});

it("re-asks for the new horizon instead of reusing the previous verdict", async () => {
  const asked: Horizon[] = [];
  const analysis: AnalysisSource = {
    getDecision: async (symbol, horizon) => {
      asked.push(horizon);
      return liveDecision(symbol, horizon === "short" ? 72.5 : 30, horizon);
    },
  };
  const view = await render(
    <MarketDataProvider analysis={analysis} repository={idleRepository}>
      <DecisionProbe horizon="short" symbols={["NVDA"]} />
    </MarketDataProvider>,
  );
  await waitFor(() =>
    expect(view.getByTestId("decision-NVDA").props.children).toBe(
      "scored|72.5|none",
    ),
  );

  await view.rerender(
    <MarketDataProvider analysis={analysis} repository={idleRepository}>
      <DecisionProbe horizon="long" symbols={["NVDA"]} />
    </MarketDataProvider>,
  );

  await waitFor(() =>
    expect(view.getByTestId("decision-NVDA").props.children).toBe(
      "scored|30|none",
    ),
  );
  expect(asked).toEqual(["short", "long"]);
});

it("asks only for the symbols that were newly revealed", async () => {
  const asked: string[] = [];
  const analysis: AnalysisSource = {
    getDecision: async (symbol, horizon) => {
      asked.push(symbol);
      return liveDecision(symbol, 60, horizon);
    },
  };
  const view = await render(
    <MarketDataProvider analysis={analysis} repository={idleRepository}>
      <DecisionProbe horizon="short" symbols={["NVDA", "TSLA"]} />
    </MarketDataProvider>,
  );
  await waitFor(() => expect(asked).toEqual(["NVDA", "TSLA"]));

  await view.rerender(
    <MarketDataProvider analysis={analysis} repository={idleRepository}>
      <DecisionProbe horizon="short" symbols={["NVDA", "TSLA", "PLTR"]} />
    </MarketDataProvider>,
  );

  await waitFor(() => expect(asked).toEqual(["NVDA", "TSLA", "PLTR"]));
  expect(view.getByTestId("decision-PLTR").props.children).toBe(
    "scored|60|none",
  );
});

it("asks again for a request that was aborted before it answered", async () => {
  const started: string[] = [];
  const resolvers = new Map<string, (decision: Decision) => void>();
  const analysis: AnalysisSource = {
    getDecision: (symbol) => {
      started.push(symbol);
      return new Promise<Decision>((resolve) => {
        resolvers.set(symbol, resolve);
      });
    },
  };
  const view = await render(
    <MarketDataProvider analysis={analysis} repository={idleRepository}>
      <DecisionProbe horizon="short" symbols={["NVDA", "TSLA"]} />
    </MarketDataProvider>,
  );
  await waitFor(() => expect(started).toEqual(["NVDA", "TSLA"]));

  // Revealing another row aborts the open requests. They never answered, so
  // their rows would sit on "loading" forever if nobody asked a second time.
  await view.rerender(
    <MarketDataProvider analysis={analysis} repository={idleRepository}>
      <DecisionProbe horizon="short" symbols={["NVDA", "TSLA", "PLTR"]} />
    </MarketDataProvider>,
  );

  await waitFor(() =>
    expect(started).toEqual(["NVDA", "TSLA", "NVDA", "TSLA", "PLTR"]),
  );
  expect(view.getByTestId("decision-NVDA").props.children).toBe(
    "loading|none|none",
  );

  await act(async () => {
    resolvers.get("NVDA")?.(liveDecision("NVDA", 66));
  });
  await waitFor(() =>
    expect(view.getByTestId("decision-NVDA").props.children).toBe(
      "scored|66|none",
    ),
  );
});

it("asks the analysis service nothing in demo mode and says so per symbol", async () => {
  const getDecision = jest.fn<AnalysisSource["getDecision"]>(async (symbol) =>
    liveDecision(symbol, 72.5),
  );
  const view = await renderProbe({
    analysis: { getDecision },
    symbols: ["NVDA", "TSLA"],
    demoMode: true,
  });

  await waitFor(() =>
    expect(view.getByTestId("decision-NVDA").props.children).toBe(
      "demo|none|none",
    ),
  );
  expect(view.getByTestId("decision-TSLA").props.children).toBe(
    "demo|none|none",
  );
  expect(getDecision).not.toHaveBeenCalled();
});

it("aborts in-flight decision requests when the screen goes away", async () => {
  const signals: AbortSignal[] = [];
  const analysis: AnalysisSource = {
    getDecision: (_symbol, _horizon, signal) => {
      if (signal) signals.push(signal);
      return new Promise<Decision>(() => undefined);
    },
  };
  const view = await renderProbe({ analysis, symbols: ["NVDA"] });

  await waitFor(() => expect(signals).toHaveLength(1));
  expect(signals[0]?.aborted).toBe(false);

  await view.unmount();

  expect(signals[0]?.aborted).toBe(true);
});

it("rejects a decision concurrency that would stall every request", async () => {
  const analysis: AnalysisSource = {
    getDecision: async (symbol) => liveDecision(symbol, 50),
  };

  await expect(
    (async () =>
      render(
        <MarketDataProvider
          analysis={analysis}
          decisionConcurrency={0}
          repository={idleRepository}>
          <DecisionProbe symbols={["NVDA"]} />
        </MarketDataProvider>,
      ))(),
  ).rejects.toThrow(/decisionConcurrency/);
});
