import { Pressable, StyleSheet, Text, View } from "react-native";

import type { DataHealth } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

const healthCopy: Record<DataHealth, { label: string; detail: string; color: string; backgroundColor: string }> = {
  fresh: { label: "数据新鲜", detail: "已按最近可用数据更新", color: colors.green, backgroundColor: colors.greenSoft },
  stale: { label: "数据可能延迟", detail: "请先确认时效再判断", color: colors.amber, backgroundColor: colors.amberSoft },
  conflict: { label: "数据存在冲突", detail: "不同来源的结论不一致", color: colors.red, backgroundColor: colors.redSoft },
  insufficient: { label: "数据不足", detail: "当前证据不足以形成建议", color: colors.purple, backgroundColor: colors.purpleSoft },
};

type DataHealthBannerProps = {
  health: DataHealth;
  marketSession: string;
  evidenceTitle: string;
  citationIds: string[];
  onOpenEvidence(title: string, citationIds: string[]): void;
};

export function DataHealthBanner({ health, marketSession, evidenceTitle, citationIds, onOpenEvidence }: DataHealthBannerProps) {
  const copy = healthCopy[health];

  return (
    <View accessibilityRole="alert" style={[styles.banner, { backgroundColor: copy.backgroundColor }]}>
      <View style={styles.row}>
        <View style={styles.copy}>
          <Text style={[styles.label, { color: copy.color }]}>{copy.label}</Text>
          <Text style={styles.detail}>{copy.detail}</Text>
        </View>
        <View style={styles.sessionCopy}>
          <Text style={styles.marker}>演示</Text>
          <Text style={styles.session}>{marketSession}</Text>
        </View>
      </View>
      <Pressable
        accessibilityHint="打开数据健康与市场时段的演示引用"
        accessibilityLabel={`查看数据健康与市场时段证据：${copy.label}，${marketSession}`}
        accessibilityRole="button"
        onPress={() => onOpenEvidence(evidenceTitle, citationIds)}
        style={styles.evidenceButton}>
        <Text style={styles.evidenceText}>查看证据</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: { borderRadius: radius.md, gap: spacing.sm, padding: spacing.md },
  row: { alignItems: "center", flexDirection: "row", gap: spacing.md },
  copy: { flex: 1 },
  label: { fontSize: 13, fontWeight: "700" },
  detail: { color: colors.muted, fontSize: 12, marginTop: spacing.xs },
  sessionCopy: { alignItems: "flex-end", flexShrink: 1 },
  marker: { color: colors.amber, fontSize: 10, fontWeight: "800" },
  session: { color: colors.ink, fontSize: 12, fontWeight: "600", textAlign: "right" },
  evidenceButton: { alignItems: "center", backgroundColor: colors.card, borderRadius: radius.sm, justifyContent: "center", minHeight: 44, paddingHorizontal: spacing.md },
  evidenceText: { color: colors.blue, fontSize: 13, fontWeight: "800" },
});
