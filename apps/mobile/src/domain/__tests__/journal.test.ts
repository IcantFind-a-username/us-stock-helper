import { expect, it } from "@jest/globals";

import { summarizeJournal, validateJournalDraft } from "../journal";

it("rejects incomplete and non-positive execution facts", () => {
  expect(
    validateJournalDraft({
      symbol: " ",
      quantity: "0",
      executionPrice: "-1",
      pnl: "not-a-number",
    }),
  ).toEqual({
    symbol: "请输入股票代码",
    quantity: "数量必须大于 0",
    executionPrice: "成交价必须大于 0",
    pnl: "盈亏必须是有效数字",
  });
});

it("aggregates realized and unrealized P&L without using it as market evidence", () => {
  expect(
    summarizeJournal([
      {
        id: "entry-1",
        symbol: "NVDA",
        side: "long",
        quantity: 10,
        executionPrice: 140,
        executedAt: "2026-07-24T14:30:00Z",
        executionDelaySeconds: 25,
        pnl: 120,
        pnlState: "realized",
        decision: "followed",
        slippage: 0.1,
        notes: "",
      },
      {
        id: "entry-2",
        symbol: "TSLA",
        side: "short",
        quantity: 5,
        executionPrice: 330,
        executedAt: "2026-07-24T15:30:00Z",
        executionDelaySeconds: 40,
        pnl: -35,
        pnlState: "unrealized",
        decision: "overridden",
        slippage: 0.2,
        notes: "",
      },
    ]),
  ).toEqual({
    realizedPnl: 120,
    unrealizedPnl: -35,
    totalPnl: 85,
    followedCount: 1,
    overriddenCount: 1,
    entryCount: 2,
  });
});
