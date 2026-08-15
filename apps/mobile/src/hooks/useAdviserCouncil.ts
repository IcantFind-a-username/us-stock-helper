import { useCallback, useEffect, useRef, useState } from "react";

import {
  AnalysisRequestError,
  DecisionValidationError,
  type AnalysisSource,
} from "@/data/analysisGateway";
import { MarketDataError } from "@/data/marketRepository";
import type { Decision, Horizon } from "@/domain/models";

/**
 * The thirteen-seat council call, and the only place on the phone that spends
 * the server's ~$0.10 / up-to-300s budget for it.
 *
 * Mirrors `useAdviserDecision`'s discipline exactly: no mount effect -- one
 * tap asks for one council opinion on one symbol and one horizon; leaving the
 * screen, changing symbol or horizon, or tapping again all cancel whatever is
 * in flight; and only one request is ever open at a time. It takes its
 * `AnalysisSource` as an argument rather than reading one out of
 * `MarketDataProvider`'s context: the council is a slower, opt-in,
 * symbol-scoped call with no reason to share that provider's lifetime, and
 * keeping this hook free of any context dependency is what makes it directly
 * testable with a fake `AnalysisSource` and nothing else.
 */

export type AdviserCouncilStatus = "idle" | "loading" | "live" | "unavailable";

export type AdviserCouncilState = {
  status: AdviserCouncilStatus;
  /** The whole decoded decision -- adviserCouncil, adviserUsage and all. */
  data: Decision | null;
  error: MarketDataError | null;
  request(): void;
};

function toMarketError(error: unknown): MarketDataError {
  if (error instanceof MarketDataError) return error;
  if (error instanceof AnalysisRequestError) {
    return new MarketDataError(error.kind, error.message);
  }
  if (error instanceof DecisionValidationError) {
    return new MarketDataError("validation", error.message);
  }
  return new MarketDataError(
    "offline",
    error instanceof Error ? error.message : "the adviser council is unavailable",
  );
}

export function useAdviserCouncil(
  analysis: AnalysisSource,
  symbol: string,
  horizon: Horizon,
): AdviserCouncilState {
  const normalizedSymbol = symbol.trim().toUpperCase();
  const scope = `${normalizedSymbol}|${horizon}`;
  const requestRef = useRef<AbortController | null>(null);
  const [state, setState] = useState<{
    scope: string;
    status: AdviserCouncilStatus;
    data: Decision | null;
    error: MarketDataError | null;
  }>({ scope, status: "idle", data: null, error: null });

  useEffect(
    () => () => {
      requestRef.current?.abort();
      requestRef.current = null;
    },
    [scope],
  );

  const request = useCallback(() => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setState({ scope, status: "loading", data: null, error: null });
    void analysis
      .getDecision(normalizedSymbol, horizon, controller.signal, {
        adviser: "full",
      })
      .then((data) => {
        if (requestRef.current !== controller) return;
        requestRef.current = null;
        setState({ scope, status: "live", data, error: null });
      })
      .catch((error: unknown) => {
        if (
          requestRef.current !== controller ||
          (error instanceof Error && error.name === "AbortError")
        ) {
          return;
        }
        requestRef.current = null;
        setState({
          scope,
          status: "unavailable",
          data: null,
          error: toMarketError(error),
        });
      });
  }, [analysis, horizon, normalizedSymbol, scope]);

  if (state.scope !== scope) {
    return { status: "idle", data: null, error: null, request };
  }
  return { ...state, request };
}
