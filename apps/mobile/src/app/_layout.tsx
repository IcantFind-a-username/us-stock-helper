import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import { useColorScheme } from "react-native";

import { fixtureRepository } from "@/fixtures/repository";
import { AppStateProvider } from "@/state/AppStateProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";

export default function RootLayout() {
  const colorScheme = useColorScheme();

  return (
    <ThemeProvider value={colorScheme === "dark" ? DarkTheme : DefaultTheme}>
      <AppStateProvider>
        <MarketDataProvider
          demoWatchlist={fixtureRepository.getDashboard("short").watchlist}>
          <Stack>
            <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
            <Stack.Screen name="stocks/[symbol]/index" options={{ headerShown: false }} />
            <Stack.Screen name="stocks/[symbol]/chart" options={{ headerShown: false }} />
            <Stack.Screen name="stocks/[symbol]/advisers" options={{ headerShown: false }} />
          </Stack>
        </MarketDataProvider>
      </AppStateProvider>
    </ThemeProvider>
  );
}
