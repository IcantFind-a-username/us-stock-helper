import { useState } from "react";
import { useRouter } from "expo-router";

import { CandidateList } from "@/components/dashboard/CandidateList";
import { MarketPlaybookCard } from "@/components/dashboard/MarketPlaybookCard";
import { PriorityAlertCard } from "@/components/dashboard/PriorityAlertCard";
import { WatchlistStrip } from "@/components/dashboard/WatchlistStrip";
import { EvidenceSheet } from "@/components/evidence/EvidenceSheet";
import { DataHealthBanner } from "@/components/ui/DataHealthBanner";
import { DemoDataBadge } from "@/components/ui/DemoDataBadge";
import { HorizonSwitch } from "@/components/ui/HorizonSwitch";
import { Screen } from "@/components/ui/Screen";
import type { Citation } from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
import { useAppState } from "@/state/AppStateProvider";

export function DashboardScreen() {
  const router = useRouter();
  const { horizon, setHorizon } = useAppState();
  const snapshot = fixtureRepository.getDashboard(horizon);
  const [evidence, setEvidence] = useState<Citation[]>([]);
  const openEvidence = (ids: string[]) => setEvidence(fixtureRepository.getCitations(ids));
  const openStock = (symbol: string) => router.push({ pathname: "/stocks/[symbol]", params: { symbol } });

  return (
    <Screen>
      <DemoDataBadge />
      <HorizonSwitch value={horizon} onChange={setHorizon} />
      <DataHealthBanner health={snapshot.dataHealth} marketSession={snapshot.marketSession} />
      <MarketPlaybookCard
        advice={snapshot.marketAdvice}
        conclusion={snapshot.marketConclusion}
        confidence={snapshot.marketConfidence}
        contradictions={snapshot.contradictions}
        drivers={snapshot.marketDrivers}
        invalidation={snapshot.marketInvalidation}
        onOpenEvidence={openEvidence}
        score={snapshot.marketScore}
        scoreChange={snapshot.marketScoreChange}
        updatedAt={snapshot.updatedAt}
      />
      <PriorityAlertCard alert={snapshot.priorityAlert} onOpenEvidence={openEvidence} onPress={() => openStock(snapshot.priorityAlert.symbol)} />
      <WatchlistStrip onPress={openStock} quotes={snapshot.watchlist} title="moomoo watchlist · 演示占位" />
      <CandidateList candidates={snapshot.candidates} onOpenEvidence={openEvidence} onPress={openStock} title="潜力候选" />
      <EvidenceSheet citations={evidence} title="市场证据" />
    </Screen>
  );
}
