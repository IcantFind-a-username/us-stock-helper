import { beforeEach, expect, it, jest } from "@jest/globals";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { StyleSheet } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { DashboardScreen } from "../DashboardScreen";
import { AppStateProvider } from "@/state/AppStateProvider";

const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  mockPush.mockClear();
});

async function renderDashboard() {
  return render(
    <AppStateProvider>
      <DashboardScreen />
    </AppStateProvider>,
  );
}

it("shows the short-first conclusion, objective dashboard context, and accessible actions", async () => {
  const view = await renderDashboard();

  await waitFor(() => expect(view.getByText("演示数据 · 非实时行情")).toBeTruthy());
  expect(view.queryByLabelText("市场证据")).toBeNull();

  expect(view.getByText("短线 · 0–5日")).toBeTruthy();
  expect(view.getByText("谨慎偏多")).toBeTruthy();
  expect(view.getByText("市场评分 61")).toBeTruthy();
  expect(view.getByText("置信度 67%")).toBeTruthy();
  expect(view.getByText("新闻与社交情绪改善，但市场广度和期限结构仍要求确认。")).toBeTruthy();
  expect(view.getByText("轻仓，等待量价与广度确认")).toBeTruthy();
  expect(view.getByText("今日建议")).toBeTruthy();
  expect(view.getByText("最强反证")).toBeTruthy();
  expect(view.getAllByText("失效条件").length).toBeGreaterThanOrEqual(1);
  expect(view.getByText("美股盘中 · 演示状态")).toBeTruthy();
  expect(view.getByText("数据新鲜")).toBeTruthy();
  expect(view.getByTestId("watchlist-grid")).toBeTruthy();

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
  expect(view.getAllByText(/新鲜度：/).length).toBeGreaterThanOrEqual(9);
  expect(view.getByText("新鲜度：存在冲突")).toBeTruthy();
  expect(view.getByRole("button", { name: /查看 地缘政治 证据.*新鲜度 存在冲突/ })).toBeTruthy();

  const evidenceAction = view.getByRole("button", { name: "查看市场证据" });
  expect(evidenceAction.props.accessibilityHint).toContain("引用");
  expect(StyleSheet.flatten(evidenceAction.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(evidenceAction);
  expect(view.getByText("市场证据")).toBeTruthy();
  expect(view.getByText("演示：短线新闻与社交情绪快照")).toBeTruthy();
  expect(view.getAllByText("演示").length).toBeGreaterThanOrEqual(7);
  await fireEvent.press(view.getByText("波段 · 1–8周"));
  await waitFor(() => expect(view.getByText("波段环境")).toBeTruthy());
  expect(view.queryByText("演示：短线新闻与社交情绪快照")).toBeNull();
  expect(view.getByText("数据存在冲突")).toBeTruthy();
  const healthEvidence = view.getByRole("button", { name: /查看数据健康与市场时段证据.*存在冲突/ });
  expect(StyleSheet.flatten(healthEvidence.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(healthEvidence);
  expect(view.getByText("波段数据健康与市场时段证据")).toBeTruthy();
  expect(view.getByText("演示：波段数据健康与市场时段快照")).toBeTruthy();
});

it("switches all fixture-backed horizon views independently", async () => {
  const view = await renderDashboard();

  await waitFor(() => expect(view.getByText("谨慎偏多")).toBeTruthy());
  await fireEvent.press(view.getByText("波段 · 1–8周"));
  await waitFor(() => expect(view.getByText("波段环境")).toBeTruthy());
  expect(view.getByText("市场评分 56")).toBeTruthy();
  expect(view.getByText("分批，优先顺势回撤")).toBeTruthy();
  expect(view.getByText("NVDA 进入波段趋势验证区")).toBeTruthy();
  expect(view.getByText("评分 64")).toBeTruthy();

  await fireEvent.press(view.getByText("中长线 · 2–24月"));
  await waitFor(() => expect(view.getByText("中长期质量优先")).toBeTruthy());
  expect(view.getByText("市场评分 68")).toBeTruthy();
  expect(view.getByText("耐心，质量优先并容忍波动")).toBeTruthy();
  expect(view.getByText("NVDA 长期盈利质量待估值确认")).toBeTruthy();
  expect(view.getByText("评分 81")).toBeTruthy();
});

it("renders the priority alert and watchlist as compact dashboard surfaces", async () => {
  const view = await renderDashboard();

  await waitFor(() => expect(view.getByText("NVDA 接近量价确认区")).toBeTruthy());

  const alert = view.getByTestId("priority-alert-card");
  expect(alert).toBeTruthy();
  expect(view.getByText("证据 5 · 反证 2 · 新鲜")).toBeTruthy();
  expect(view.queryByText("来源覆盖：盘中报价、期权与量价演示快照")).toBeNull();
  expect(view.queryByText("顾问有限调整 +2 · 不能独立触发")).toBeNull();
  expect(view.queryByText("收盘跌破 136.40")).toBeNull();

  expect(view.getByTestId("watchlist-grid")).toBeTruthy();
  expect(view.queryByTestId("watchlist-scroll")).toBeNull();
  expect(view.getAllByTestId("watchlist-quote")).toHaveLength(3);
});

it("routes alert, quotes, and both long/short candidates while disclosing their evidence", async () => {
  const view = await renderDashboard();

  await waitFor(() => expect(view.getByText("NVDA 接近量价确认区")).toBeTruthy());

  expect(view.getByText("证据 5 · 反证 2 · 新鲜")).toBeTruthy();
  expect(view.queryByText("顾问有限调整 +2 · 不能独立触发")).toBeNull();
  expect(view.queryByText("来源覆盖：盘中报价、期权与量价演示快照")).toBeNull();
  expect(view.getByText("我的关注")).toBeTruthy();
  expect(view.getByText("量价待确认")).toBeTruthy();
  expect(view.getByText("做多 · 非对称上行")).toBeTruthy();
  expect(view.getByText("做空 · 常规")).toBeTruthy();
  expect(view.getByText("达到行动研究门槛")).toBeTruthy();
  expect(view.getByText("观察池")).toBeTruthy();
  expect(view.getByText("风险升高")).toBeTruthy();
  expect(view.getAllByText("最强反例").length).toBeGreaterThanOrEqual(3);
  expect(view.getAllByText("失效条件").length).toBeGreaterThanOrEqual(4);

  const alert = view.getByRole("button", { name: /查看 NVDA 提醒详情：NVDA 接近量价确认区/ });
  expect(StyleSheet.flatten(alert.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(alert);
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/stocks/[symbol]", params: { symbol: "NVDA" } });

  await fireEvent.press(view.getByRole("button", { name: /查看 TSLA 行情详情.*下跌/ }));
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/stocks/[symbol]", params: { symbol: "TSLA" } });

  await fireEvent.press(view.getByRole("button", { name: /查看 TSLA 候选详情.*做空.*观察池/ }));
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/stocks/[symbol]", params: { symbol: "TSLA" } });

  const driver = view.getByRole("button", { name: /新闻与社交情绪.*评分.*新鲜度/ });
  expect(StyleSheet.flatten(driver.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(driver);
  expect(view.getByText("新闻与社交情绪证据")).toBeTruthy();
  expect(view.getByText("演示：短线新闻与社交情绪快照")).toBeTruthy();

  const alertEvidence = view.getByRole("button", { name: "查看 NVDA 提醒依据" });
  expect(StyleSheet.flatten(alertEvidence.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(alertEvidence);
  expect(view.getByText("NVDA 提醒证据")).toBeTruthy();
  expect(view.getByText("演示：短线 NVDA 量价确认快照")).toBeTruthy();

  const candidateEvidence = view.getByRole("button", { name: /TSLA 候选证据.*做空.*观察池/ });
  expect(StyleSheet.flatten(candidateEvidence.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(candidateEvidence);
  expect(view.getByText("TSLA 候选证据")).toBeTruthy();
  expect(view.getByText("演示：TSLA 短线交付预期快照")).toBeTruthy();

  const quote = view.getByRole("button", { name: /TSLA 行情详情.*\$318\.20.*下跌.*事件波动高/ });
  expect(StyleSheet.flatten(quote.props.style).minHeight).toBeGreaterThanOrEqual(44);
});
