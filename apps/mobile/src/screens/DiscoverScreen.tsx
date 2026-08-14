import { useState } from "react";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { CandidateCard } from "@/components/discover/CandidateCard";
import { AnalysisNotConnected } from "@/components/ui/AnalysisNotConnected";
import {
  DashboardDetailSheet,
  type DetailSection,
} from "@/components/dashboard/DashboardDetailSheet";
import { HorizonSwitch } from "@/components/ui/HorizonSwitch";
import { Screen } from "@/components/ui/Screen";
import {
  useMarketDataMode,
  useMarketWatchlist,
  type DemoMarketWatchlist,
  type MarketDataState,
} from "@/state/MarketDataProvider";
import type { MarketWatchlist } from "@/data/marketRepository";
import type { Candidate, Citation, PlanSide, WatchlistQuote } from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
import { describeMarketError } from "@/i18n/marketErrorCopy";
import { useAppState } from "@/state/AppStateProvider";
import { colors, radius, spacing } from "@/theme/tokens";

type SideFilter = "all" | PlanSide;

type DetailState = {
  title: string;
  sections: DetailSection[];
  citations: Citation[];
} | null;

export function DiscoverScreen() {
  const router = useRouter();
  const { horizon, setHorizon } = useAppState();
  const { demoMode } = useMarketDataMode();
  const watchlist = useMarketWatchlist();
  const openStock = (symbol: string) =>
    router.push({ pathname: "/stocks/[symbol]", params: { symbol } });
  const [sideFilter, setSideFilter] = useState<SideFilter>("all");
  const [asymmetricOnly, setAsymmetricOnly] = useState(false);
  const [detail, setDetail] = useState<DetailState>(null);
  const candidates = fixtureRepository
    .getDashboard(horizon)
    .candidates.filter(
      (candidate) =>
        (sideFilter === "all" || candidate.side === sideFilter) &&
        (!asymmetricOnly || candidate.designation === "asymmetric-upside"),
    );

  const openEvidence = (candidate: Candidate) =>
    setDetail({
      title: `${candidate.symbol} 候选证据`,
      sections: [
        { label: "催化", body: candidate.catalyst },
        { label: "排序原因", body: candidate.reason },
        { label: "最强反证", body: candidate.counterCase },
        { label: "失效条件", body: candidate.invalidation },
        { label: "技术面", body: candidate.technicalState },
        { label: "基本面", body: candidate.fundamentalState },
        {
          label: "证据健康",
          body: `${candidate.evidenceFreshness} · 证据 ${candidate.evidenceCount} · 反证 ${candidate.counterEvidenceCount}`,
        },
      ],
      citations: fixtureRepository.getCitations(candidate.citationIds),
    });

  if (!demoMode) {
    return (
      <Screen hideGlobalHeader style={styles.screen}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>自选异动 · 只读行情</Text>
            <Text style={styles.title}>机会发现</Text>
          </View>
        </View>
        <MarketScan onOpen={openStock} watchlist={watchlist} />
        {/* The scan above is real quotes and nothing more. Ranking by catalyst,
            counter-case and asymmetry is a different service that is not
            deployed, so that half stays empty instead of being approximated
            from a price move. */}
        <AnalysisNotConnected
          missing="缺的是全市场扫描服务：上面的异动来自你的自选行情，只是价格变动排序。催化、最强反证、失效条件与非对称评估需要服务端的候选扫描，目前没有这个路由。"
          surface="候选排序"
        />
      </Screen>
    );
  }

  return (
    <Screen hideGlobalHeader style={styles.screen}>
      <View style={styles.header}>
        <View>
          <Text style={styles.demoLabel}>演示数据 · 非实时行情</Text>
          <Text style={styles.eyebrow}>全市场扫描 · 确定性演示</Text>
          <Text style={styles.title}>机会发现</Text>
        </View>
        <View style={styles.count}>
          <Text style={styles.countValue}>{candidates.length}</Text>
          <Text style={styles.countLabel}>当前候选</Text>
        </View>
      </View>

      <HorizonSwitch
        onChange={(next) => {
          setHorizon(next);
          setDetail(null);
        }}
        value={horizon}
      />

      <View style={styles.hero}>
        <Text style={styles.heroEyebrow}>非对称机会雷达</Text>
        <Text style={styles.heroTitle}>先看赔率，再看故事</Text>
        <Text style={styles.heroBody}>
          结合消息催化、市场情绪、量价、机构参与代理、技术与基本面；不对称候选不代表收益承诺。
        </Text>
      </View>

      <View accessibilityRole="tablist" style={styles.filters}>
        {([
          ["all", "全部方向"],
          ["long", "只看做多"],
          ["short", "只看做空"],
        ] as const).map(([value, label]) => {
          const selected = sideFilter === value;
          return (
            <Pressable
              accessibilityLabel={label}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              key={value}
              onPress={() => setSideFilter(value)}
              style={({ pressed }) => [
                styles.filter,
                selected && styles.filterSelected,
                pressed && styles.pressed,
              ]}>
              <Text style={[styles.filterText, selected && styles.filterTextSelected]}>
                {label}
              </Text>
            </Pressable>
          );
        })}
        <Pressable
          accessibilityLabel="只看非对称上行"
          accessibilityRole="button"
          accessibilityState={{ selected: asymmetricOnly }}
          onPress={() => setAsymmetricOnly((current) => !current)}
          style={({ pressed }) => [
            styles.filter,
            asymmetricOnly && styles.asymmetricSelected,
            pressed && styles.pressed,
          ]}>
          <Text style={[styles.filterText, asymmetricOnly && styles.asymmetricText]}>
            非对称上行
          </Text>
        </Pressable>
      </View>

      <View style={styles.list}>
        {candidates.map((candidate) => (
          <CandidateCard
            candidate={candidate}
            key={candidate.symbol}
            onOpen={() =>
              router.push({
                pathname: "/stocks/[symbol]",
                params: { symbol: candidate.symbol },
              })
            }
            onOpenEvidence={() => openEvidence(candidate)}
          />
        ))}
        {candidates.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>当前筛选没有候选</Text>
            <Text style={styles.emptyBody}>放宽方向或非对称条件后再看。</Text>
          </View>
        ) : null}
      </View>

      <DashboardDetailSheet
        citations={detail?.citations ?? []}
        onClose={() => setDetail(null)}
        sections={detail?.sections ?? []}
        title={detail?.title ?? ""}
        visible={detail !== null}
      />
    </Screen>
  );
}

/**
 * The real half of this page: the reader's own watchlist, ranked by how far
 * each name has moved today.
 *
 * Size of move is the only ordering the quote feed can justify. It is not a
 * ranking of opportunity, and the copy says so, because a list sorted by
 * anything on this screen invites being read as a recommendation.
 */
function MarketScan({
  watchlist,
  onOpen,
}: {
  watchlist: MarketDataState<MarketWatchlist | DemoMarketWatchlist>;
  onOpen(symbol: string): void;
}) {
  const quotes = [...(watchlist.data?.quotes ?? [])].sort(
    (left, right) =>
      Math.abs(right.changePercent) - Math.abs(left.changePercent),
  );

  if (watchlist.status === "unavailable") {
    const failure = describeMarketError(watchlist.error?.category ?? "offline");
    return (
      <View style={styles.scanCard} testID="market-scan-unavailable">
        <Text style={styles.scanTitle}>
          {`自选行情不可用 · ${failure.label}`}
        </Text>
        <Text style={styles.scanBody}>
          取数失败不是「今天没有异动」。
        </Text>
        <Text style={styles.scanBody} testID="market-scan-unavailable-body">
          {failure.body}
        </Text>
        <Pressable
          accessibilityLabel="重试行情"
          accessibilityRole="button"
          onPress={watchlist.refresh}
          style={({ pressed }) => [styles.scanRetry, pressed && styles.pressed]}>
          <Text style={styles.scanRetryText}>重试</Text>
        </Pressable>
      </View>
    );
  }

  if (watchlist.status === "loading") {
    return (
      <View style={styles.scanCard} testID="market-scan-loading">
        <Text style={styles.scanTitle}>正在连接 moomoo 行情…</Text>
      </View>
    );
  }

  return (
    <View style={styles.list} testID="market-scan">
      <View style={styles.scanHeader}>
        <Text style={styles.scanHeaderTitle}>
          {`自选异动 · ${quotes.length} 只`}
        </Text>
        <Text
          style={[
            styles.scanHeaderMeta,
            watchlist.status === "stale" && styles.staleText,
          ]}>
          {watchlist.status === "stale"
            ? `已延迟 · 原始时间 ${watchlist.lastVerifiedAt ?? "未知"}`
            : "实时只读"}
        </Text>
      </View>
      <Text style={styles.scanNote}>
        按当日涨跌幅绝对值排序，只是行情事实；不含催化、反证与非对称评估。
      </Text>
      {quotes.length === 0 ? (
        <View style={styles.scanCard} testID="market-scan-empty">
          <Text style={styles.scanTitle}>自选列表为空</Text>
          <Text style={styles.scanBody}>
            行情已接入，但这个账户没有自选标的。
          </Text>
        </View>
      ) : (
        quotes.map((item) => (
          <ScanRow key={item.symbol} onOpen={onOpen} quote={item} />
        ))
      )}
    </View>
  );
}

function ScanRow({
  quote,
  onOpen,
}: {
  quote: WatchlistQuote;
  onOpen(symbol: string): void;
}) {
  const rising = quote.changePercent >= 0;
  return (
    <Pressable
      accessibilityLabel={`打开 ${quote.symbol} 个股分析`}
      accessibilityRole="button"
      onPress={() => onOpen(quote.symbol)}
      style={({ pressed }) => [styles.scanRow, pressed && styles.pressed]}
      testID={`market-scan-row-${quote.symbol}`}>
      <Text style={styles.scanSymbol}>{quote.symbol}</Text>
      <Text style={styles.scanPrice}>${quote.price.toFixed(2)}</Text>
      <Text style={[styles.scanChange, rising ? styles.up : styles.down]}>
        {`${rising ? "+" : ""}${quote.changePercent.toFixed(2)}%`}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { gap: spacing.md, paddingTop: spacing.xs },
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  demoLabel: { color: colors.amber, fontSize: 11, fontWeight: "900" },
  eyebrow: { color: colors.muted, fontSize: 11, fontWeight: "800" },
  title: { color: colors.ink, fontSize: 23, fontWeight: "900", marginTop: spacing.xxs },
  count: { alignItems: "flex-end" },
  countValue: { color: colors.blue, fontSize: 20, fontWeight: "900" },
  countLabel: { color: colors.muted, fontSize: 11, fontWeight: "800" },
  hero: { backgroundColor: colors.navy, borderRadius: radius.lg, gap: spacing.xs, padding: spacing.md },
  heroEyebrow: { color: colors.blueBright, fontSize: 11, fontWeight: "900" },
  heroTitle: { color: colors.card, fontSize: 18, fontWeight: "900" },
  heroBody: { color: colors.navyMuted, fontSize: 11, lineHeight: 15 },
  filters: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  filter: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: "center",
    minHeight: 44,
    paddingHorizontal: spacing.md,
  },
  filterSelected: { backgroundColor: colors.blue, borderColor: colors.blue },
  filterText: { color: colors.muted, fontSize: 11, fontWeight: "900" },
  filterTextSelected: { color: colors.card },
  asymmetricSelected: { backgroundColor: colors.purpleSoft, borderColor: colors.purple },
  asymmetricText: { color: colors.purple },
  list: { gap: spacing.sm },
  empty: { alignItems: "center", backgroundColor: colors.card, borderRadius: radius.lg, padding: spacing.xl },
  emptyTitle: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  emptyBody: { color: colors.muted, fontSize: 11, marginTop: spacing.xs },
  pressed: { opacity: 0.66 },
  scanCard: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    padding: spacing.md,
  },
  scanTitle: { color: colors.ink, fontSize: 12, fontWeight: "900" },
  scanBody: { color: colors.muted, fontSize: 11, lineHeight: 15 },
  scanRetry: {
    alignItems: "flex-start",
    justifyContent: "center",
    minHeight: 44,
  },
  scanRetryText: { color: colors.blue, fontSize: 11, fontWeight: "900" },
  scanHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  scanHeaderTitle: { color: colors.ink, fontSize: 12, fontWeight: "900" },
  scanHeaderMeta: { color: colors.green, fontSize: 11, fontWeight: "700" },
  staleText: { color: colors.amber },
  scanNote: { color: colors.muted, fontSize: 11, lineHeight: 13 },
  scanRow: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: spacing.sm,
    minHeight: 48,
    paddingHorizontal: spacing.md,
  },
  scanSymbol: { color: colors.ink, flex: 1, fontSize: 13, fontWeight: "900" },
  scanPrice: {
    color: colors.ink,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "700",
  },
  scanChange: {
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    fontWeight: "900",
    minWidth: 64,
    textAlign: "right",
  },
  up: { color: colors.green },
  down: { color: colors.red },
});
