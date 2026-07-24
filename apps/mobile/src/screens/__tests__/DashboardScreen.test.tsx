import { expect, it, jest } from "@jest/globals";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { DashboardScreen } from "../DashboardScreen";
import { AppStateProvider } from "@/state/AppStateProvider";

const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

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

  expect(view.getByText("短线 · 0–5日")).toBeTruthy();
  expect(view.getByText("谨慎偏多")).toBeTruthy();
  expect(view.getByText("市场评分 61")).toBeTruthy();
  expect(view.getByText("置信度 67%")).toBeTruthy();
  expect(view.getByText("今日建议")).toBeTruthy();
  expect(view.getByText("最强反证")).toBeTruthy();
  expect(view.getAllByText("失效条件").length).toBeGreaterThanOrEqual(1);
  expect(view.getByText("美股盘中 · 演示状态")).toBeTruthy();
  expect(view.getByText("数据新鲜")).toBeTruthy();

  [
    "新闻与整体情绪",
    "市场广度",
    "波动率与期权",
    "板块强弱",
    "利率与美元",
    "宏观、信用与能源",
    "流动性与相关性压力",
    "大盘趋势",
    "地缘政治",
  ].forEach((label) => {
    expect(view.getByText(label)).toBeTruthy();
  });
  expect(view.getAllByText(/新鲜度：/).length).toBeGreaterThanOrEqual(9);

  const evidenceAction = view.getByRole("button", { name: "查看市场证据" });
  expect(evidenceAction.props.accessibilityHint).toContain("引用");
  expect(StyleSheet.flatten(evidenceAction.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(evidenceAction);
  expect(view.getByText("演示：市场与成交结构快照")).toBeTruthy();
});

it("switches all fixture-backed horizon views independently", async () => {
  const view = await renderDashboard();

  await waitFor(() => expect(view.getByText("谨慎偏多")).toBeTruthy());
  await fireEvent.press(view.getByText("波段 · 1–8周"));
  await waitFor(() => expect(view.getByText("波段环境")).toBeTruthy());
  expect(view.getByText("市场评分 56")).toBeTruthy();

  await fireEvent.press(view.getByText("中长线 · 2–24月"));
  await waitFor(() => expect(view.getByText("中长期质量优先")).toBeTruthy());
  expect(view.getByText("市场评分 68")).toBeTruthy();
});

it("routes alert, quotes, and both long/short candidates while disclosing their evidence", async () => {
  const view = await renderDashboard();

  await waitFor(() => expect(view.getByText("NVDA 接近量价确认区")).toBeTruthy());

  expect(view.getByText("证据 5 · 反证 2")).toBeTruthy();
  expect(view.getByText("顾问调整 +2")).toBeTruthy();
  expect(view.getByText("moomoo watchlist · 演示占位")).toBeTruthy();
  expect(view.getByText("当前脉冲：量价待确认")).toBeTruthy();
  expect(view.getByText("做多 · 非对称上行")).toBeTruthy();
  expect(view.getByText("做空 · 常规")).toBeTruthy();
  expect(view.getByText("达到行动研究门槛")).toBeTruthy();
  expect(view.getByText("观察池")).toBeTruthy();
  expect(view.getByText("风险升高")).toBeTruthy();
  expect(view.getAllByText("最强反例").length).toBeGreaterThanOrEqual(3);
  expect(view.getAllByText("失效条件").length).toBeGreaterThanOrEqual(4);

  const alert = view.getByRole("button", { name: "查看 NVDA 提醒详情" });
  expect(StyleSheet.flatten(alert.props.style).minHeight).toBeGreaterThanOrEqual(44);
  await fireEvent.press(alert);
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/stocks/[symbol]", params: { symbol: "NVDA" } });

  await fireEvent.press(view.getByRole("button", { name: "查看 TSLA 行情详情" }));
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/stocks/[symbol]", params: { symbol: "TSLA" } });

  await fireEvent.press(view.getByRole("button", { name: "查看 TSLA 候选详情" }));
  expect(mockPush).toHaveBeenLastCalledWith({ pathname: "/stocks/[symbol]", params: { symbol: "TSLA" } });
});
