import { beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { AppStateProvider } from "@/state/AppStateProvider";

import { DiscoverScreen } from "../DiscoverScreen";

const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  mockPush.mockClear();
});

async function renderDiscover() {
  return render(
    <AppStateProvider>
      <DiscoverScreen />
    </AppStateProvider>,
  );
}

it("filters horizon candidates and preserves evidence-gated stock navigation", async () => {
  const view = await renderDiscover();

  await waitFor(() => expect(view.getByText("机会发现")).toBeTruthy());
  expect(view.getByText("NVDA · NVIDIA")).toBeTruthy();
  expect(view.getByText("TSLA · Tesla")).toBeTruthy();
  expect(view.getByText("PLTR · Palantir")).toBeTruthy();
  expect(view.getByText(/不对称候选不代表收益承诺/)).toBeTruthy();

  await fireEvent.press(view.getByRole("button", { name: "只看做空" }));
  expect(view.queryByText("NVDA · NVIDIA")).toBeNull();
  expect(view.getByText("TSLA · Tesla")).toBeTruthy();
  expect(view.queryByText("PLTR · Palantir")).toBeNull();

  await fireEvent.press(view.getByRole("button", { name: "全部方向" }));
  await fireEvent.press(view.getByRole("button", { name: "只看非对称上行" }));
  expect(view.getByText("NVDA · NVIDIA")).toBeTruthy();
  expect(view.queryByText("TSLA · Tesla")).toBeNull();

  await fireEvent.press(view.getByRole("button", { name: "查看 NVDA 候选依据" }));
  expect(view.getByText("NVDA 候选证据")).toBeTruthy();
  expect(view.getByText("最强反证")).toBeTruthy();
  expect(view.getByText("失效条件")).toBeTruthy();
  expect(view.getByText("演示：短线 NVDA 量价确认快照")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "关闭NVDA 候选证据" }));

  await fireEvent.press(view.getByRole("button", { name: "打开 NVDA 个股分析" }));
  expect(mockPush).toHaveBeenLastCalledWith({
    pathname: "/stocks/[symbol]",
    params: { symbol: "NVDA" },
  });
});
