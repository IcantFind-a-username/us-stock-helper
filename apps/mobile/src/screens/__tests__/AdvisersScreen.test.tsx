import { beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import type { PropsWithChildren } from "react";

import { AppStateProvider } from "@/state/AppStateProvider";
import { DeviceSessionProvider } from "@/state/DeviceSessionProvider";

import { AdvisersScreen } from "../AdvisersScreen";
import { MarketDataProvider } from "@/state/MarketDataProvider";
import type { MarketRepository } from "@/data/marketRepository";
import { AnalysisRequestError, type AnalysisSource } from "@/data/analysisGateway";
import { adviserCouncilFixture, adviserUsageFixture, decisionFixture } from "@/data/__tests__/decision.fixture";
import type { Decision } from "@/domain/models";

const idleRepository = {
  loadWatchlist: async () => {
    throw new Error("not used in this test");
  },
  loadSnapshot: async () => {
    throw new Error("not used in this test");
  },
} as unknown as MarketRepository;


jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ symbol: "NVDA" }),
  useRouter: () => ({ back: jest.fn() }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
});

/**
 * The device session gate every real-mode render now passes through to reach
 * its own analysis client. `pairingRequired={false}` with no credential store
 * settles it to "unpaired" (a null token) without touching the Keychain --
 * harmless here because the tests below inject their own `analysis` source
 * and never let the screen build one from runtime config.
 */
function Wrapper({ children }: PropsWithChildren) {
  return (
    <AppStateProvider>
      <DeviceSessionProvider pairingRequired={false}>
        {children}
      </DeviceSessionProvider>
    </AppStateProvider>
  );
}

function deferredAnalysis() {
  const calls: {
    symbol: string;
    horizon: string;
    signal: AbortSignal | undefined;
    resolve: (value: Decision) => void;
    reject: (error: unknown) => void;
  }[] = [];
  const analysis: AnalysisSource = {
    getDecision: (symbol, horizon, signal) =>
      new Promise<Decision>((resolve, reject) => {
        calls.push({ symbol, horizon, signal, resolve, reject });
      }),
  };
  return { analysis, calls };
}

function availableCouncilDecision(): Decision {
  return {
    ...decisionFixture(),
    adviserCouncil: adviserCouncilFixture(),
    adviserUsage: adviserUsageFixture(),
  } as unknown as Decision;
}

it("keeps the objective layer frozen while selecting deterministic long and short plans", async () => {
  const view = await render(
    <Wrapper>
      <MarketDataProvider development initialDemoMode repository={idleRepository}>
      <AdvisersScreen />
    </MarketDataProvider>
    </Wrapper>,
  );

  await waitFor(() => expect(view.getByTestId("adviser-council")).toBeTruthy());

  expect(view.getAllByText("演示数据 · 非实时行情")).toHaveLength(1);
  expect(view.getByText("客观算法结论")).toBeTruthy();
  expect(view.getByText("72")).toBeTruthy();
  expect(view.getByText("置信度 68%")).toBeTruthy();
  expect(view.getByText(/公开投资理念的风格模拟/)).toBeTruthy();
  expect(view.getByText("按需调用 · 当前激活 4 / 13 · 节省 Token")).toBeTruthy();

  expect(view.getByRole("button", { name: "做多方案，已选择" })).toBeTruthy();
  expect(view.getByRole("button", { name: "均衡风险偏好，已选择" })).toBeTruthy();
  expect(view.getByTestId("trade-plan-card")).toBeTruthy();
  expect(view.getByText("回踩分批限价")).toBeTruthy();
  expect(view.getByText("$139.80 – $141.20")).toBeTruthy();
  expect(view.getByText("1.25× / 上限 1.50×")).toBeTruthy();
  // The服务端 caps the adviser panel at ±3 points; showing a wider bound here
  // would tell the user advisers carry more weight than they actually do.
  expect(view.getByText("顾问软因子 / 上限 3.0")).toBeTruthy();
  expect(view.queryByText(/上限 10/)).toBeNull();

  await fireEvent.press(view.getByRole("button", { name: "查看方案引用" }));
  expect(view.getByText("NVDA 方案证据")).toBeTruthy();
  expect(view.getByText("演示：NVDA 机构持仓与财报快照")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "关闭NVDA 方案证据" }));

  await fireEvent.press(view.getByRole("button", { name: "做空方案" }));
  await fireEvent.press(view.getByRole("button", { name: "进取风险偏好" }));

  expect(view.getByText("突破限价")).toBeTruthy();
  expect(view.getByText("$143.40 – $144.60")).toBeTruthy();
  expect(view.getByText("可借券：是")).toBeTruthy();
  expect(view.getByText("预计借券费 0.35%")).toBeTruthy();
  expect(view.getAllByText(/无限损失风险/).length).toBeGreaterThan(0);

  expect(view.getByText("72")).toBeTruthy();
  expect(view.getByText("置信度 68%")).toBeTruthy();
  expect(view.getByText("仅供分析与建议，不连接券商，不会自动下单。")).toBeTruthy();
  expect(view.queryByText(/提交订单|自动交易|一键下单/)).toBeNull();
});

function renderRealMode(analysis: AnalysisSource) {
  return render(
    <Wrapper>
      <MarketDataProvider development repository={idleRepository}>
        <AdvisersScreen analysis={analysis} />
      </MarketDataProvider>
    </Wrapper>,
  );
}

it("real mode shows an explicit invoke flow before anything is requested, not the demo grid", async () => {
  const { analysis, calls } = deferredAnalysis();
  const view = await renderRealMode(analysis);

  await waitFor(() => expect(view.getByTestId("adviser-council")).toBeTruthy());
  expect(view.getByTestId("adviser-council-not-requested")).toBeTruthy();
  expect(view.getByText(/预计花费约 US\$0\.10/)).toBeTruthy();
  expect(view.getByText(/最长可能等待 5 分钟/)).toBeTruthy();
  expect(view.getByText(/本周期满编 7 席/)).toBeTruthy();
  expect(view.queryByTestId("adviser-council-not-deployed")).toBeNull();
  expect(view.queryByTestId("analysis-not-connected")).toBeNull();
  expect(view.queryByTestId("adviser-council-available")).toBeNull();
  // Nothing about the demo's named-investor grid or its fixture score leaks
  // into real mode.
  expect(view.queryByText("演示数据 · 非实时行情")).toBeNull();
  expect(calls).toHaveLength(0);
});

it("makes exactly one network call per tap, ignores a repeat tap while loading, and aborts on unmount", async () => {
  const { analysis, calls } = deferredAnalysis();
  const view = await renderRealMode(analysis);

  await waitFor(() => expect(view.getByTestId("adviser-council-invoke")).toBeTruthy());
  await fireEvent.press(view.getByTestId("adviser-council-invoke"));

  expect(calls).toHaveLength(1);
  expect(calls[0]?.symbol).toBe("NVDA");
  expect(calls[0]?.horizon).toBe("short");
  expect(view.getByTestId("adviser-council-loading")).toBeTruthy();

  await fireEvent.press(view.getByTestId("adviser-council-invoke"));
  // The button disables itself while loading, so a repeat tap adds no call.
  expect(calls).toHaveLength(1);

  await view.unmount();
  expect(calls[0]?.signal?.aborted).toBe(true);
});

it("renders the available council with per-framework quotes, the score fold and usage cost", async () => {
  const { analysis, calls } = deferredAnalysis();
  const view = await renderRealMode(analysis);

  await waitFor(() => expect(view.getByTestId("adviser-council-invoke")).toBeTruthy());
  await fireEvent.press(view.getByTestId("adviser-council-invoke"));
  await act(async () => {
    calls[0]?.resolve(availableCouncilDecision());
  });

  await waitFor(() => expect(view.getByTestId("adviser-council-available")).toBeTruthy());
  expect(calls).toHaveLength(1);
  expect(view.getByText("各框架都读到同一条指引上调。")).toBeTruthy();
  expect(view.getByText("基线 72.5 → 调整后 75.5（+3.0）")).toBeTruthy();
  expect(view.queryByTestId("adviser-council-blocked")).toBeNull();
  expect(view.getByText("技术结构框架")).toBeTruthy();
  expect(view.getByText("立场：bullish")).toBeTruthy();
  expect(view.getByText("已知盲区：对基本面突变无感。")).toBeTruthy();
  expect(view.getByText("指引上调支持偏多的解读。")).toBeTruthy();
  // Verbatim, quoted -- not paraphrased.
  expect(view.getByText("「raises full-year revenue guidance」")).toBeTruthy();
  expect(view.getByText(/实测花费 US\$0\.1630/)).toBeTruthy();
  expect(view.getByText(/claude-opus-4-8/)).toBeTruthy();
  expect(view.getByText(/风格模型，非本人意见/)).toBeTruthy();
});

it("shows the hard-gate banner instead of a fold when a hard gate voided the council", async () => {
  const { analysis, calls } = deferredAnalysis();
  const view = await renderRealMode(analysis);
  const gatedCouncil = adviserCouncilFixture();

  await waitFor(() => expect(view.getByTestId("adviser-council-invoke")).toBeTruthy());
  await fireEvent.press(view.getByTestId("adviser-council-invoke"));
  await act(async () => {
    calls[0]?.resolve({
      ...decisionFixture(),
      adviserCouncil: {
        ...gatedCouncil,
        value: {
          ...gatedCouncil.value,
          scoreAdjustment: 0,
          adjustedScore: 72.5,
          blockedBy: ["liquidity_gate"],
          actionable: false,
        },
      },
      adviserUsage: adviserUsageFixture(),
    } as unknown as Decision);
  });

  await waitFor(() => expect(view.getByTestId("adviser-council-blocked")).toBeTruthy());
  expect(view.getByText("liquidity_gate")).toBeTruthy();
  expect(view.getByText("基线 72.5 → 调整后 72.5（+0.0）")).toBeTruthy();
});

it("shows the not-deployed copy when a live response carries no council field at all", async () => {
  const { analysis, calls } = deferredAnalysis();
  const view = await renderRealMode(analysis);

  await waitFor(() => expect(view.getByTestId("adviser-council-invoke")).toBeTruthy());
  await fireEvent.press(view.getByTestId("adviser-council-invoke"));
  await act(async () => {
    calls[0]?.resolve({
      ...decisionFixture(),
      adviserCouncil: null,
    } as unknown as Decision);
  });

  await waitFor(() =>
    expect(view.getByTestId("adviser-council-not-deployed")).toBeTruthy(),
  );
  expect(view.queryByTestId("adviser-council-invoke")).toBeNull();
});

it("keeps a model that was asked and could not answer distinct from one nobody asked", async () => {
  const { analysis, calls } = deferredAnalysis();
  const view = await renderRealMode(analysis);

  await waitFor(() => expect(view.getByTestId("adviser-council-invoke")).toBeTruthy());
  await fireEvent.press(view.getByTestId("adviser-council-invoke"));
  await act(async () => {
    calls[0]?.resolve({
      ...decisionFixture(),
      adviserCouncil: {
        status: "unavailable",
        reason: "模型这次超时了，没有给出可用意见。",
        value: null,
      },
    } as unknown as Decision);
  });

  await waitFor(() =>
    expect(view.getByTestId("adviser-council-model-unavailable")).toBeTruthy(),
  );
  expect(view.getByText("模型这次超时了，没有给出可用意见。")).toBeTruthy();
  expect(view.queryByTestId("adviser-council-request-failed")).toBeNull();
  expect(view.queryByTestId("adviser-council-not-requested")).toBeNull();
});

it("shows the request-failed copy, distinct from a model refusal, when the call itself never lands", async () => {
  const { analysis, calls } = deferredAnalysis();
  const view = await renderRealMode(analysis);

  await waitFor(() => expect(view.getByTestId("adviser-council-invoke")).toBeTruthy());
  await fireEvent.press(view.getByTestId("adviser-council-invoke"));
  await act(async () => {
    calls[0]?.reject(new AnalysisRequestError("timeout", "analysis request timed out"));
  });

  await waitFor(() =>
    expect(view.getByTestId("adviser-council-request-failed")).toBeTruthy(),
  );
  expect(view.queryByTestId("adviser-council-model-unavailable")).toBeNull();
});
