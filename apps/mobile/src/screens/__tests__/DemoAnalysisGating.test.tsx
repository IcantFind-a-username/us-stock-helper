import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { render, waitFor } from "@testing-library/react-native";
import type { ReactElement } from "react";

import { AppStateProvider } from "@/state/AppStateProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";
import type { MarketRepository } from "@/data/marketRepository";

import { AdvisersScreen } from "../AdvisersScreen";
import { AgentScreen } from "../AgentScreen";
import { AlertsScreen } from "../AlertsScreen";
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

const idleRepository = {
  loadWatchlist: async () => {
    throw new Error("not used in these tests");
  },
  loadSnapshot: async () => {
    throw new Error("not used in these tests");
  },
} as unknown as MarketRepository;

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

const SCREENS: { name: string; element: ReactElement; demoText: RegExp }[] = [
  { name: "发现", element: <DiscoverScreen />, demoText: /NVDA · NVIDIA/ },
  {
    name: "提醒",
    element: <AlertsScreen />,
    demoText: /NVDA 接近量价确认区/,
  },
  { name: "顾问", element: <AdvisersScreen />, demoText: /客观算法结论/ },
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
