import { beforeEach, expect, it, jest } from "@jest/globals";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { StyleSheet } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { DashboardScreen } from "../DashboardScreen";
import {
  createMarketRepository,
  MarketDataError,
  type MarketDataSource,
  type MarketRepository,
} from "@/data/marketRepository";
import { fixtureRepository } from "@/fixtures/repository";
import { AppStateProvider } from "@/state/AppStateProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";

const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  mockPush.mockClear();
});

function repositoryWithWatchlist(
  loadWatchlist: MarketDataSource["loadWatchlist"],
) {
  return createMarketRepository({
    loadSnapshot: async () => {
      throw new MarketDataError("configuration", "snapshot not configured");
    },
    loadWatchlist,
  });
}

async function renderDashboard({
  repository,
  demoMode = true,
  development = true,
}: {
  repository?: MarketRepository;
  demoMode?: boolean;
  development?: boolean;
} = {}) {
  const demoWatchlist = fixtureRepository.getDashboard("short").watchlist;
  return render(
    <AppStateProvider>
      <MarketDataProvider
        demoWatchlist={demoWatchlist}
        development={development}
        initialDemoMode={demoMode}
        {...(repository ? { repository } : {})}>
        <DashboardScreen />
      </MarketDataProvider>
    </AppStateProvider>,
  );
}

it("shows the short-first conclusion, objective dashboard context, and accessible actions", async () => {
  const view = await renderDashboard();

  await waitFor(() => expect(view.getByText("谨慎偏多")).toBeTruthy());
  expect(view.getByLabelText("市场评分 61")).toBeTruthy();
  expect(view.getByText("今日建议")).toBeTruthy();
  expect(view.getByText("需要关注")).toBeTruthy();
  expect(view.getByText("我的关注")).toBeTruthy();
  expect(view.getByText("潜力候选")).toBeTruthy();
  expect(view.queryByText("最强反证")).toBeNull();

  expect(view.getByText("短线 · 0–5日")).toBeTruthy();
  expect(view.getByText("谨慎偏多")).toBeTruthy();
  expect(view.getByText("新闻与社交情绪改善，但市场广度和期限结构仍要求确认。")).toBeTruthy();
  expect(view.getByLabelText("自选行情，演示")).toBeTruthy();
  expect(view.getByTestId("watchlist-grid")).toBeTruthy();

  const evidenceAction = view.getByRole("button", { name: "查看完整依据" });
  expect(StyleSheet.flatten(evidenceAction.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(evidenceAction);
  expect(view.getByText("市场完整依据")).toBeTruthy();
  expect(view.getByText("最强反证")).toBeTruthy();
  expect(view.getByText("失效条件")).toBeTruthy();
  expect(view.getByText("轻仓，等待量价与广度确认")).toBeTruthy();

  [
    "新闻与社交情绪",
    "市场广度",
    "波动率、期权与期限结构",
    "板块强弱",
    "利率、收益率曲线与美元",
    "宏观、信用、能源与商品",
    "流动性与相关性压力",
    "大盘趋势",
    "地缘政治",
  ].forEach((label) => {
    expect(view.getByText(label)).toBeTruthy();
  });
  expect(view.getByText("演示：短线新闻与社交情绪快照")).toBeTruthy();

  await fireEvent.press(view.getByRole("button", { name: "关闭市场完整依据" }));
  await fireEvent.press(view.getByText("波段 · 1–8周"));
  await waitFor(() => expect(view.getByText("波段环境")).toBeTruthy());
  expect(view.queryByText("演示：短线新闻与社交情绪快照")).toBeNull();
  expect(view.getByText(/美股盘中 · 演示状态 · 数据冲突/)).toBeTruthy();
});

it("switches all fixture-backed horizon views independently", async () => {
  const view = await renderDashboard();

  await waitFor(() => expect(view.getByText("谨慎偏多")).toBeTruthy());
  await fireEvent.press(view.getByText("波段 · 1–8周"));
  await waitFor(() => expect(view.getByText("波段环境")).toBeTruthy());
  expect(view.getByLabelText("市场评分 56")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "查看完整依据" }));
  expect(view.getByText("分批，优先顺势回撤")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "关闭市场完整依据" }));
  expect(view.getByText("进入波段趋势验证区")).toBeTruthy();
  expect(view.queryByText("NVDA 进入波段趋势验证区")).toBeNull();
  expect(view.getByText("64")).toBeTruthy();

  await fireEvent.press(view.getByText("中长线 · 2–24月"));
  await waitFor(() => expect(view.getByText("中长期质量优先")).toBeTruthy());
  expect(view.getByLabelText("市场评分 68")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "查看完整依据" }));
  expect(view.getByText("耐心，质量优先并容忍波动")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "关闭市场完整依据" }));
  expect(view.getByText("长期盈利质量待估值确认")).toBeTruthy();
  expect(view.queryByText("NVDA 长期盈利质量待估值确认")).toBeNull();
  expect(view.getByText("81")).toBeTruthy();
});

it("renders the priority alert and watchlist as compact dashboard surfaces", async () => {
  const view = await renderDashboard();

  await waitFor(() => expect(view.getByText("接近量价确认区")).toBeTruthy());
  expect(view.queryByText("NVDA 接近量价确认区")).toBeNull();

  const alert = view.getByTestId("priority-alert-card");
  expect(alert).toBeTruthy();
  expect(view.getByText("证据 5 · 反证 2 · 新鲜")).toBeTruthy();
  expect(view.queryByText("来源覆盖：盘中报价、期权与量价演示快照")).toBeNull();
  expect(view.queryByText("顾问有限调整 +2 · 不能独立触发")).toBeNull();
  expect(view.queryByText("收盘跌破 136.40")).toBeNull();

  expect(view.getByTestId("watchlist-grid")).toBeTruthy();
  expect(view.queryByTestId("watchlist-scroll")).toBeNull();
  expect(view.getAllByTestId("watchlist-quote")).toHaveLength(3);

  const sectionAction = view.getByRole("button", { name: "来自 moomoo ›" });
  expect(StyleSheet.flatten(sectionAction.props.style).minHeight).toBeGreaterThanOrEqual(44);
  expect(StyleSheet.flatten(sectionAction.props.style).minWidth).toBeGreaterThanOrEqual(44);
});

it("routes alert, quotes, and both long/short candidates while disclosing their evidence", async () => {
  const view = await renderDashboard();

  await waitFor(() => expect(view.getByText("接近量价确认区")).toBeTruthy());
  expect(view.queryByText("NVDA 接近量价确认区")).toBeNull();

  expect(view.getByText("证据 5 · 反证 2 · 新鲜")).toBeTruthy();
  expect(view.queryByText("顾问有限调整 +2 · 不能独立触发")).toBeNull();
  expect(view.queryByText("来源覆盖：盘中报价、期权与量价演示快照")).toBeNull();
  expect(view.getByText("我的关注")).toBeTruthy();
  expect(view.getByText("量价待确认")).toBeTruthy();
  expect(view.getByText("NVDA · 达到行动研究门槛")).toBeTruthy();
  expect(view.getByText("TSLA · 观察池")).toBeTruthy();
  expect(view.queryByText("最强反例")).toBeNull();
  expect(view.queryByText("失效条件")).toBeNull();

  const alert = view.getByRole("button", { name: /查看 NVDA 提醒详情：NVDA 接近量价确认区/ });
  expect(StyleSheet.flatten(alert.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(alert);
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/stocks/[symbol]", params: { symbol: "NVDA" } });

  await fireEvent.press(view.getByRole("button", { name: /查看 TSLA 行情详情.*下跌/ }));
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/stocks/[symbol]", params: { symbol: "TSLA" } });

  const candidate = view.getByRole("button", { name: "查看 TSLA 候选详情" });
  expect(StyleSheet.flatten(candidate.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(candidate);
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/stocks/[symbol]", params: { symbol: "TSLA" } });

  await fireEvent.press(view.getByRole("button", { name: "查看完整依据" }));
  expect(view.getByText("新闻与社交情绪")).toBeTruthy();
  expect(view.getByText("演示：短线新闻与社交情绪快照")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "关闭市场完整依据" }));

  const alertEvidence = view.getByRole("button", { name: "查看 NVDA 提醒依据" });
  expect(StyleSheet.flatten(alertEvidence.props.style).minHeight).toBeGreaterThanOrEqual(44);
  expect(StyleSheet.flatten(alertEvidence.props.style).minWidth).toBeGreaterThanOrEqual(44);
  await fireEvent.press(alertEvidence);
  expect(view.getByText("NVDA 提醒依据")).toBeTruthy();
  expect(view.getByText("盘中报价、期权与量价演示快照")).toBeTruthy();
  expect(view.getByText("演示：短线 NVDA 量价确认快照")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "关闭NVDA 提醒依据" }));

  const candidateEvidence = view.getByRole("button", { name: "查看 TSLA 候选依据" });
  expect(StyleSheet.flatten(candidateEvidence.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(candidateEvidence);
  expect(view.getByText("TSLA 候选依据")).toBeTruthy();
  expect(view.getByText("最强反例")).toBeTruthy();
  expect(view.getByText("放量突破近期反弹高点并维持两日。")).toBeTruthy();
  expect(view.getByText("演示：TSLA 短线交付预期快照")).toBeTruthy();

  const quote = view.getByRole("button", { name: /TSLA 行情详情.*\$318\.20.*下跌.*事件波动高/ });
  expect(StyleSheet.flatten(quote.props.style).minHeight).toBeGreaterThanOrEqual(44);
});

it("turns Search and the moomoo source affordance into complete interactions", async () => {
  const view = await renderDashboard();

  await waitFor(() => expect(view.getByText("谨慎偏多")).toBeTruthy());

  await fireEvent.press(view.getByRole("button", { name: "搜索股票" }));
  expect(view.getByText("搜索关注标的")).toBeTruthy();
  const input = view.getByLabelText("搜索股票代码或名称");
  await fireEvent.changeText(input, "tesla");
  await fireEvent.press(view.getByRole("button", { name: "打开 TSLA Tesla" }));
  expect(mockPush).toHaveBeenLastCalledWith({
    pathname: "/stocks/[symbol]",
    params: { symbol: "TSLA" },
  });

  await fireEvent.press(view.getByRole("button", { name: "搜索股票" }));
  expect(view.getByRole("button", { name: "打开 NVDA NVIDIA" })).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "关闭股票搜索" }));

  await fireEvent.press(view.getByRole("button", { name: "来自 moomoo ›" }));
  expect(view.getByText("moomoo 数据来源")).toBeTruthy();
  expect(view.getByText(/开发者已显式开启/)).toBeTruthy();
  expect(view.getByText(/演示回退/)).toBeTruthy();
});

it("renders verified moomoo watchlist rows without fixture fallback", async () => {
  const repository = repositoryWithWatchlist(async () => ({
    source: "moomoo",
    asOf: "2026-07-25T15:59:50.000Z",
    quotes: [
      {
        symbol: "AAPL",
        price: 245.12,
        changePercent: 1.25,
        direction: "bullish",
        summary: "实时只读",
      },
      {
        symbol: "MSFT",
        price: 512.34,
        changePercent: -0.4,
        direction: "bearish",
        summary: "实时只读",
      },
    ],
  }));
  const view = await renderDashboard({ repository, demoMode: false });

  await waitFor(() => expect(view.getByText("实时行情")).toBeTruthy());
  expect(
    view.getByLabelText(
      "自选行情，实时，验证时间 2026-07-25T15:59:50.000Z",
    ),
  ).toBeTruthy();
  expect(view.getAllByTestId("watchlist-quote")).toHaveLength(2);
  expect(view.getByText("AAPL")).toBeTruthy();
  expect(view.getByText("MSFT")).toBeTruthy();
  expect(
    view.queryByRole("button", { name: /NVDA 行情详情.*143\.80/ }),
  ).toBeNull();
  expect(view.queryByText("演示数据 · 非实时")).toBeNull();
});

it("keeps verified rows and their original time when a refresh becomes stale", async () => {
  let requestCount = 0;
  const repository = repositoryWithWatchlist(async () => {
    requestCount += 1;
    if (requestCount > 1) {
      throw new MarketDataError("offline", "OpenD offline");
    }
    return {
      source: "moomoo",
      asOf: "2026-07-25T15:59:50.000Z",
      quotes: [
        {
          symbol: "AAPL",
          price: 245.12,
          changePercent: 1.25,
          direction: "bullish",
          summary: "实时只读",
        },
      ],
    };
  });
  const view = await renderDashboard({ repository, demoMode: false });

  await waitFor(() => expect(view.getByText("实时行情")).toBeTruthy());
  await fireEvent.press(view.getByRole("button", { name: "刷新行情" }));
  await waitFor(() => expect(view.getByText(/^行情已延迟/)).toBeTruthy());
  expect(
    view.getByLabelText(
      "自选行情，陈旧，原始时间 2026-07-25T15:59:50.000Z",
    ),
  ).toBeTruthy();
  expect(view.getByText("AAPL")).toBeTruthy();
  expect(view.getByText(/2026-07-25T15:59:50.000Z/)).toBeTruthy();
});

it("shows one actionable unavailable state with the error category", async () => {
  const repository = repositoryWithWatchlist(async () => {
    throw new MarketDataError("permission", "quote permission denied");
  });
  const view = await renderDashboard({ repository, demoMode: false });

  await waitFor(() =>
    expect(view.getByText("行情不可用 · permission")).toBeTruthy(),
  );
  expect(view.getByRole("button", { name: "重试行情" })).toBeTruthy();
  expect(view.queryByTestId("watchlist-grid")).toBeNull();
  expect(view.queryByTestId("watchlist-quote")).toBeNull();
});

it("shows login-required without rendering fallback rows", async () => {
  const repository = repositoryWithWatchlist(async () => {
    throw new MarketDataError("login-required", "login required");
  });
  const view = await renderDashboard({ repository, demoMode: false });

  await waitFor(() =>
    expect(view.getByText("行情不可用 · login-required")).toBeTruthy(),
  );
  expect(view.getByRole("button", { name: "重试行情" })).toBeTruthy();
  expect(view.queryByTestId("watchlist-grid")).toBeNull();
});

it("shows the explicit demo switch only to developers", async () => {
  const repository = repositoryWithWatchlist(async () => {
    throw new MarketDataError("offline", "OpenD offline");
  });
  const developerView = await renderDashboard({
    repository,
    demoMode: true,
    development: true,
  });
  expect(developerView.getByText("演示模式")).toBeTruthy();
  expect(developerView.getByText("演示数据 · 非实时")).toBeTruthy();
  await developerView.unmount();

  const productionView = await renderDashboard({
    repository,
    demoMode: false,
    development: false,
  });
  expect(productionView.queryByText("演示模式")).toBeNull();
  await waitFor(() =>
    expect(productionView.getByText("行情不可用 · offline")).toBeTruthy(),
  );
});
