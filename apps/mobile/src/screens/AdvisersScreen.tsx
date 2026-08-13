import { useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { AdviserSummary } from "@/components/advisers/AdviserSummary";
import { PlanSelector } from "@/components/advisers/PlanSelector";
import { TradePlanCard } from "@/components/advisers/TradePlanCard";
import {
  DashboardDetailSheet,
  type DetailSection,
} from "@/components/dashboard/DashboardDetailSheet";
import { AnalysisNotConnected } from "@/components/ui/AnalysisNotConnected";
import { Screen } from "@/components/ui/Screen";
import { ADVISER_SCORE_CAP } from "@/domain/models";
import type { PlanSide, RiskPreference } from "@/domain/models";
import { evaluateTradePlanSafety, selectTradePlan } from "@/domain/plan";
import { fixtureRepository } from "@/fixtures/repository";
import { useAppState } from "@/state/AppStateProvider";
import { useMarketDataMode } from "@/state/MarketDataProvider";
import { colors, radius, spacing } from "@/theme/tokens";

export function AdvisersScreen() {
  const params = useLocalSearchParams<{ symbol?: string | string[] }>();
  const router = useRouter();
  const { horizon, savePlan } = useAppState();
  const { demoMode } = useMarketDataMode();
  const symbolParam = Array.isArray(params.symbol) ? params.symbol[0] : params.symbol;
  const symbol = (symbolParam ?? "NVDA").toUpperCase();
  const stock = fixtureRepository.getStock(symbol, horizon);
  const advisers = fixtureRepository.getAdvisers(symbol, horizon);
  const plans = fixtureRepository.getTradePlans(symbol, horizon);
  const [side, setSide] = useState<PlanSide>("long");
  const [preference, setPreference] = useState<RiskPreference>("balanced");
  const [showAll, setShowAll] = useState(false);
  const [researchRequested, setResearchRequested] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showPlanEvidence, setShowPlanEvidence] = useState(false);
  const selectedPlan = selectTradePlan(plans, side, preference, horizon);
  const activeAdvisers = advisers.filter(({ active }) => active);
  const bullishCount = activeAdvisers.filter(({ direction }) => direction === "bullish").length;
  const bearishCount = activeAdvisers.filter(({ direction }) => direction === "bearish").length;
  const neutralCount = activeAdvisers.length - bullishCount - bearishCount;
  const adviserAdjustment = Math.max(
    -ADVISER_SCORE_CAP,
    Math.min(
      ADVISER_SCORE_CAP,
      activeAdvisers.reduce(
        (sum, adviser) =>
          sum +
          (adviser.direction === "bullish"
            ? adviser.confidence
            : adviser.direction === "bearish"
              ? -adviser.confidence
              : 0),
        0,
      ) /
        Math.max(activeAdvisers.length, 1) *
        10,
    ),
  );
  const planSafety = evaluateTradePlanSafety(
    selectedPlan,
    stock.forecast.predictedAt,
  );
  const planEvidenceSections: DetailSection[] = [
    {
      label: "方案生成",
      body: `${selectedPlan.methodVersion} · ${formatAsOf(selectedPlan.generatedAt)} · ${selectedPlan.horizon}`,
    },
    {
      label: "安全门",
      body: planSafety.allowed ? "通过当前演示安全门" : planSafety.reasons.join(" · "),
    },
    {
      label: "时序边界",
      body: `证据与借券状态都不得晚于 ${formatAsOf(stock.forecast.predictedAt)}`,
    },
  ];

  if (!demoMode) {
    return (
      <Screen hideGlobalHeader style={styles.screen}>
        <AnalysisNotConnected
          missing="缺的是大模型凭据：顾问层要读环境变量 ANTHROPIC_API_KEY，目前没有配置，分析服务也还没有暴露逐位顾问的路由。个股结论里的顾问调整项因此固定为 0，不是顾问看空。"
          surface="顾问会诊"
        />
      </Screen>
    );
  }

  return (
    <Screen hideGlobalHeader style={styles.screen}>
      <View style={styles.header}>
        <Pressable
          accessibilityLabel="返回股票详情"
          accessibilityRole="button"
          onPress={() => router.back()}
          style={({ pressed }) => [styles.back, pressed && styles.pressed]}>
          <Text style={styles.backText}>返回</Text>
        </Pressable>
        <View style={styles.headerCopy}>
          <Text style={styles.headerTitle}>{symbol} · 顾问会诊</Text>
          <Text style={styles.headerMeta}>
            证据截止 {formatAsOf(stock.forecast.predictedAt)}
          </Text>
        </View>
        <View style={styles.back} />
      </View>
      <Text style={styles.demo}>演示数据 · 非实时行情</Text>

      <View style={styles.objective}>
        <View style={styles.objectiveTop}>
          <View style={styles.objectiveCopy}>
            <Text style={styles.objectiveEyebrow}>客观算法结论</Text>
            <Text style={styles.objectiveTitle}>{stock.conclusion}</Text>
            <Text style={styles.objectiveBody}>
              基础分 {stock.baseScore} · 市场上下文 {stock.marketContext.scoreAdjustment} ·
              偏好不会改变方向与置信度
            </Text>
          </View>
          <View style={styles.score}>
            <Text style={styles.scoreValue}>{selectedPlan.objectiveScore}</Text>
            <Text style={styles.scoreLabel}>客观分</Text>
          </View>
        </View>
        <View style={styles.objectiveFooter}>
          <Text style={styles.confidence}>
            {`置信度 ${Math.round(selectedPlan.confidence * 100)}%`}
          </Text>
          <View style={styles.softFactor}>
            <Text style={styles.softValue}>
              {adviserAdjustment > 0 ? "+" : ""}
              {adviserAdjustment.toFixed(1)}
            </Text>
            <Text style={styles.softLabel}>
              顾问软因子 / 上限 {ADVISER_SCORE_CAP.toFixed(1)}
            </Text>
          </View>
        </View>
      </View>

      <PlanSelector
        onPreferenceChange={setPreference}
        onSideChange={setSide}
        preference={preference}
        side={side}
      />

      <View style={styles.council} testID="adviser-council">
        <View style={styles.sectionHeader}>
          <View>
            <Text style={styles.sectionTitle}>十三风格顾问委员会</Text>
            <Text style={styles.sectionMeta}>
              按需调用 · 当前激活 4 / 13 · 节省 Token
            </Text>
          </View>
          <Pressable
            accessibilityLabel={showAll ? "收起全部顾问" : "查看全部 13 位顾问"}
            accessibilityRole="button"
            onPress={() => setShowAll((current) => !current)}
            style={styles.textButton}>
            <Text style={styles.textButtonLabel}>{showAll ? "收起" : "全部 13 位"}</Text>
          </Pressable>
        </View>
        <Text style={styles.disclaimer}>
          以下为公开投资理念的风格模拟，不代表本人、背书或实时个人意见。
        </Text>
        <View style={styles.adviserGrid}>
          {(showAll ? advisers : activeAdvisers).map((opinion) => (
            <AdviserSummary key={opinion.id} opinion={opinion} />
          ))}
        </View>
      </View>

      <View style={styles.consensus}>
        <View style={styles.consensusHeader}>
          <Text style={styles.consensusTitle}>共识与最大分歧</Text>
          <Text style={styles.consensusCount}>
            偏多 {bullishCount} · 反对 {bearishCount} · 中性 {neutralCount}
          </Text>
        </View>
        <Text style={styles.consensusBody}>
          当前激活风格在同一 {symbol} 证据包上形成分歧；反对意见优先检查估值拥挤、事件链和失效条件。
        </Text>
        <View style={styles.missing}>
          <Text style={styles.missingTitle}>缺失证据</Text>
          <Text style={styles.missingBody}>
            下一周期真实量价确认、最新公司与政策文本，以及当前可用的借券与流动性状态。
          </Text>
          <Pressable
            accessibilityLabel="申请补充调查"
            accessibilityRole="button"
            onPress={() => setResearchRequested(true)}
            style={({ pressed }) => [styles.researchButton, pressed && styles.pressed]}>
            <Text style={styles.researchText}>申请补充调查</Text>
          </Pressable>
          {researchRequested ? (
            <Text style={styles.researchState}>
              已加入本地调查清单；演示阶段不会发送外部请求。
            </Text>
          ) : null}
        </View>
      </View>

      <View style={styles.planHeading}>
        <Text style={styles.sectionTitle}>
          {side === "long" ? "做多" : "做空"} ·{" "}
          {preference === "conservative"
            ? "稳健"
            : preference === "balanced"
              ? "均衡"
              : "进取"}{" "}
          分析方案
        </Text>
        <Text style={styles.sectionMeta}>演示数字 · 正式版由确定性风险引擎重算</Text>
      </View>
      <TradePlanCard plan={selectedPlan} />
      <Pressable
        accessibilityLabel="查看方案引用"
        accessibilityRole="button"
        onPress={() => setShowPlanEvidence(true)}
        style={({ pressed }) => [styles.evidenceButton, pressed && styles.pressed]}>
        <Text style={styles.evidenceButtonText}>
          查看方案引用 · {selectedPlan.citationIds.length} 条
        </Text>
      </Pressable>
      {!planSafety.allowed ? (
        <Text style={styles.blocked}>
          当前方案未通过安全门：{planSafety.reasons.join(" · ")}
        </Text>
      ) : null}
      <Pressable
        accessibilityLabel={
          planSafety.allowed
            ? "保存分析方案到复盘"
            : "保存分析方案到复盘，当前不可用"
        }
        accessibilityRole="button"
        accessibilityState={{ disabled: !planSafety.allowed }}
        disabled={!planSafety.allowed}
        onPress={() => {
          savePlan(selectedPlan);
          setSaved(true);
        }}
        style={({ pressed }) => [
          styles.saveButton,
          !planSafety.allowed && styles.saveDisabled,
          pressed && styles.pressed,
        ]}>
        <Text style={styles.saveText}>{saved ? "已保存到复盘" : "保存分析方案"}</Text>
      </Pressable>
      <Text style={styles.safety}>
        仅分析与建议，不连接券商，不会自动下单。
      </Text>
      <DashboardDetailSheet
        citations={fixtureRepository.getCitations(selectedPlan.citationIds)}
        onClose={() => setShowPlanEvidence(false)}
        sections={planEvidenceSections}
        title={`${symbol} 方案证据`}
        visible={showPlanEvidence}
      />
    </Screen>
  );
}

function formatAsOf(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", {
        hour12: false,
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
}

const styles = StyleSheet.create({
  screen: { gap: spacing.md, paddingTop: spacing.xs },
  header: { alignItems: "center", flexDirection: "row" },
  back: { alignItems: "center", justifyContent: "center", minHeight: 44, minWidth: 44 },
  backText: { color: colors.blue, fontSize: 12, fontWeight: "900" },
  headerCopy: { alignItems: "center", flex: 1 },
  headerTitle: { color: colors.ink, fontSize: 17, fontWeight: "900" },
  headerMeta: { color: colors.muted, fontSize: 9, marginTop: 2 },
  demo: { alignSelf: "center", color: colors.muted, fontSize: 9, fontWeight: "600" },
  objective: { backgroundColor: colors.navy, borderRadius: radius.lg, gap: spacing.md, padding: spacing.md },
  objectiveTop: { alignItems: "center", flexDirection: "row", gap: spacing.md },
  objectiveCopy: { flex: 1 },
  objectiveEyebrow: { color: colors.blueBright, fontSize: 9, fontWeight: "900" },
  objectiveTitle: { color: colors.card, fontSize: 18, fontWeight: "900", lineHeight: 23, marginTop: 3 },
  objectiveBody: { color: colors.navyMuted, fontSize: 9, lineHeight: 14, marginTop: 4 },
  score: { alignItems: "center", borderColor: colors.navyLine, borderRadius: radius.round, borderWidth: 3, height: 62, justifyContent: "center", width: 62 },
  scoreValue: { color: colors.card, fontSize: 21, fontVariant: ["tabular-nums"], fontWeight: "900" },
  scoreLabel: { color: colors.navyMuted, fontSize: 8, fontWeight: "800" },
  objectiveFooter: { alignItems: "center", borderTopColor: colors.navyLine, borderTopWidth: 1, flexDirection: "row", justifyContent: "space-between", paddingTop: spacing.sm },
  confidence: { color: colors.green, fontSize: 11, fontVariant: ["tabular-nums"], fontWeight: "900" },
  softFactor: { alignItems: "flex-end" },
  softValue: { color: colors.blueBright, fontSize: 13, fontWeight: "900" },
  softLabel: { color: colors.navyMuted, fontSize: 8, fontWeight: "600" },
  council: { gap: spacing.sm },
  sectionHeader: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  sectionTitle: { color: colors.ink, fontSize: 15, fontWeight: "900" },
  sectionMeta: { color: colors.muted, fontSize: 9, fontWeight: "600", marginTop: 2 },
  textButton: { alignItems: "center", justifyContent: "center", minHeight: 44, paddingLeft: spacing.md },
  textButtonLabel: { color: colors.blue, fontSize: 10, fontWeight: "900" },
  disclaimer: { backgroundColor: colors.blueSoft, borderRadius: radius.sm, color: "#3B5F91", fontSize: 9, lineHeight: 14, overflow: "hidden", padding: spacing.sm },
  adviserGrid: { gap: spacing.sm },
  consensus: { backgroundColor: colors.card, borderColor: colors.line, borderRadius: radius.lg, borderWidth: StyleSheet.hairlineWidth, gap: spacing.sm, padding: spacing.md },
  consensusHeader: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  consensusTitle: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  consensusCount: { color: colors.green, fontSize: 9, fontWeight: "900" },
  consensusBody: { color: colors.muted, fontSize: 10, lineHeight: 15 },
  missing: { backgroundColor: colors.amberSoft, borderRadius: radius.md, gap: 4, padding: spacing.sm },
  missingTitle: { color: "#704B05", fontSize: 10, fontWeight: "900" },
  missingBody: { color: "#8B5C08", fontSize: 9, lineHeight: 14 },
  researchButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.card, borderRadius: radius.sm, justifyContent: "center", minHeight: 44, paddingHorizontal: spacing.md },
  researchText: { color: colors.ink, fontSize: 10, fontWeight: "900" },
  researchState: { color: "#8B5C08", fontSize: 9, fontWeight: "700" },
  planHeading: { gap: 2 },
  evidenceButton: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: "center",
    minHeight: 44,
  },
  evidenceButtonText: { color: colors.blue, fontSize: 10, fontWeight: "900" },
  blocked: { color: colors.red, fontSize: 9, fontWeight: "800", lineHeight: 14 },
  saveButton: { alignItems: "center", backgroundColor: colors.blue, borderRadius: radius.md, justifyContent: "center", minHeight: 48 },
  saveDisabled: { backgroundColor: colors.muted, opacity: 0.55 },
  saveText: { color: colors.card, fontSize: 12, fontWeight: "900" },
  safety: { color: colors.muted, fontSize: 10, fontWeight: "800", textAlign: "center" },
  pressed: { opacity: 0.68 },
});
