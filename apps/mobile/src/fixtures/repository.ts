import type {
  AdviserOpinion,
  AlertThread,
  Citation,
  ConversationTurn,
  DashboardSnapshot,
  Horizon,
  StockSnapshot,
  TradePlan,
} from "@/domain/models";
import { alertThreads } from "./alerts";
import { adviserOpinions, tradePlanFixtures } from "./advisers";
import { conversationTurns } from "./conversations";
import { dashboardCitations, dashboardFixtures } from "./dashboard";
import { stockFixtures } from "./stocks";

export interface FixtureRepository {
  getDashboard(horizon: Horizon): DashboardSnapshot;
  getStock(symbol: string, horizon: Horizon): StockSnapshot;
  getAdvisers(symbol: string, horizon: Horizon): AdviserOpinion[];
  getTradePlans(symbol: string, horizon?: Horizon): TradePlan[];
  getAlerts(): AlertThread[];
  getConversation(): ConversationTurn[];
  getCitations(ids: string[]): Citation[];
}

export const fixtureRepository: FixtureRepository = {
  getDashboard: (horizon) => dashboardFixtures[horizon],
  getStock: (symbol, horizon) => {
    const key = `${symbol.toUpperCase()}:${horizon}`;
    const stock = stockFixtures[key];
    if (!stock) throw new Error(`Missing stock fixture: ${key}`);
    return stock;
  },
  getAdvisers: (symbol, horizon) => {
    const normalized = symbol.toUpperCase();
    const directionBySymbol: Record<string, AdviserOpinion["direction"][]> = {
      NVDA: ["bullish", "bullish", "bullish", "bearish"],
      TSLA: ["neutral", "bearish", "bearish", "bullish"],
      PLTR: ["bullish", "neutral", "bearish", "bullish"],
    };
    return adviserOpinions.map((opinion, index) => ({
      ...opinion,
      direction: directionBySymbol[normalized]?.[index] ?? opinion.direction,
      thesis: `基于 ${normalized} ${horizon} 演示证据包的风格化观点。`,
      evidenceIds: [`${normalized.toLowerCase()}-source-1`],
    }));
  },
  getTradePlans: (symbol, horizon = "short") =>
    tradePlanFixtures.filter(
      (plan) => plan.symbol === symbol.toUpperCase() && plan.horizon === horizon,
    ),
  getAlerts: () => alertThreads,
  getConversation: () => conversationTurns,
  getCitations: (ids) => {
    const all = [
      ...Object.values(stockFixtures).flatMap((stock) => stock.citations),
      ...alertThreads.flatMap((alert) => alert.citations),
      ...dashboardCitations,
    ];
    return ids.flatMap((id) => {
      const citation = all.find((candidate) => candidate.id === id);
      return citation ? [citation] : [];
    });
  },
};
