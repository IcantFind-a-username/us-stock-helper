import type { ConversationTurn } from "@/domain/models";

export const conversationTurns: ConversationTurn[] = [{
  id: "assistant-nvda-short",
  role: "assistant",
  citationIds: ["nvda-source-1", "nvda-source-2"],
  sections: [
    { title: "客观结论", body: "短线谨慎偏多，但不追高。" },
    { title: "证据", body: "【事实】正式披露持仓；【推断】板块相对强势、量价结构改善。" },
    { title: "最强反证", body: "【传闻】出口限制尚待确认；【情景】若升级可能改变风险溢价。" },
    { title: "缺失信息与不确定性", body: "盘中参与结构只是估算代理，非真实账户标签。" },
    { title: "个性化风险场景", body: "高回报偏好只改变仓位与止损方案，不改变方向判断。" },
    { title: "引用", body: "SEC 演示持仓报告；演示市场快照。" },
  ],
}];
