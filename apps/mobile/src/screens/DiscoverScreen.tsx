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
import { useMarketDataMode } from "@/state/MarketDataProvider";
import type { Candidate, Citation, PlanSide } from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
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
        <AnalysisNotConnected surface="全市场机会扫描" />
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

const styles = StyleSheet.create({
  screen: { gap: spacing.md, paddingTop: spacing.xs },
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  demoLabel: { color: colors.amber, fontSize: 8, fontWeight: "900" },
  eyebrow: { color: colors.muted, fontSize: 9, fontWeight: "800" },
  title: { color: colors.ink, fontSize: 23, fontWeight: "900", marginTop: spacing.xxs },
  count: { alignItems: "flex-end" },
  countValue: { color: colors.blue, fontSize: 20, fontWeight: "900" },
  countLabel: { color: colors.muted, fontSize: 8, fontWeight: "800" },
  hero: { backgroundColor: colors.navy, borderRadius: radius.lg, gap: spacing.xs, padding: spacing.md },
  heroEyebrow: { color: colors.blueBright, fontSize: 9, fontWeight: "900" },
  heroTitle: { color: colors.card, fontSize: 18, fontWeight: "900" },
  heroBody: { color: colors.navyMuted, fontSize: 10, lineHeight: 15 },
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
  filterText: { color: colors.muted, fontSize: 9, fontWeight: "900" },
  filterTextSelected: { color: colors.card },
  asymmetricSelected: { backgroundColor: colors.purpleSoft, borderColor: colors.purple },
  asymmetricText: { color: colors.purple },
  list: { gap: spacing.sm },
  empty: { alignItems: "center", backgroundColor: colors.card, borderRadius: radius.lg, padding: spacing.xl },
  emptyTitle: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  emptyBody: { color: colors.muted, fontSize: 10, marginTop: spacing.xs },
  pressed: { opacity: 0.66 },
});
