import { useState } from "react";
import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";

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
import { HorizonSwitch } from "@/components/ui/HorizonSwitch";
import { Screen } from "@/components/ui/Screen";
import type { Candidate, Citation } from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
import { useAppState } from "@/state/AppStateProvider";
import { spacing } from "@/theme/tokens";

type DetailState = {
  title: string;
  sections: DetailSection[];
  citations: Citation[];
} | null;

export function DashboardScreen() {
  const router = useRouter();
  const { horizon, setHorizon } = useAppState();
  const snapshot = fixtureRepository.getDashboard(horizon);
  const [detail, setDetail] = useState<DetailState>(null);

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
  };

  const openStock = (symbol: string) =>
    router.push({ pathname: "/stocks/[symbol]", params: { symbol } });

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

  return (
    <Screen hideGlobalHeader style={styles.dashboard}>
      <DashboardHeader
        health={snapshot.dataHealth}
        marketSession={snapshot.marketSession}
        onAlerts={() => router.push("/alerts")}
        onSearch={() => undefined}
        updatedAt={snapshot.updatedAt}
      />
      <HorizonSwitch value={horizon} onChange={changeHorizon} />
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
      <WatchlistStrip onPress={openStock} quotes={snapshot.watchlist} />
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
});
