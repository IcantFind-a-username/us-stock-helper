import { Tabs } from "expo-router";
import { SymbolView } from "expo-symbols";

import { layout } from "@/theme/tokens";

export const tabRoutes = [
  ["index", "首页", "home-outline"],
  ["discover", "发现", "scan-outline"],
  ["alerts", "提醒", "flash-outline"],
  ["journal", "复盘", "document-text-outline"],
  ["agent", "Agent", "sparkles-outline"],
] as const;

const tabSymbols = {
  "home-outline": { android: "home", ios: "house", web: "home" },
  "scan-outline": { android: "search", ios: "magnifyingglass", web: "search" },
  "flash-outline": { android: "bolt", ios: "bolt", web: "bolt" },
  "document-text-outline": { android: "description", ios: "doc.text", web: "description" },
  "sparkles-outline": { android: "auto_awesome", ios: "sparkles", web: "auto_awesome" },
} as const;

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: "#4285FF",
        tabBarInactiveTintColor: "#8A96A8",
        tabBarLabelStyle: {
          fontSize: 10,
          fontWeight: "700",
        },
        tabBarStyle: {
          backgroundColor: "rgba(255,255,255,0.98)",
          borderTopColor: "rgba(18,33,55,0.07)",
          height: layout.tabBarHeight,
          paddingBottom: 8,
          paddingTop: 6,
        },
      }}>
      {tabRoutes.map(([name, title, icon]) => (
        <Tabs.Screen
          key={name}
          name={name}
          options={{
            title,
            tabBarIcon: ({ color, size }) => (
              <SymbolView name={tabSymbols[icon]} size={size} tintColor={color} />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}
