import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import { StyleSheet, useColorScheme } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import { DeviceSessionGate } from "@/components/ui/DeviceSessionGate";
import { AppStateProvider } from "@/state/AppStateProvider";
import { DeviceSessionProvider } from "@/state/DeviceSessionProvider";
import { PairedMarketData } from "@/state/PairedMarketData";

export default function RootLayout() {
  const colorScheme = useColorScheme();

  return (
    // Chart pinch and drag are gesture-handler gestures, and those only reach
    // the native recogniser from inside this root view.
    <GestureHandlerRootView style={styles.root}>
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
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({ root: { flex: 1 } });
