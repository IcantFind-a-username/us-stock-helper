import { useState } from "react";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { AgentComposer } from "@/components/agent/AgentComposer";
import { ConversationTurnCard } from "@/components/agent/ConversationTurnCard";
import {
  DashboardDetailSheet,
  type DetailSection,
} from "@/components/dashboard/DashboardDetailSheet";
import { Screen } from "@/components/ui/Screen";
import type { ConversationTurn } from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
import { colors, radius, spacing } from "@/theme/tokens";

export function AgentScreen() {
  const router = useRouter();
  const initialTurns = fixtureRepository.getConversation();
  const citationIds = [...new Set(initialTurns.flatMap((turn) => turn.citationIds))];
  const citations = fixtureRepository.getCitations(citationIds);
  const [turns, setTurns] = useState<ConversationTurn[]>(initialTurns);
  const [showEvidence, setShowEvidence] = useState(false);
  const [researchAcknowledged, setResearchAcknowledged] = useState(false);

  const answer = (prompt: string) => {
    const suffix = Date.now().toString();
    setTurns((current) => [
      ...current,
      {
        id: `user-${suffix}`,
        role: "user",
        text: prompt,
        citationIds: [],
      },
      {
        id: `assistant-${suffix}`,
        role: "assistant",
        citationIds,
        sections: [
          {
            title: "客观结论",
            body: "短线仍是谨慎偏多、等待确认；不会因为你的高回报偏好而上调客观置信度。",
          },
          {
            title: "证据",
            body: "【事实】演示持仓披露；【推断】量价和板块相对强势正在改善。",
          },
          {
            title: "最强反证",
            body: "市场广度有限、估值拥挤，出口限制消息仍缺少确定性确认。",
          },
          {
            title: "缺失信息与不确定性",
            body: "当前是本地确定性演示，没有调用实时行情、新闻服务或外部大模型。",
          },
          {
            title: "个性化风险场景",
            body: "高回报倾向只能改变建议仓位、止损与最大杠杆上限，不能改变事实、方向和置信度。",
          },
          {
            title: "引用",
            body: "查看本轮引用可核对发布时间、首次发现时间与证据类型。",
          },
        ],
      },
    ]);
  };

  const evidenceSections: DetailSection[] = [
    {
      label: "时序边界",
      body: "引用按首次发现时间冻结；分析时点之后才出现的资料不得进入本轮结论。",
    },
    {
      label: "当前状态",
      body: "确定性演示数据；未连接实时行情、新闻服务或外部模型。",
    },
  ];

  return (
    <Screen hideGlobalHeader style={styles.screen}>
      <View style={styles.header}>
        <View>
          <Text style={styles.demoLabel}>演示数据 · 非实时行情</Text>
          <Text style={styles.eyebrow}>事实优先 · 反迎合对话</Text>
          <Text style={styles.title}>Alpha Agent</Text>
        </View>
        <View style={styles.status}>
          <View style={styles.statusDot} />
          <Text style={styles.statusText}>本地演示</Text>
        </View>
      </View>

      <View style={styles.guardrail}>
        <Text style={styles.guardrailTitle}>客观结论与个性化场景分离</Text>
        <Text style={styles.guardrailBody}>
          先陈述事实、推断、反证与不确定性，再谈你的风险预算；不会为了迎合偏好改变市场判断。
        </Text>
      </View>

      <View style={styles.turns}>
        {turns.map((turn) => <ConversationTurnCard key={turn.id} turn={turn} />)}
      </View>

      <View style={styles.actions}>
        <Pressable
          accessibilityLabel="查看本轮引用"
          accessibilityRole="button"
          onPress={() => setShowEvidence(true)}
          style={({ pressed }) => [styles.secondary, pressed && styles.pressed]}>
          <Text style={styles.secondaryText}>查看本轮引用</Text>
        </Pressable>
        <Pressable
          accessibilityLabel="申请补充调查"
          accessibilityRole="button"
          onPress={() => setResearchAcknowledged(true)}
          style={({ pressed }) => [styles.secondary, pressed && styles.pressed]}>
          <Text style={styles.secondaryText}>申请补充调查</Text>
        </Pressable>
      </View>
      {researchAcknowledged ? (
        <Text style={styles.acknowledgement}>已创建演示调查请求；未向外部服务发送。</Text>
      ) : null}

      <AgentComposer onSubmit={answer} />

      <Pressable
        accessibilityLabel="进入 13 风格顾问会诊"
        accessibilityRole="button"
        onPress={() =>
          router.push({
            pathname: "/stocks/[symbol]/advisers",
            params: { symbol: "NVDA" },
          })
        }
        style={({ pressed }) => [styles.council, pressed && styles.pressed]}>
        <View style={styles.councilIcon}>
          <Text style={styles.councilIconText}>13</Text>
        </View>
        <View style={styles.councilCopy}>
          <Text style={styles.councilTitle}>13 风格顾问会诊</Text>
          <Text style={styles.councilBody}>
            在同一证据包上给出互补观点；作为有上限软因子，不能独立触发提醒。
          </Text>
          <Text style={styles.disclaimer}>公开理念的风格模拟，不代表真人背书。</Text>
        </View>
        <Text style={styles.chevron}>›</Text>
      </Pressable>

      <DashboardDetailSheet
        citations={citations}
        onClose={() => setShowEvidence(false)}
        sections={evidenceSections}
        title="本轮证据与引用"
        visible={showEvidence}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { gap: spacing.md, paddingTop: spacing.xs },
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  demoLabel: { color: colors.amber, fontSize: 8, fontWeight: "900" },
  eyebrow: { color: colors.muted, fontSize: 9, fontWeight: "800", marginTop: 2 },
  title: { color: colors.ink, fontSize: 23, fontWeight: "900", marginTop: spacing.xxs },
  status: { alignItems: "center", flexDirection: "row", gap: spacing.xs },
  statusDot: { backgroundColor: colors.green, borderRadius: 4, height: 7, width: 7 },
  statusText: { color: colors.muted, fontSize: 9, fontWeight: "900" },
  guardrail: {
    backgroundColor: colors.navy,
    borderRadius: radius.lg,
    gap: spacing.xs,
    padding: spacing.md,
  },
  guardrailTitle: { color: colors.card, fontSize: 15, fontWeight: "900" },
  guardrailBody: { color: colors.navyMuted, fontSize: 9, lineHeight: 14 },
  turns: { gap: spacing.sm },
  actions: { flexDirection: "row", gap: spacing.sm },
  secondary: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    flex: 1,
    justifyContent: "center",
    minHeight: 44,
  },
  secondaryText: { color: colors.blue, fontSize: 9, fontWeight: "900" },
  acknowledgement: { color: colors.green, fontSize: 9, fontWeight: "800" },
  council: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: spacing.sm,
    minHeight: 104,
    padding: spacing.md,
  },
  councilIcon: {
    alignItems: "center",
    backgroundColor: colors.purpleSoft,
    borderRadius: radius.md,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  councilIconText: { color: colors.purple, fontSize: 15, fontWeight: "900" },
  councilCopy: { flex: 1, gap: 3 },
  councilTitle: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  councilBody: { color: colors.muted, fontSize: 9, lineHeight: 13 },
  disclaimer: { color: colors.purple, fontSize: 8, fontWeight: "800" },
  chevron: { color: colors.muted, fontSize: 23, fontWeight: "700" },
  pressed: { opacity: 0.66 },
});
