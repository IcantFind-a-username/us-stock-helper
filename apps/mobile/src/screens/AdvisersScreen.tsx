import { useMemo, useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import { AdviserSummary } from "@/components/advisers/AdviserSummary";
import { PlanSelector } from "@/components/advisers/PlanSelector";
import { TradePlanCard } from "@/components/advisers/TradePlanCard";
import {
  DashboardDetailSheet,
  type DetailSection,
} from "@/components/dashboard/DashboardDetailSheet";
import { AnalysisNotConnected } from "@/components/ui/AnalysisNotConnected";
import { Screen } from "@/components/ui/Screen";
import { getAnalysisRuntimeConfig } from "@/config/runtimeConfig";
import { createAnalysisClient, type AnalysisSource } from "@/data/analysisGateway";
import { MarketDataError } from "@/data/marketRepository";
import { ADVISER_SCORE_CAP } from "@/domain/models";
import type {
  AdviserCitation,
  AdviserConclusion,
  AdviserUsage,
  CouncilFrameworkOpinion,
  DecisionAdviserCouncil,
  Horizon,
  PlanSide,
  RiskPreference,
} from "@/domain/models";
import { evaluateTradePlanSafety, selectTradePlan } from "@/domain/plan";
import { fixtureRepository } from "@/fixtures/repository";
import { useAdviserCouncil } from "@/hooks/useAdviserCouncil";
import { describeMarketError } from "@/i18n/marketErrorCopy";
import { useAppState } from "@/state/AppStateProvider";
import { useDeviceSession } from "@/state/DeviceSessionProvider";
import { useMarketDataMode } from "@/state/MarketDataProvider";
import { colors, radius, spacing } from "@/theme/tokens";

/**
 * How many of the thirteen frameworks `select_frameworks` actually convenes
 * for each horizon (services/adviser_llm/src/adviser_llm/frameworks.py):
 * every framework whose `suitable_horizons` include this one, in declaration
 * order. Shown as an expectation on the invoke button, not asserted against
 * the server's answer -- the server, not this map, is the source of truth
 * for who actually showed up.
 */
const COUNCIL_SEATS_BY_HORIZON: Record<Horizon, number> = {
  short: 7,
  swing: 12,
  long: 9,
};

/**
 * Builds the one client this screen's council call goes through.
 *
 * Deliberately independent of `MarketDataProvider`'s shared `analysis`
 * client: the council is a slow, opt-in, symbol-scoped call with no reason to
 * share that provider's context, and `createAnalysisClient` holds no state
 * that would make a second instance observably different from the first.
 */
function buildCouncilAnalysisSource(deviceToken: string | null): AnalysisSource {
  try {
    const config = getAnalysisRuntimeConfig();
    if (!config.apiUrl) {
      throw new Error("EXPO_PUBLIC_ANALYSIS_API_URL is not configured");
    }
    const token = deviceToken ?? config.authorizationToken;
    return createAnalysisClient({
      baseUrl: config.apiUrl,
      ...(token ? { authorizationToken: token } : {}),
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "invalid analysis configuration";
    return {
      getDecision: async () =>
        Promise.reject(new MarketDataError("configuration", message)),
    };
  }
}

/**
 * Demo-mode-only fixture bundle for a symbol/horizon. Real mode never calls
 * this -- the fixture repository only ships sample data for a handful of
 * symbols (NVDA, TSLA, PLTR), and a symbol outside that set must fall back to
 * a graceful state here rather than crash the screen.
 */
function loadDemoFixtures(symbol: string, horizon: Horizon) {
  try {
    return {
      stock: fixtureRepository.getStock(symbol, horizon),
      advisers: fixtureRepository.getAdvisers(symbol, horizon),
      plans: fixtureRepository.getTradePlans(symbol, horizon),
    };
  } catch {
    return null;
  }
}

export function AdvisersScreen({
  analysis: analysisOverride,
}: { analysis?: AnalysisSource | undefined } = {}) {
  const params = useLocalSearchParams<{ symbol?: string | string[] }>();
  const router = useRouter();
  const { horizon, savePlan } = useAppState();
  const { demoMode } = useMarketDataMode();
  const { deviceToken } = useDeviceSession();
  const symbolParam = Array.isArray(params.symbol) ? params.symbol[0] : params.symbol;
  const symbol = (symbolParam ?? "NVDA").toUpperCase();
  const councilAnalysis = useMemo(
    () => analysisOverride ?? buildCouncilAnalysisSource(deviceToken),
    [analysisOverride, deviceToken],
  );
  const council = useAdviserCouncil(councilAnalysis, symbol, horizon);
  const [side, setSide] = useState<PlanSide>("long");
  const [preference, setPreference] = useState<RiskPreference>("balanced");
  const [showAll, setShowAll] = useState(false);
  const [researchRequested, setResearchRequested] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showPlanEvidence, setShowPlanEvidence] = useState(false);

  if (!demoMode) {
    const block = council.data?.adviserCouncil ?? null;
    const usage = council.data?.adviserUsage ?? null;
    const notDeployed = council.status === "live" && block === null;
    const seatsExpected = COUNCIL_SEATS_BY_HORIZON[horizon];
    const buttonLabel =
      council.status === "loading"
        ? "顾问委员会正在生成…"
        : council.status === "live" && block?.status === "available"
          ? "重新生成顾问委员会意见"
          : "生成顾问委员会意见";

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
              {council.data
                ? `证据截止 ${formatAsOf(council.data.decisionCutoff)}`
                : `${horizon} 周期 · 十三风格顾问委员会`}
            </Text>
          </View>
          <View style={styles.back} />
        </View>

        {notDeployed ? (
          <AnalysisNotConnected
            missing="这次响应没有携带顾问委员会字段：部署的分析服务版本比这台手机认识的委员会解析更旧，或者委员会层尚未在服务端配置。个股结论里的顾问调整项因此固定为 0，这不是委员会看空，是它没有跑起来。"
            surface="顾问委员会"
            testID="adviser-council-not-deployed"
          />
        ) : (
          <View style={styles.council} testID="adviser-council">
            <Text style={styles.disclaimer}>
              风格模型，非本人意见：以下为公开投资理念的方法论模拟，不代表本人、背书或实时个人意见；受硬门否决，且幅度有上限。
            </Text>

            <Pressable
              accessibilityLabel={buttonLabel}
              accessibilityRole="button"
              accessibilityState={{ disabled: council.status === "loading" }}
              disabled={council.status === "loading"}
              onPress={council.request}
              style={({ pressed }) => [
                styles.inviteButton,
                council.status === "loading" && styles.inviteButtonLoading,
                pressed && styles.pressed,
              ]}
              testID="adviser-council-invoke">
              <Text style={styles.inviteButtonTitle}>{buttonLabel}</Text>
              <Text style={styles.inviteButtonMeta}>
                {`预计花费约 US$0.10 · 最长可能等待 5 分钟 · 每次点击只调用一次模型 · 本周期满编 ${seatsExpected} 席`}
              </Text>
            </Pressable>

            {council.status === "idle" ? (
              <View style={styles.notice} testID="adviser-council-not-requested">
                <Text style={styles.noticeTitle}>尚未请求委员会</Text>
                <Text style={styles.noticeBody}>
                  点击上方按钮，请求一次真实的十三风格顾问委员会分析；在此之前这里不会显示任何结论，也不会调用模型。
                </Text>
              </View>
            ) : council.status === "loading" ? (
              <View style={styles.notice} testID="adviser-council-loading">
                <Text style={styles.noticeTitle}>顾问委员会正在生成…</Text>
                <Text style={styles.noticeBody}>
                  最长可能等待 5 分钟；请勿重复点击，离开本页会放弃等待结果；已开始的会诊费用不会退回。
                </Text>
              </View>
            ) : council.status === "unavailable" ? (
              <View style={styles.notice} testID="adviser-council-request-failed">
                <Text style={styles.noticeTitle}>
                  {`本次未生成：${describeMarketError(council.error?.category ?? "offline").label}`}
                </Text>
                <Text style={styles.noticeBody}>
                  {describeMarketError(council.error?.category ?? "offline").body}
                </Text>
              </View>
            ) : block?.status === "not-requested" ? (
              <View
                style={styles.notice}
                testID="adviser-council-block-not-requested">
                <Text style={styles.noticeTitle}>本次未获得委员会意见</Text>
                <Text style={styles.noticeBody}>
                  {block.reason ?? "服务端没有说明原因。"}
                </Text>
              </View>
            ) : block?.status === "unavailable" ? (
              <View style={styles.notice} testID="adviser-council-model-unavailable">
                <Text style={styles.noticeTitle}>委员会不可用</Text>
                <Text style={styles.noticeBody}>
                  {block.reason ?? "模型这次没有给出可用的意见。"}
                </Text>
                <Text style={styles.noticeBody}>
                  这是模型调用失败，不是「没有观点」。
                </Text>
              </View>
            ) : block?.status === "available" && block.value ? (
              <CouncilResult usage={usage} value={block.value} />
            ) : null}
          </View>
        )}

        <View style={styles.pendingFeatures}>
          <Text style={styles.pendingTitle}>暂未接入真实数据的部分</Text>
          <Text style={styles.pendingBody}>
            客观算法结论、分析方案生成与安全门仍依赖尚未部署的确定性风险引擎，这里暂不展示；接上之前不会用演示内容顶替。
          </Text>
        </View>

        <Text style={styles.safety}>
          仅供分析与建议，不连接券商，不会自动下单。
        </Text>
      </Screen>
    );
  }

  const demoData = loadDemoFixtures(symbol, horizon);
  if (!demoData) {
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
          </View>
          <View style={styles.back} />
        </View>
        <Text style={styles.demo}>演示数据 · 非实时行情</Text>
        <View style={styles.notice} testID="adviser-demo-fixture-missing">
          <Text style={styles.noticeTitle}>演示模式仅包含 NVDA</Text>
          <Text style={styles.noticeBody}>
            当前演示数据没有覆盖 {symbol}；切换回 NVDA 查看完整演示，或切换到真实模式请求{" "}
            {symbol} 的顾问委员会。
          </Text>
        </View>
        <Text style={styles.safety}>
          仅供分析与建议，不连接券商，不会自动下单。
        </Text>
      </Screen>
    );
  }
  const { stock, advisers, plans } = demoData;
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
        仅供分析与建议，不连接券商，不会自动下单。
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

/**
 * The real council's answer: baseline vs. adjusted score (only ever rendered
 * when the block is `available` -- the fold has nothing to show otherwise),
 * the hard-gate ledger, every framework's stance and blind spot with its
 * quoted evidence, and what the call actually cost.
 */
function CouncilResult({
  usage,
  value,
}: {
  usage: AdviserUsage | null;
  value: DecisionAdviserCouncil;
}) {
  return (
    <View style={styles.result} testID="adviser-council-available">
      <Text style={styles.summary}>{value.summary}</Text>

      <View style={styles.scoreFold} testID="adviser-council-score-fold">
        <Text style={styles.scoreFoldText}>
          {`基线 ${value.baselineScore.toFixed(1)} → 调整后 ${value.adjustedScore.toFixed(1)}（${
            value.scoreAdjustment >= 0 ? "+" : ""
          }${value.scoreAdjustment.toFixed(1)}）`}
        </Text>
      </View>

      {value.blockedBy.length > 0 ? (
        <View style={styles.councilBlocked} testID="adviser-council-blocked">
          <Text style={styles.councilBlockedTitle}>硬门已拦截本次调整</Text>
          <Text style={styles.councilBlockedBody}>{value.blockedBy.join(" · ")}</Text>
        </View>
      ) : null}

      {value.opinions.map((opinion) => (
        <FrameworkOpinionCard key={opinion.frameworkId} opinion={opinion} />
      ))}

      <Text style={styles.councilDisclaimer}>{value.disclaimer}</Text>

      {usage ? (
        <Text style={styles.cost} testID="adviser-council-cost">
          {`本次模型调用 ${
            usage.inputTokens +
            usage.outputTokens +
            usage.cacheCreationInputTokens +
            usage.cacheReadInputTokens
          } tokens · 实测花费 US$${usage.costUsd.toFixed(4)}${
            usage.model === null ? "" : ` · ${usage.model}`
          }`}
        </Text>
      ) : null}
    </View>
  );
}

function FrameworkOpinionCard({ opinion }: { opinion: CouncilFrameworkOpinion }) {
  return (
    <View
      style={styles.frameworkCard}
      testID={`adviser-council-framework-${opinion.frameworkId}`}>
      <Text style={styles.frameworkName}>{opinion.displayName}</Text>
      <Text style={styles.frameworkStance}>{`立场：${opinion.stance}`}</Text>
      <Text style={styles.frameworkBlindSpot}>{`已知盲区：${opinion.blindSpot}`}</Text>
      {opinion.conclusions.map((conclusion, index) => (
        <ConclusionRow
          conclusion={conclusion}
          key={`${index}-${conclusion.statement}`}
        />
      ))}
    </View>
  );
}

function ConclusionRow({ conclusion }: { conclusion: AdviserConclusion }) {
  return (
    <View style={styles.conclusion}>
      <Text style={styles.conclusionStatement}>{conclusion.statement}</Text>
      <Text style={styles.conclusionConfidence}>
        {`模型自评置信度 ${conclusion.confidence}`}
      </Text>
      {[...conclusion.citations, ...conclusion.counterEvidence].map(
        (citation) => (
          <CitationChip citation={citation} key={citation.evidenceId} />
        ),
      )}
    </View>
  );
}

function CitationChip({ citation }: { citation: AdviserCitation }) {
  return (
    <Pressable
      accessibilityHint="在浏览器中打开被引用的原始报道"
      accessibilityLabel={`打开引用来源：${citation.publisher}`}
      accessibilityRole="link"
      onPress={() => {
        void Linking.openURL(citation.url);
      }}
      style={({ pressed }) => [styles.citation, pressed && styles.pressed]}>
      <Text style={styles.citationPublisher}>
        {`${citation.publisher}${citation.isCounterEvidence ? " · 反证" : ""} ↗`}
      </Text>
      {/* Verbatim from the source; the server refuses any quote it cannot
          find there, which is what lets the reader check the conclusion
          without leaving this screen. */}
      <Text style={styles.citationQuote}>{`「${citation.quote}」`}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { gap: spacing.md, paddingTop: spacing.xs },
  header: { alignItems: "center", flexDirection: "row" },
  back: { alignItems: "center", justifyContent: "center", minHeight: 44, minWidth: 44 },
  backText: { color: colors.blue, fontSize: 12, fontWeight: "900" },
  headerCopy: { alignItems: "center", flex: 1 },
  headerTitle: { color: colors.ink, fontSize: 17, fontWeight: "900" },
  headerMeta: { color: colors.muted, fontSize: 11, marginTop: 2 },
  demo: { alignSelf: "center", color: colors.muted, fontSize: 11, fontWeight: "600" },
  objective: { backgroundColor: colors.navy, borderRadius: radius.lg, gap: spacing.md, padding: spacing.md },
  objectiveTop: { alignItems: "center", flexDirection: "row", gap: spacing.md },
  objectiveCopy: { flex: 1 },
  objectiveEyebrow: { color: colors.blueBright, fontSize: 11, fontWeight: "900" },
  objectiveTitle: { color: colors.card, fontSize: 18, fontWeight: "900", lineHeight: 23, marginTop: 3 },
  objectiveBody: { color: colors.navyMuted, fontSize: 11, lineHeight: 14, marginTop: 4 },
  score: { alignItems: "center", borderColor: colors.navyLine, borderRadius: radius.round, borderWidth: 3, height: 62, justifyContent: "center", width: 62 },
  scoreValue: { color: colors.card, fontSize: 21, fontVariant: ["tabular-nums"], fontWeight: "900" },
  scoreLabel: { color: colors.navyMuted, fontSize: 11, fontWeight: "800" },
  objectiveFooter: { alignItems: "center", borderTopColor: colors.navyLine, borderTopWidth: 1, flexDirection: "row", justifyContent: "space-between", paddingTop: spacing.sm },
  confidence: { color: colors.green, fontSize: 11, fontVariant: ["tabular-nums"], fontWeight: "900" },
  softFactor: { alignItems: "flex-end" },
  softValue: { color: colors.blueBright, fontSize: 13, fontWeight: "900" },
  softLabel: { color: colors.navyMuted, fontSize: 11, fontWeight: "600" },
  council: { gap: spacing.sm },
  sectionHeader: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  sectionTitle: { color: colors.ink, fontSize: 15, fontWeight: "900" },
  sectionMeta: { color: colors.muted, fontSize: 11, fontWeight: "600", marginTop: 2 },
  textButton: { alignItems: "center", justifyContent: "center", minHeight: 44, paddingLeft: spacing.md },
  textButtonLabel: { color: colors.blue, fontSize: 11, fontWeight: "900" },
  disclaimer: { backgroundColor: colors.blueSoft, borderRadius: radius.sm, color: "#3B5F91", fontSize: 11, lineHeight: 14, overflow: "hidden", padding: spacing.sm },
  adviserGrid: { gap: spacing.sm },
  consensus: { backgroundColor: colors.card, borderColor: colors.line, borderRadius: radius.lg, borderWidth: StyleSheet.hairlineWidth, gap: spacing.sm, padding: spacing.md },
  consensusHeader: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  consensusTitle: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  consensusCount: { color: colors.green, fontSize: 11, fontWeight: "900" },
  consensusBody: { color: colors.muted, fontSize: 11, lineHeight: 15 },
  missing: { backgroundColor: colors.amberSoft, borderRadius: radius.md, gap: 4, padding: spacing.sm },
  missingTitle: { color: "#704B05", fontSize: 11, fontWeight: "900" },
  missingBody: { color: "#8B5C08", fontSize: 11, lineHeight: 14 },
  researchButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.card, borderRadius: radius.sm, justifyContent: "center", minHeight: 44, paddingHorizontal: spacing.md },
  researchText: { color: colors.ink, fontSize: 11, fontWeight: "900" },
  researchState: { color: "#8B5C08", fontSize: 11, fontWeight: "700" },
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
  evidenceButtonText: { color: colors.blue, fontSize: 11, fontWeight: "900" },
  blocked: { color: colors.red, fontSize: 11, fontWeight: "800", lineHeight: 14 },
  saveButton: { alignItems: "center", backgroundColor: colors.blue, borderRadius: radius.md, justifyContent: "center", minHeight: 48 },
  saveDisabled: { backgroundColor: colors.muted, opacity: 0.55 },
  saveText: { color: colors.card, fontSize: 12, fontWeight: "900" },
  safety: { color: colors.muted, fontSize: 11, fontWeight: "800", textAlign: "center" },
  pressed: { opacity: 0.68 },
  inviteButton: {
    backgroundColor: colors.navy,
    borderRadius: radius.md,
    gap: 4,
    minHeight: 56,
    justifyContent: "center",
    padding: spacing.md,
  },
  inviteButtonLoading: { opacity: 0.72 },
  inviteButtonTitle: { color: colors.card, fontSize: 13, fontWeight: "900" },
  inviteButtonMeta: { color: colors.navyMuted, fontSize: 11, lineHeight: 15 },
  notice: {
    backgroundColor: colors.blueSoft,
    borderRadius: radius.md,
    gap: spacing.xxs,
    padding: spacing.sm,
  },
  noticeTitle: { color: colors.ink, fontSize: 12, fontWeight: "800", lineHeight: 17 },
  noticeBody: { color: colors.muted, fontSize: 11, lineHeight: 15 },
  pendingFeatures: {
    backgroundColor: colors.blueSoft,
    borderRadius: radius.md,
    gap: 4,
    padding: spacing.sm,
  },
  pendingTitle: { color: colors.ink, fontSize: 11, fontWeight: "900" },
  pendingBody: { color: colors.muted, fontSize: 11, lineHeight: 15 },
  result: { gap: spacing.sm },
  summary: { color: colors.ink, fontSize: 13, fontWeight: "700", lineHeight: 19 },
  scoreFold: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    padding: spacing.sm,
  },
  scoreFoldText: {
    color: colors.ink,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "900",
  },
  councilBlocked: {
    backgroundColor: colors.amberSoft,
    borderRadius: radius.md,
    gap: 4,
    padding: spacing.sm,
  },
  councilBlockedTitle: { color: "#704B05", fontSize: 11, fontWeight: "900" },
  councilBlockedBody: { color: "#8B5C08", fontSize: 11, lineHeight: 14 },
  frameworkCard: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    padding: spacing.sm,
  },
  frameworkName: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  frameworkStance: { color: colors.blue, fontSize: 11, fontWeight: "800" },
  frameworkBlindSpot: { color: colors.muted, fontSize: 11, lineHeight: 15 },
  conclusion: {
    borderLeftColor: colors.blue,
    borderLeftWidth: 2,
    gap: spacing.xxs,
    paddingLeft: spacing.sm,
  },
  conclusionStatement: { color: colors.ink, fontSize: 12, fontWeight: "700", lineHeight: 17 },
  conclusionConfidence: { color: colors.muted, fontSize: 11, fontWeight: "700" },
  citation: {
    backgroundColor: colors.blueSoft,
    borderRadius: radius.sm,
    gap: 2,
    minHeight: 44,
    padding: spacing.xs,
  },
  citationPublisher: { color: colors.blue, fontSize: 11, fontWeight: "800" },
  citationQuote: { color: colors.muted, fontSize: 11, lineHeight: 16 },
  councilDisclaimer: { color: colors.muted, fontSize: 11, fontStyle: "italic", lineHeight: 15 },
  cost: { color: colors.muted, fontSize: 11, fontVariant: ["tabular-nums"], lineHeight: 15 },
});
