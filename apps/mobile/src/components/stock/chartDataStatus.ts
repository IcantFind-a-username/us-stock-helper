import type { MarketDataStatus } from "@/state/MarketDataProvider";

export type ChartDataStatus = "demo" | "live" | "stale";

export function getChartDataStatus(
  marketStatus: MarketDataStatus,
  demoData: boolean,
): ChartDataStatus {
  if (demoData || marketStatus === "demo") return "demo";
  if (marketStatus === "live") return "live";
  return "stale";
}
