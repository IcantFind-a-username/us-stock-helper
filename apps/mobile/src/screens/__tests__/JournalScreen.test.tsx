import { beforeEach, expect, it } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { AppStateProvider } from "@/state/AppStateProvider";

import { JournalScreen } from "../JournalScreen";

beforeEach(async () => {
  await AsyncStorage.clear();
});

async function renderJournal() {
  const view = await render(
    <AppStateProvider>
      <JournalScreen />
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
