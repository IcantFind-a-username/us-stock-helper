import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import { useColorScheme } from "react-native";

import { DeviceSessionGate } from "@/components/ui/DeviceSessionGate";
import { AppStateProvider } from "@/state/AppStateProvider";
import { DeviceSessionProvider } from "@/state/DeviceSessionProvider";
import { PairedMarketData } from "@/state/PairedMarketData";

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
