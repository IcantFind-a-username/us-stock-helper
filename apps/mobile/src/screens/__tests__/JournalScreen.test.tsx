import { beforeEach, expect, it } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { AppStateProvider } from "@/state/AppStateProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";
import type { MarketRepository } from "@/data/marketRepository";

import { JournalScreen } from "../JournalScreen";

const idleRepository = {
  loadWatchlist: async () => {
    throw new Error("not used in these tests");
  },
  loadSnapshot: async () => {
    throw new Error("not used in these tests");
  },
} as unknown as MarketRepository;

beforeEach(async () => {
  await AsyncStorage.clear();
});

async function renderJournal(demoMode = false) {
  const view = await render(
    <AppStateProvider>
      <MarketDataProvider
        development
        initialDemoMode={demoMode}
        repository={idleRepository}>
        <JournalScreen />
      </MarketDataProvider>
    </AppStateProvider>,
  );
  await waitFor(() => expect(view.getByText("交易复盘")).toBeTruthy());
  return view;
}

it("keeps user execution history isolated and persists a validated local entry", async () => {
  const view = await renderJournal();

  expect(view.getByText("还没有保存的分析方案")).toBeTruthy();
  expect(view.getByText("还没有执行记录")).toBeTruthy();
  expect(view.getByText(/不会改变股票评分、方向或证据可信度/)).toBeTruthy();

  await fireEvent.press(view.getByRole("button", { name: "记录一笔执行" }));
  await fireEvent.press(view.getByRole("button", { name: "保存执行记录" }));
  expect(view.getByText("请输入股票代码")).toBeTruthy();
  expect(view.getByText("数量必须大于 0")).toBeTruthy();
  expect(view.getByText("成交价必须大于 0")).toBeTruthy();
  expect(view.getByText("盈亏必须是有效数字")).toBeTruthy();

  await fireEvent.changeText(view.getByLabelText("股票代码"), "nvda");
  await fireEvent.changeText(view.getByLabelText("成交数量"), "10");
  await fireEvent.changeText(view.getByLabelText("成交价格"), "140.25");
  await fireEvent.changeText(view.getByLabelText("本笔盈亏"), "120");
  await fireEvent.changeText(view.getByLabelText("复盘备注"), "按失效条件执行");
  await fireEvent.press(view.getByRole("button", { name: "保存执行记录" }));

  await waitFor(() => expect(view.getByText("NVDA · 做多")).toBeTruthy());
  expect(view.getAllByText("+$120.00")).toHaveLength(3);
  expect(view.getByText("按失效条件执行")).toBeTruthy();
  expect(view.queryByText("还没有执行记录")).toBeNull();

  const persisted = await AsyncStorage.getItem("us-stock-helper/journal-entries");
  expect(persisted).toContain('"symbol":"NVDA"');
});

it("does not call the reader's own trade log demo data when demo mode is off", async () => {
  const view = await renderJournal(false);

  // The journal holds facts the reader typed in. They are real in every mode,
  // and the badge used to claim otherwise on a build with demo mode disabled.
  expect(view.queryByText("演示数据 · 非实时行情")).toBeNull();
  expect(view.getByText("本地日志 · 客观性隔离")).toBeTruthy();
});

it("still marks the demo build so seeded numbers are never mistaken for real", async () => {
  const view = await renderJournal(true);

  expect(view.getByText("演示数据 · 非实时行情")).toBeTruthy();
});
