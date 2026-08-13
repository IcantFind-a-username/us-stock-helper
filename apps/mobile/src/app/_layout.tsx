import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import type { PropsWithChildren } from "react";
import { useColorScheme } from "react-native";

import { DeviceSessionGate } from "@/components/ui/DeviceSessionGate";
import { fixtureRepository } from "@/fixtures/repository";
import { AppStateProvider } from "@/state/AppStateProvider";
import {
  DeviceSessionProvider,
  useDeviceSession,
} from "@/state/DeviceSessionProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";

export default function RootLayout() {
  const colorScheme = useColorScheme();

  return (
    <ThemeProvider value={colorScheme === "dark" ? DarkTheme : DefaultTheme}>
      <AppStateProvider>
        <DeviceSessionProvider>
          <DeviceSessionGate>
            <PairedMarketData>
              <Stack>
                <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
                <Stack.Screen name="stocks/[symbol]/index" options={{ headerShown: false }} />
                <Stack.Screen name="stocks/[symbol]/chart" options={{ headerShown: false }} />
                <Stack.Screen name="stocks/[symbol]/advisers" options={{ headerShown: false }} />
              </Stack>
            </PairedMarketData>
          </DeviceSessionGate>
        </DeviceSessionProvider>
      </AppStateProvider>
    </ThemeProvider>
  );
}

/**
 * The market layer is mounted below the gate so that it is only ever built once
 * a token exists to build it with, and rebuilt if the pairing changes.
 */
function PairedMarketData({ children }: PropsWithChildren) {
  const { deviceToken } = useDeviceSession();

  return (
    <MarketDataProvider
      deviceToken={deviceToken}
      demoWatchlist={fixtureRepository.getDashboard("short").watchlist}>
      {children}
    </MarketDataProvider>
  );
}
