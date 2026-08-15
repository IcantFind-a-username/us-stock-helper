import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import { StyleSheet, useColorScheme } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";

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
      {/*
       * DeviceSessionGate reads useSafeAreaInsets to keep its recovery pill
       * clear of the tab bar, and that hook throws without a SafeAreaProvider
       * ancestor — this is that ancestor, above every screen it and the rest
       * of the tree could otherwise reach for the same reason.
       */}
      <SafeAreaProvider>
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
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({ root: { flex: 1 } });
