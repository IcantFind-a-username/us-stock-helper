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
import { WatchlistStrip } from "@/components/dashboard/WatchlistStrip";
import {
  StockSearchSheet,
  type StockSearchOption,
} from "@/components/search/StockSearchSheet";
import { HorizonSwitch } from "@/components/ui/HorizonSwitch";
import { Screen } from "@/components/ui/Screen";
import type { Candidate, Citation } from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
import { useAppState } from "@/state/AppStateProvider";
import {
  useMarketDataMode,
  useMarketWatchlist,
} from "@/state/MarketDataProvider";
import { colors, radius, spacing } from "@/theme/tokens";

type DetailState = {
  title: string;
  sections: DetailSection[];
  citations: Citation[];
} | null;

export function DashboardScreen() {
  const router = useRouter();
  const { horizon, setHorizon } = useAppState();
  const { demoAvailable, demoMode, setDemoMode } = useMarketDataMode();
  const marketWatchlist = useMarketWatchlist();
  const snapshot = fixtureRepository.getDashboard(horizon);
  const [detail, setDetail] = useState<DetailState>(null);
  const [searchVisible, setSearchVisible] = useState(false);

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

  const watchlistQuotes = marketWatchlist.data?.quotes ?? [];
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

  const watchlistSurface =
    marketWatchlist.status === "unavailable" ? (
      <View style={styles.watchlistState}>
        <Text style={styles.watchlistTitle}>我的关注</Text>
        <Pressable
          accessibilityLabel="重试行情"
          accessibilityRole="button"
          onPress={marketWatchlist.refresh}
          style={styles.unavailableAction}>
          <Text style={styles.unavailableText}>
            行情不可用 · {marketWatchlist.error?.category ?? "offline"}
          </Text>
          <Text style={styles.retryText}>重试</Text>
        </Pressable>
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
        <WatchlistStrip
          onOpenSource={openWatchlistSource}
          onPress={openStock}
          quotes={watchlistQuotes}
        />
      </View>
    );

  return (
    <Screen hideGlobalHeader style={styles.dashboard}>
      <DashboardHeader
        health={snapshot.dataHealth}
        marketSession={snapshot.marketSession}
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
      {watchlistSurface}
      <CandidateList
        candidates={snapshot.candidates}
        onOpenDiscover={() => router.push("/discover")}
        onOpenEvidence={openCandidateEvidence}
        onPress={openStock}
      />
      <DashboardDetailSheet
        citations={detail?.citations ?? []}
        onClose={() => setDetail(null)}
        sections={detail?.sections ?? []}
        title={detail?.title ?? ""}
        visible={detail !== null}
      />
      <StockSearchSheet
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
  demoModeLabel: { color: colors.ink, fontSize: 11, fontWeight: "800" },
  demoModeHint: { color: colors.muted, fontSize: 9, marginTop: 2 },
  watchlistState: { gap: spacing.xs },
  watchlistTitle: { color: colors.ink, fontSize: 12, fontWeight: "800" },
  watchlistStatusRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 24,
  },
  watchlistMeta: { color: colors.green, fontSize: 10, fontWeight: "700" },
  staleText: { color: colors.amber },
  refreshAction: {
    alignItems: "flex-end",
    justifyContent: "center",
    minHeight: 44,
    minWidth: 44,
  },
  unavailableAction: {
    alignItems: "center",
    backgroundColor: colors.amberSoft,
    borderRadius: radius.md,
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 48,
    paddingHorizontal: spacing.md,
  },
  unavailableText: { color: colors.ink, fontSize: 11, fontWeight: "700" },
  retryText: { color: colors.blue, fontSize: 10, fontWeight: "800" },
});
