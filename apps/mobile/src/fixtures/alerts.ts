import type { AlertThread } from "@/domain/models";

export const alertThreads: AlertThread[] = [{
  id: "NVDA-volume-confirmation",
  symbol: "NVDA",
  horizon: "short",
  severity: "action",
  title: "NVDA 接近量价确认区",
  summary: "价格走强，但仍需成交量与指数环境共同确认。",
  triggeredAt: "2026-07-24T10:26:00-04:00",
  sourceFreshness: "fresh",
  sourceCoverage: "盘中报价、期权与量价演示快照",
  currentState: "等待量价确认",
  invalidation: "收盘跌破 136.40",
  baseScoreContribution: 7,
  adviserAdjustment: 2,
  evidenceCount: 5,
  counterEvidenceCount: 2,
  updatedAt: "2026-07-24T10:30:00-04:00",
  citations: [{
    id: "nvda-source-2",
    title: "演示：市场与成交结构快照",
    publisher: "Demo Market Feed",
    url: "https://example.com/demo-market-feed",
    publishedAt: "2026-07-24T14:30:00Z",
    firstSeenAt: "2026-07-24T14:30:01Z",
    kind: "inference",
  }],
}];
