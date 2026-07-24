import type { JournalEntry } from "./models";

export type JournalDraft = {
  symbol: string;
  quantity: string;
  executionPrice: string;
  pnl: string;
};

export type JournalDraftErrors = Partial<Record<keyof JournalDraft, string>>;

export function validateJournalDraft(draft: JournalDraft): JournalDraftErrors {
  const errors: JournalDraftErrors = {};
  const quantity = Number(draft.quantity);
  const executionPrice = Number(draft.executionPrice);
  const pnl = Number(draft.pnl);

  if (draft.symbol.trim() === "") errors.symbol = "请输入股票代码";
  if (!Number.isFinite(quantity) || quantity <= 0) errors.quantity = "数量必须大于 0";
  if (!Number.isFinite(executionPrice) || executionPrice <= 0) {
    errors.executionPrice = "成交价必须大于 0";
  }
  if (draft.pnl.trim() === "" || !Number.isFinite(pnl)) {
    errors.pnl = "盈亏必须是有效数字";
  }

  return errors;
}

export function summarizeJournal(entries: JournalEntry[]) {
  return entries.reduce(
    (summary, entry) => {
      summary.entryCount += 1;
      summary.totalPnl += entry.pnl;
      if (entry.pnlState === "realized") summary.realizedPnl += entry.pnl;
      else summary.unrealizedPnl += entry.pnl;
      if (entry.decision === "followed") summary.followedCount += 1;
      else summary.overriddenCount += 1;
      return summary;
    },
    {
      realizedPnl: 0,
      unrealizedPnl: 0,
      totalPnl: 0,
      followedCount: 0,
      overriddenCount: 0,
      entryCount: 0,
    },
  );
}
