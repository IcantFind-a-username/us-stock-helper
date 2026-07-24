import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import { useColorScheme } from "react-native";

import { AppStateProvider } from "@/state/AppStateProvider";

export default function RootLayout() {
  const colorScheme = useColorScheme();

  return (
    <ThemeProvider value={colorScheme === "dark" ? DarkTheme : DefaultTheme}>
      <AppStateProvider>
        <Stack>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="stocks/[symbol]/index" options={{ headerShown: false }} />
          <Stack.Screen name="stocks/[symbol]/chart" options={{ headerShown: false }} />
          <Stack.Screen name="stocks/[symbol]/advisers" options={{ headerShown: false }} />
        </Stack>
      </AppStateProvider>
    </ThemeProvider>
  );
}
