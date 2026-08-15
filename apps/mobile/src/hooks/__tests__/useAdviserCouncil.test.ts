import { expect, it } from "@jest/globals";
import { act, renderHook, waitFor } from "@testing-library/react-native";

import type { AnalysisSource } from "@/data/analysisGateway";
import { AnalysisRequestError } from "@/data/analysisGateway";
import { decisionFixture } from "@/data/__tests__/decision.fixture";
import type { Decision } from "@/domain/models";

import { useAdviserCouncil } from "../useAdviserCouncil";

function liveDecision(): Decision {
  return decisionFixture() as unknown as Decision;
}

/**
 * A controllable fake of the one method the hook calls. Each call gets its
 * own deferred promise so a test can resolve, reject, or simply inspect the
 * abort signal it was handed without a real network.
 */
function deferredAnalysis() {
  const calls: {
    symbol: string;
    horizon: string;
    signal: AbortSignal | undefined;
    options: unknown;
    resolve: (value: Decision) => void;
    reject: (error: unknown) => void;
  }[] = [];
  const analysis: AnalysisSource = {
    getDecision: (symbol, horizon, signal, options) =>
      new Promise<Decision>((resolve, reject) => {
        calls.push({ symbol, horizon, signal, options, resolve, reject });
      }),
  };
  return { analysis, calls };
}

it("starts idle and never calls the analysis source on its own", async () => {
  const { analysis, calls } = deferredAnalysis();
  const { result } = await renderHook(() =>
    useAdviserCouncil(analysis, "nvda", "short"),
  );

  expect(result.current.status).toBe("idle");
  expect(result.current.data).toBeNull();
  expect(result.current.error).toBeNull();
  expect(calls).toHaveLength(0);
});

it("asks for the full council, not the news adviser, exactly once per tap", async () => {
  const { analysis, calls } = deferredAnalysis();
  const { result } = await renderHook(() =>
    useAdviserCouncil(analysis, "nvda", "short"),
  );

  await act(async () => {
    result.current.request();
  });

  expect(result.current.status).toBe("loading");
  expect(calls).toHaveLength(1);
  expect(calls[0]?.symbol).toBe("NVDA");
  expect(calls[0]?.horizon).toBe("short");
  expect(calls[0]?.options).toEqual({ adviser: "full" });
  expect(calls[0]?.signal?.aborted).toBe(false);
});

it("goes live with the decoded decision once the call resolves", async () => {
  const { analysis, calls } = deferredAnalysis();
  const { result } = await renderHook(() =>
    useAdviserCouncil(analysis, "nvda", "short"),
  );

  await act(async () => {
    result.current.request();
  });
  await act(async () => {
    calls[0]?.resolve(liveDecision());
  });

  await waitFor(() => expect(result.current.status).toBe("live"));
  expect(result.current.data?.symbol).toBe("NVDA");
  expect(result.current.error).toBeNull();
});

it("reports a failed call as unavailable with a translated error, not a thrown exception", async () => {
  const { analysis, calls } = deferredAnalysis();
  const { result } = await renderHook(() =>
    useAdviserCouncil(analysis, "nvda", "short"),
  );

  await act(async () => {
    result.current.request();
  });
  await act(async () => {
    calls[0]?.reject(new AnalysisRequestError("timeout", "timed out"));
  });

  await waitFor(() => expect(result.current.status).toBe("unavailable"));
  expect(result.current.data).toBeNull();
  expect(result.current.error?.category).toBe("timeout");
});

it("aborts the in-flight call and starts a fresh one when tapped again before it answers", async () => {
  const { analysis, calls } = deferredAnalysis();
  const { result } = await renderHook(() =>
    useAdviserCouncil(analysis, "nvda", "short"),
  );

  await act(async () => {
    result.current.request();
  });
  await act(async () => {
    result.current.request();
  });

  expect(calls).toHaveLength(2);
  expect(calls[0]?.signal?.aborted).toBe(true);
  expect(calls[1]?.signal?.aborted).toBe(false);
  expect(result.current.status).toBe("loading");
});

it("ignores a stale answer from a request superseded by a second tap", async () => {
  const { analysis, calls } = deferredAnalysis();
  const { result } = await renderHook(() =>
    useAdviserCouncil(analysis, "nvda", "short"),
  );

  await act(async () => {
    result.current.request();
  });
  await act(async () => {
    result.current.request();
  });
  await act(async () => {
    // The superseded first call answers late; it must not overwrite the
    // second, still-loading request.
    calls[0]?.resolve({ ...liveDecision(), symbol: "STALE" } as Decision);
  });

  expect(result.current.status).toBe("loading");

  await act(async () => {
    calls[1]?.resolve(liveDecision());
  });
  await waitFor(() => expect(result.current.status).toBe("live"));
  expect(result.current.data?.symbol).toBe("NVDA");
});

it("aborts whatever is in flight when the screen unmounts", async () => {
  const { analysis, calls } = deferredAnalysis();
  const { result, unmount } = await renderHook(() =>
    useAdviserCouncil(analysis, "nvda", "short"),
  );

  await act(async () => {
    result.current.request();
  });
  await unmount();

  expect(calls[0]?.signal?.aborted).toBe(true);
});

it("resets to idle when the symbol or horizon changes underneath it", async () => {
  const { analysis, calls } = deferredAnalysis();
  const { result, rerender } = await renderHook(
    ({ symbol, horizon }: { symbol: string; horizon: "short" | "swing" | "long" }) =>
      useAdviserCouncil(analysis, symbol, horizon),
    { initialProps: { symbol: "nvda", horizon: "short" } },
  );

  await act(async () => {
    result.current.request();
  });
  expect(result.current.status).toBe("loading");

  await rerender({ symbol: "msft", horizon: "short" });

  expect(result.current.status).toBe("idle");
  expect(result.current.data).toBeNull();
  // The abandoned scope's in-flight request is cancelled, not left to answer
  // into a screen that has moved on to a different symbol.
  expect(calls[0]?.signal?.aborted).toBe(true);
});
