import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import type { ReactElement } from "react";

import { AppStateProvider } from "@/state/AppStateProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";
import {
  createMarketRepository,
  MarketDataError,
  type MarketRepository,
} from "@/data/marketRepository";
import {
  AnalysisRequestError,
  type AnalysisSource,
} from "@/data/analysisGateway";
import { decisionFixture } from "@/data/__tests__/decision.fixture";
import {
  marketBriefFixture,
  marketBriefUnavailableFixture,
} from "@/data/__tests__/marketBrief.fixture";
import type { Decision, MarketBrief } from "@/domain/models";
import { DeviceSessionProvider } from "@/state/DeviceSessionProvider";

import { AdvisersScreen } from "../AdvisersScreen";
import { AgentScreen } from "../AgentScreen";
import { AlertsScreen } from "../AlertsScreen";
import { DashboardScreen } from "../DashboardScreen";
import { DiscoverScreen } from "../DiscoverScreen";

const mockPush = jest.fn();
const mockBack = jest.fn();

jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ symbol: "NVDA" }),
  useRouter: () => ({ back: mockBack, push: mockPush }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  mockPush.mockClear();
});

// A real repository over sources that refuse: the discover screen now reads
// the watchlist, so a bare source object would fail on repository-only methods.
const idleRepository: MarketRepository = createMarketRepository({
  loadWatchlist: async () => {
    throw new MarketDataError("configuration", "not used in these tests");
  },
  loadSnapshot: async () => {
    throw new MarketDataError("configuration", "not used in these tests");
  },
});

async function renderScreen(screen: ReactElement, demoMode: boolean) {
  return render(
    <AppStateProvider>
      <MarketDataProvider
        development
        initialDemoMode={demoMode}
        repository={idleRepository}>
        {screen}
      </MarketDataProvider>
    </AppStateProvider>,
  );
}

// 顾问 is deliberately absent from this table: since it gained an explicit
// invoke flow, its real-mode surface is not the blanket "analysis-not-
// connected" shape every other screen here still has -- it is exercised in
// its own describe block below instead.
const SCREENS: { name: string; element: ReactElement; demoText: RegExp }[] = [
  { name: "发现", element: <DiscoverScreen />, demoText: /NVDA · NVIDIA/ },
  {
    name: "提醒",
    element: <AlertsScreen />,
    demoText: /NVDA 接近量价确认区/,
  },
  { name: "Agent", element: <AgentScreen />, demoText: /为什么短线不追高？/ },
];

describe.each(SCREENS)("$name 屏幕的演示门控", ({ element, demoText }) => {
  it("在真实模式下不渲染任何演示分析内容", async () => {
    const view = await renderScreen(element, false);

    await waitFor(() =>
      expect(view.getByTestId("analysis-not-connected")).toBeTruthy(),
    );
    expect(view.queryByText(demoText)).toBeNull();
  });

  it("在显式开启的演示模式下仍然展示演示内容", async () => {
    const view = await renderScreen(element, true);

    await waitFor(() => expect(view.getAllByText(demoText).length).toBeGreaterThan(0));
    expect(view.queryByTestId("analysis-not-connected")).toBeNull();
  });
});

// Each of these screens is blocked on something different. They shared one
// sentence before, and that sentence blamed an analysis service that has since
// shipped — so the guard is that the reasons stay distinct and concrete. 顾问
// is absent here for the same reason it is absent from SCREENS above.
const BLOCKERS: { name: string; element: ReactElement; reason: RegExp }[] = [
  { name: "发现", element: <DiscoverScreen />, reason: /全市场扫描服务/ },
  { name: "提醒", element: <AlertsScreen />, reason: /提醒服务本身/ },
  { name: "Agent", element: <AgentScreen />, reason: /ANTHROPIC_API_KEY/ },
];

describe.each(BLOCKERS)("$name 占位文案", ({ element, reason }) => {
  it("说明真正缺的是什么，而不是笼统地说分析没上线", async () => {
    const view = await renderScreen(element, false);

    await waitFor(() =>
      expect(view.getByTestId("analysis-not-connected")).toHaveTextContent(
        reason,
      ),
    );
    expect(view.queryByText(/真实分析服务上线前/)).toBeNull();
  });
});

// 顾问's real mode is no longer a single blanket refusal: `GET
// /decision?adviser=true` is deployed and invocable now (b05de28/0495488,
// 4170859), so the screen offers an explicit, cost-and-duration-labelled
// invoke flow instead of assuming the whole feature is missing. The generic
// SCREENS/BLOCKERS tables above cannot express that three-state shape
// (idle-before-tap / live-and-rendered / genuinely-not-deployed), so it gets
// its own block, wrapped in the DeviceSessionProvider its own analysis
// client construction now depends on.
async function renderAdvisers(demoMode: boolean, analysis?: AnalysisSource) {
  return render(
    <AppStateProvider>
      <DeviceSessionProvider pairingRequired={false}>
        <MarketDataProvider
          development
          initialDemoMode={demoMode}
          repository={idleRepository}>
          <AdvisersScreen analysis={analysis} />
        </MarketDataProvider>
      </DeviceSessionProvider>
    </AppStateProvider>,
  );
}

describe("顾问 屏幕的演示门控", () => {
  it("演示模式下展示演示内容，不出现真实委员会的邀请流程", async () => {
    const view = await renderAdvisers(true);

    await waitFor(() => expect(view.getByText("客观算法结论")).toBeTruthy());
    expect(view.queryByTestId("analysis-not-connected")).toBeNull();
    expect(view.queryByTestId("adviser-council-not-requested")).toBeNull();
  });

  it("真实模式下点击之前展示邀请流程，不渲染任何演示分析内容，也不是笼统的未接入", async () => {
    const view = await renderAdvisers(false);

    await waitFor(() =>
      expect(view.getByTestId("adviser-council-not-requested")).toBeTruthy(),
    );
    expect(view.queryByText("客观算法结论")).toBeNull();
    expect(view.queryByTestId("analysis-not-connected")).toBeNull();
  });

  it("真实模式下服务端确实没有携带委员会字段时，具体说明缺的是什么", async () => {
    const view = await renderAdvisers(false, {
      getDecision: async () =>
        ({ ...decisionFixture(), adviserCouncil: null }) as unknown as Decision,
    });

    await waitFor(() =>
      expect(view.getByTestId("adviser-council-invoke")).toBeTruthy(),
    );
    await fireEvent.press(view.getByTestId("adviser-council-invoke"));

    await waitFor(() =>
      expect(
        view.getByTestId("adviser-council-not-deployed"),
      ).toHaveTextContent(
        /部署的分析服务版本比这台手机认识的委员会解析更旧|委员会层尚未在服务端配置/,
      ),
    );
    expect(view.queryByText(/真实分析服务上线前/)).toBeNull();
  });
});

// The dashboard does not fit the single `analysis-not-connected` shape above:
// real mode is not one blocked surface but a mix -- a served market brief, an
// honest per-symbol watchlist, and two still-missing services (alerts,
// candidates) that each name what they are waiting on. `GET /market-brief`
// (799d6c4) and its decoder (cf3c66e) are both real now, so this is what the
// Dashboard does with them.
function briefOnlyAnalysis(
  getMarketBrief: () => Promise<MarketBrief>,
): AnalysisSource {
  return {
    getDecision: async () => {
      throw new AnalysisRequestError(
        "route-unsupported",
        "not used in these tests",
      );
    },
    getMarketBrief,
  };
}

async function renderDashboard(analysis: AnalysisSource, demoMode: boolean) {
  return render(
    <AppStateProvider>
      <MarketDataProvider
        analysis={analysis}
        development
        initialDemoMode={demoMode}
        repository={idleRepository}>
        <DashboardScreen />
      </MarketDataProvider>
    </AppStateProvider>,
  );
}

describe("Dashboard 屏幕的市场简报", () => {
  it("真实模式下渲染简报的结论、情绪打分、不确定性与驱动覆盖，不出现任何演示字符串", async () => {
    const view = await renderDashboard(
      briefOnlyAnalysis(async () => marketBriefFixture()),
      false,
    );

    await waitFor(() =>
      expect(view.getByTestId("market-brief-card")).toBeTruthy(),
    );
    expect(view.getByText("偏多")).toBeTruthy();
    expect(view.getByText(/情绪打分\s*\+0\.42/)).toBeTruthy();
    expect(view.getByText("独立来源不足")).toBeTruthy();
    expect(view.getByText("新闻与社交情绪")).toBeTruthy();
    expect(view.getByText("市场广度")).toBeTruthy();
    expect(
      view.getByText("大盘涨跌家数、新高新低等广度数据源尚未接入。"),
    ).toBeTruthy();
    expect(view.getByText("数据新鲜")).toBeTruthy();

    // Zero fixture strings: the demo hero and its placeholder predecessor must
    // both be structurally absent, not merely unmatched by coincidence.
    expect(view.queryByTestId("market-regime-hero")).toBeNull();
    expect(view.queryByText("谨慎偏多")).toBeNull();
    // The exact demo-status marker, not a loose substring match: the
    // watchlist's own "未配置" copy legitimately mentions "演示数据" while
    // explaining that it will *not* fall back to it, and that honest sentence
    // must not be mistaken for the marker this assertion actually guards.
    expect(view.queryByText("演示数据 · 非实时行情")).toBeNull();
    expect(view.queryByText("演示数据 · 非实时")).toBeNull();
    expect(view.queryByText("市场分析尚未接入真实数据")).toBeNull();
  });

  it("保持优先提醒与候选条隐藏，并各自说明真正缺的服务", async () => {
    const view = await renderDashboard(
      briefOnlyAnalysis(async () => marketBriefFixture()),
      false,
    );

    await waitFor(() =>
      expect(view.getByTestId("market-brief-card")).toBeTruthy(),
    );
    expect(view.queryByTestId("priority-alert-card")).toBeNull();
    expect(view.queryByTestId("candidate-list")).toBeNull();
    expect(
      view.getByTestId("dashboard-priority-alert-not-connected"),
    ).toHaveTextContent(/提醒服务本身/);
    expect(
      view.getByTestId("dashboard-candidate-list-not-connected"),
    ).toHaveTextContent(/全市场扫描服务/);
  });

  it("打开数据健康横幅时展示简报自己的引用，而不是演示引用", async () => {
    const view = await renderDashboard(
      briefOnlyAnalysis(async () => marketBriefFixture()),
      false,
    );

    await waitFor(() =>
      expect(view.getByTestId("market-brief-card")).toBeTruthy(),
    );
    await fireEvent.press(
      view.getByRole("button", { name: /查看数据健康与市场时段证据/ }),
    );
    expect(
      view.getByText("NVIDIA raises full-year revenue guidance"),
    ).toBeTruthy();
    // The row renders "reuters · <time>" as one interpolated Text node, so the
    // publisher is matched as a substring rather than an exact string.
    expect(view.getByText(/reuters/)).toBeTruthy();
    expect(view.queryByText("演示数据 · 非实时行情")).toBeNull();
  });

  it("服务端判定简报不可用时，原样展示服务端的失败原因，绝不回退演示内容", async () => {
    const view = await renderDashboard(
      briefOnlyAnalysis(async () => marketBriefUnavailableFixture()),
      false,
    );

    await waitFor(() =>
      expect(view.getByTestId("market-brief-unavailable")).toBeTruthy(),
    );
    expect(
      view.getByTestId("market-brief-unavailable-reason"),
    ).toHaveTextContent(
      "本次未能读取任何情报源：sec-current-8-k（HTTP 503）、fred-releases（无法连接）",
    );
    expect(view.queryByTestId("market-brief-card")).toBeNull();
    expect(view.queryByText("谨慎偏多")).toBeNull();
    // The exact demo-status marker, not a loose substring match: the
    // watchlist's own "未配置" copy legitimately mentions "演示数据" while
    // explaining that it will *not* fall back to it, and that honest sentence
    // must not be mistaken for the marker this assertion actually guards.
    expect(view.queryByText("演示数据 · 非实时行情")).toBeNull();
    expect(view.queryByText("演示数据 · 非实时")).toBeNull();
  });

  it("请求本身失败时，展示传输层原因而不是服务端的业务原因或演示内容", async () => {
    const view = await renderDashboard(
      briefOnlyAnalysis(async () => {
        throw new AnalysisRequestError(
          "offline",
          "the analysis service is unavailable",
        );
      }),
      false,
    );

    await waitFor(() =>
      expect(view.getByTestId("market-brief-unavailable")).toBeTruthy(),
    );
    expect(view.getByText(/市场简报不可用 · 连不上/)).toBeTruthy();
    expect(view.queryByTestId("market-brief-card")).toBeNull();
    expect(view.queryByText("谨慎偏多")).toBeNull();
  });

  it("演示模式下从不请求市场简报，且演示市场英雄区保持字节不变", async () => {
    const getMarketBrief = jest.fn(async () => marketBriefFixture());
    const view = await renderDashboard(
      briefOnlyAnalysis(getMarketBrief),
      true,
    );

    await waitFor(() =>
      expect(view.getByTestId("market-regime-hero")).toBeTruthy(),
    );
    expect(view.queryByTestId("market-brief-card")).toBeNull();
    expect(view.queryByTestId("market-brief-unavailable")).toBeNull();
    expect(view.queryByTestId("market-brief-loading")).toBeNull();
    expect(getMarketBrief).not.toHaveBeenCalled();
  });

  it("真实模式下头部的时段与数据健康行由简报驱动", async () => {
    const view = await renderDashboard(
      briefOnlyAnalysis(async () => marketBriefFixture()),
      false,
    );

    await waitFor(() =>
      expect(
        view.getByTestId("dashboard-header-real-session"),
      ).toHaveTextContent("盘中 · 数据新鲜 · 更新 14:03"),
    );
  });
});
