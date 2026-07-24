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
import { dashboardFixtures } from "./dashboard";
import { stockFixtures } from "./stocks";

export interface FixtureRepository {
  getDashboard(horizon: Horizon): DashboardSnapshot;
  getStock(symbol: string, horizon: Horizon): StockSnapshot;
  getAdvisers(symbol: string, horizon: Horizon): AdviserOpinion[];
  getTradePlans(symbol: string): TradePlan[];
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
  getAdvisers: () => adviserOpinions,
  getTradePlans: (symbol) =>
    tradePlanFixtures.filter((plan) => plan.symbol === symbol.toUpperCase()),
  getAlerts: () => alertThreads,
  getConversation: () => conversationTurns,
  getCitations: (ids) => {
    const all = [
      ...Object.values(stockFixtures).flatMap((stock) => stock.citations),
      ...alertThreads.flatMap((alert) => alert.citations),
    ];
    return ids.flatMap((id) => {
      const citation = all.find((candidate) => candidate.id === id);
      return citation ? [citation] : [];
    });
  },
};
