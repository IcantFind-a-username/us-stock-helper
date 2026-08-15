import { useState } from "react";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Switch, Text, View } from "react-native";

import { CandidateList } from "@/components/dashboard/CandidateList";
import {
  DashboardDetailSheet,
  type DetailSection,
} from "@/components/dashboard/DashboardDetailSheet";
import { DashboardHeader } from "@/components/dashboard/DashboardHeader";
import { DashboardSectionHeader } from "@/components/dashboard/DashboardSectionHeader";
import { MarketRegimeHero } from "@/components/dashboard/MarketRegimeHero";
import { PriorityAlertCard } from "@/components/dashboard/PriorityAlertCard";
import {
  visibleWatchlistQuotes,
  WatchlistPanel,
} from "@/components/dashboard/WatchlistPanel";
import {
  StockSearchSheet,
  type StockSearchOption,
} from "@/components/search/StockSearchSheet";
import { HorizonSwitch } from "@/components/ui/HorizonSwitch";
import { Screen } from "@/components/ui/Screen";
import type { Candidate, Citation } from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
import { describeMarketError } from "@/i18n/marketErrorCopy";
import { useNow } from "@/hooks/use-now";
import { useAppState } from "@/state/AppStateProvider";
import {
  useMarketDataMode,
  useMarketWatchlist,
  useWatchlistDecisions,
} from "@/state/MarketDataProvider";
import { colors, radius, spacing } from "@/theme/tokens";

type DetailState = {
  title: string;
  sections: DetailSection[];
  citations: Citation[];
} | null;

export function DashboardScreen() {
  const router = useRouter();
  const now = useNow();
  const { horizon, setHorizon } = useAppState();
  const { demoAvailable, demoMode, setDemoMode } = useMarketDataMode();
  const marketWatchlist = useMarketWatchlist();
  const snapshot = fixtureRepository.getDashboard(horizon);
  const [detail, setDetail] = useState<DetailState>(null);
  const [searchVisible, setSearchVisible] = useState(false);
  const [watchlistExpanded, setWatchlistExpanded] = useState(false);
  const watchlistQuotes = marketWatchlist.data?.quotes ?? [];
  // Only the rows on screen are scored: the service answers one symbol per
  // request, so scoring a hidden row would spend a request nobody is reading.
  const scoredQuotes = visibleWatchlistQuotes(watchlistQuotes, watchlistExpanded);
  const decisions = useWatchlistDecisions(
    scoredQuotes.map((quote) => quote.symbol),
    horizon,
  );

  const openDetail = (
    title: string,
    sections: DetailSection[],
    citationIds: string[],
  ) => {
    setDetail({
      title,
      sections,
      citations: fixtureRepository.getCitations(citationIds),
    });
  };

  const marketSections: DetailSection[] = [
    { label: "为什么", body: snapshot.marketRationale },
    { label: "当前策略 / 风险姿态", body: snapshot.marketRiskPosture },
    { label: "最强反证", body: snapshot.contradictions.join("\n") },
    { label: "失效条件", body: snapshot.marketInvalidation },
    ...snapshot.marketDrivers.map((driver) => ({
      label: driver.label,
      body: `${driver.conclusion} · 评分 ${driver.score > 0 ? "+" : ""}${driver.score} · 新鲜度 ${driver.freshness}`,
    })),
  ];

  const changeHorizon = (nextHorizon: typeof horizon) => {
    setHorizon(nextHorizon);
    setDetail(null);
    setSearchVisible(false);
  };

  const openStock = (symbol: string) =>
    router.push({ pathname: "/stocks/[symbol]", params: { symbol } });

  const searchOptions: StockSearchOption[] = watchlistQuotes.map((quote) => {
    let company = quote.symbol;
    try {
      company = fixtureRepository.getStock(quote.symbol, horizon).company;
    } catch {
      // Live watchlists are not limited to the developer fixture catalog.
    }
    return {
      company,
      symbol: quote.symbol,
      price: quote.price,
      changePercent: quote.changePercent,
    };
  });

  const openCandidateEvidence = (candidate: Candidate) =>
    openDetail(
      `${candidate.symbol} 候选依据`,
      [
        { label: "原因", body: candidate.reason },
        { label: "最强反例", body: candidate.counterCase },
        { label: "失效条件", body: candidate.invalidation },
        {
          label: "证据状态",
          body: `证据 ${candidate.evidenceCount} · 反证 ${candidate.counterEvidenceCount} · ${candidate.evidenceFreshness}`,
        },
      ],
      candidate.citationIds,
    );

  const openWatchlistSource = () => {
    const connectionBody =
      marketWatchlist.status === "demo"
        ? "开发者已显式开启演示回退；当前数据是确定性 fixture，不是实时行情。"
        : marketWatchlist.status === "live"
          ? `只读 moomoo 行情已验证；原始时间 ${marketWatchlist.lastVerifiedAt ?? "未知"}。`
          : marketWatchlist.status === "stale"
            ? `连接已中断；继续显示上次验证数据，原始时间 ${marketWatchlist.lastVerifiedAt ?? "未知"}。`
            : "只读 moomoo 行情当前不可用；未使用演示数据自动回退。";
    openDetail(
      "moomoo 数据来源",
      [
        { label: "当前连接", body: connectionBody },
        {
          label: "接入边界",
          body: "通过本机 OpenD 读取自选、报价与 K 线；App 不保存账号凭据，也不会调用交易接口。",
        },
      ],
      [],
    );
  };

  const watchlistAccessibilityLabel =
    marketWatchlist.status === "demo"
      ? "自选行情，演示"
      : marketWatchlist.status === "stale"
        ? `自选行情，陈旧，原始时间 ${marketWatchlist.lastVerifiedAt ?? "未知"}`
        : `自选行情，实时，验证时间 ${marketWatchlist.lastVerifiedAt ?? "未知"}`;

  // A failure worth showing is a failure worth explaining. The row used to be
  // the category identifier and nothing else, which named the problem in a
  // language the reader does not read and offered no way to judge whether it
  // was his to fix.
  const watchlistFailure = describeMarketError(
    marketWatchlist.error?.category ?? "offline",
  );

  const watchlistSurface =
    marketWatchlist.status === "unavailable" ? (
      <View style={styles.watchlistState}>
        <Text style={styles.watchlistTitle}>我的关注</Text>
        <View style={styles.unavailableCard}>
          <Text style={styles.unavailableText}>
            行情不可用 · {watchlistFailure.label}
          </Text>
          <Text
            style={styles.unavailableBody}
            testID="watchlist-unavailable-body">
            {watchlistFailure.body}
          </Text>
          <Pressable
            accessibilityHint={watchlistFailure.title}
            accessibilityLabel="重试行情"
            accessibilityRole="button"
            onPress={marketWatchlist.refresh}
            style={styles.unavailableAction}>
            <Text style={styles.retryText}>重试</Text>
          </Pressable>
        </View>
      </View>
    ) : marketWatchlist.status === "loading" ? (
      <View style={styles.watchlistState}>
        <Text style={styles.watchlistTitle}>我的关注</Text>
        <Text style={styles.watchlistMeta}>正在连接 moomoo 行情…</Text>
      </View>
    ) : (
      <View style={styles.watchlistState}>
        <View style={styles.watchlistStatusRow}>
          <Text
            style={[
              styles.watchlistMeta,
              marketWatchlist.status === "stale" && styles.staleText,
            ]}>
            {marketWatchlist.status === "demo"
              ? "演示数据 · 非实时"
              : marketWatchlist.status === "stale"
                ? `行情已延迟 · 原始时间 ${marketWatchlist.lastVerifiedAt ?? "未知"}`
                : "实时行情"}
          </Text>
          {marketWatchlist.status !== "demo" ? (
            <Pressable
              accessibilityLabel="刷新行情"
              accessibilityRole="button"
              onPress={marketWatchlist.refresh}
              style={styles.refreshAction}>
              <Text style={styles.retryText}>刷新</Text>
            </Pressable>
          ) : null}
        </View>
        {watchlistQuotes.length === 0 ? (
          <View style={styles.emptyCard} testID="watchlist-empty">
            <Text style={styles.watchlistTitle}>我的关注</Text>
            <Text style={styles.emptyTitle}>
              {marketWatchlist.status === "demo"
                ? "演示自选为空"
                : "moomoo 自选为空"}
            </Text>
            <Text style={styles.emptyHint}>
              {marketWatchlist.status === "demo"
                ? "演示模式没有提供任何自选标的。"
                : "moomoo 账户里没有自选标的。在 moomoo 中添加后刷新。"}
            </Text>
          </View>
        ) : (
          <WatchlistPanel
            accessibilityLabel={watchlistAccessibilityLabel}
            decisions={decisions}
            expanded={watchlistExpanded}
            onOpenSource={openWatchlistSource}
            onPress={openStock}
            onToggleExpanded={() =>
              setWatchlistExpanded((expanded) => !expanded)
            }
            quotes={watchlistQuotes}
          />
        )}
      </View>
    );

  return (
    <Screen hideGlobalHeader style={styles.dashboard}>
      <DashboardHeader
        demoMode={demoMode}
        health={snapshot.dataHealth}
        marketSession={snapshot.marketSession}
        now={now}
        onAlerts={() => router.push("/alerts")}
        onSearch={() => setSearchVisible(true)}
        updatedAt={snapshot.updatedAt}
      />
      <HorizonSwitch value={horizon} onChange={changeHorizon} />
      {demoAvailable ? (
        <View style={styles.demoModeRow}>
          <View>
            <Text style={styles.demoModeLabel}>演示模式</Text>
            <Text style={styles.demoModeHint}>仅开发构建 · 不会自动开启</Text>
          </View>
          <Switch
            accessibilityLabel="演示模式"
            onValueChange={setDemoMode}
            value={demoMode}
          />
        </View>
      ) : null}
      {demoMode ? (
        <MarketRegimeHero
          advice={snapshot.marketAdvice}
          conclusion={snapshot.marketConclusion}
          drivers={snapshot.marketDrivers}
          onOpenDetail={() =>
            openDetail(
              "市场完整依据",
              marketSections,
              [
                ...snapshot.dataHealthCitationIds,
                ...snapshot.marketDrivers.flatMap((driver) => driver.citationIds),
              ],
            )
          }
          rationale={snapshot.marketRationale}
          score={snapshot.marketScore}
          updatedAt={snapshot.updatedAt}
        />
      ) : (
        <View style={styles.analysisPlaceholder}>
          <Text style={styles.analysisPlaceholderTitle}>
            市场分析尚未接入真实数据
          </Text>
          <Text style={styles.analysisPlaceholderHint}>
            市场结论、优先提醒与候选列表只在演示模式展示确定性演示内容；真实分析上线前不显示任何推断结论。下方自选里的个股评分来自真实分析服务，取不到时会写明原因。
          </Text>
        </View>
      )}
      {demoMode ? (
        <View style={styles.section}>
          <DashboardSectionHeader
            actionLabel="全部提醒 ›"
            onAction={() => router.push("/alerts")}
            title="需要关注"
          />
          <PriorityAlertCard
            alert={snapshot.priorityAlert}
            onOpenDetail={() =>
              openDetail(
                `${snapshot.priorityAlert.symbol} 提醒依据`,
                [
                  { label: "当前状态", body: snapshot.priorityAlert.currentState },
                  { label: "来源覆盖", body: snapshot.priorityAlert.sourceCoverage },
                  { label: "失效条件", body: snapshot.priorityAlert.invalidation },
                ],
                snapshot.priorityAlert.citations.map((citation) => citation.id),
              )
            }
            onPress={() => openStock(snapshot.priorityAlert.symbol)}
          />
        </View>
      ) : null}
      {watchlistSurface}
      {demoMode ? (
        <CandidateList
          candidates={snapshot.candidates}
          onOpenDiscover={() => router.push("/discover")}
          onOpenEvidence={openCandidateEvidence}
          onPress={openStock}
        />
      ) : null}
      <DashboardDetailSheet
        citations={detail?.citations ?? []}
        onClose={() => setDetail(null)}
        sections={detail?.sections ?? []}
        title={detail?.title ?? ""}
        visible={detail !== null}
      />
      <StockSearchSheet
        demoMode={demoMode}
        onClose={() => setSearchVisible(false)}
        onSelect={(symbol) => {
          setSearchVisible(false);
          openStock(symbol);
        }}
        options={searchOptions}
        visible={searchVisible}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  dashboard: {
    gap: 10,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xs,
  },
  section: { gap: 7 },
  demoModeRow: {
    alignItems: "center",
    backgroundColor: colors.blueSoft,
    borderRadius: radius.md,
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 48,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  demoModeLabel: { color: colors.ink, fontSize: 13, fontWeight: "800" },
  demoModeHint: { color: colors.muted, fontSize: 11, lineHeight: 16, marginTop: 2 },
  analysisPlaceholder: {
    backgroundColor: colors.blueSoft,
    borderRadius: radius.md,
    gap: spacing.xs,
    padding: spacing.md,
  },
  analysisPlaceholderTitle: { color: colors.ink, fontSize: 14, fontWeight: "800" },
  analysisPlaceholderHint: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  watchlistState: { gap: spacing.xs },
  emptyCard: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    padding: spacing.md,
  },
  emptyTitle: { color: colors.ink, fontSize: 14, fontWeight: "800" },
  emptyHint: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  watchlistTitle: { color: colors.ink, fontSize: 14, fontWeight: "800" },
  watchlistStatusRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 24,
  },
  watchlistMeta: { color: colors.green, fontSize: 11, fontWeight: "700" },
  staleText: { color: colors.amber },
  refreshAction: {
    alignItems: "flex-end",
    justifyContent: "center",
    minHeight: 44,
    minWidth: 44,
  },
  unavailableCard: {
    backgroundColor: colors.amberSoft,
    borderRadius: radius.md,
    gap: spacing.xs,
    padding: spacing.md,
  },
  unavailableAction: {
    alignItems: "flex-start",
    justifyContent: "center",
    minHeight: 44,
  },
  unavailableText: { color: colors.ink, fontSize: 14, fontWeight: "700" },
  unavailableBody: { color: "#8B5C08", fontSize: 12, lineHeight: 18 },
  retryText: { color: colors.blue, fontSize: 12, fontWeight: "800" },
});
