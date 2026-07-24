import { StyleSheet, Text, View } from "react-native";

import { DemoDataBadge } from "@/components/ui/DemoDataBadge";

export function TemporaryScreen({ title }: { title: string }) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>{title}</Text>
      <DemoDataBadge />
      <Text style={styles.description}>演示页面将在后续任务中完善。</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    flex: 1,
    justifyContent: "center",
    padding: 24,
  },
  description: {
    color: "#667085",
    marginTop: 8,
  },
  title: {
    color: "#101828",
    fontSize: 24,
    fontWeight: "700",
  },
});
