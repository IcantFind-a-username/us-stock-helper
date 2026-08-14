import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import {
  JournalEntryForm,
  type JournalEntryValue,
} from "@/components/journal/JournalEntryForm";
import { SavedPlanCard } from "@/components/journal/SavedPlanCard";
import { Screen } from "@/components/ui/Screen";
import { summarizeJournal } from "@/domain/journal";
import type { JournalEntry } from "@/domain/models";
import { useAppState } from "@/state/AppStateProvider";
import { useMarketDataMode } from "@/state/MarketDataProvider";
import { colors, radius, spacing } from "@/theme/tokens";

export function JournalScreen() {
  const { addJournalEntry, journalEntries, savedPlans } = useAppState();
  const { demoMode } = useMarketDataMode();
  const [showForm, setShowForm] = useState(false);
  const summary = summarizeJournal(journalEntries);

  const saveEntry = (value: JournalEntryValue) => {
    const entry: JournalEntry = {
      ...value,
      id: `journal-${Date.now()}`,
      executedAt: new Date().toISOString(),
      executionDelaySeconds: 0,
      slippage: 0,
    };
    addJournalEntry(entry);
    setShowForm(false);
  };

  return (
    <Screen hideGlobalHeader style={styles.screen}>
      <View style={styles.header}>
        <View>
          {/* The entries below are facts the reader typed in, so they are real
              whatever the data mode is. The badge tracks demo mode rather than
              being pinned on, because on a real build it was labelling the
              reader's own trade history as fake. */}
          {demoMode ? (
            <Text style={styles.demoLabel}>演示数据 · 非实时行情</Text>
          ) : null}
          <Text style={styles.eyebrow}>本地日志 · 客观性隔离</Text>
          <Text style={styles.title}>交易复盘</Text>
        </View>
        <Pressable
          accessibilityLabel="记录一笔执行"
          accessibilityRole="button"
          onPress={() => setShowForm(true)}
          style={({ pressed }) => [styles.addButton, pressed && styles.pressed]}>
          <Text style={styles.addText}>＋ 记录</Text>
        </Pressable>
      </View>

      <View style={styles.summary}>
        <SummaryMetric label="总盈亏" value={formatPnl(summary.totalPnl)} />
        <SummaryMetric label="已实现" value={formatPnl(summary.realizedPnl)} />
        <SummaryMetric label="未实现" value={formatPnl(summary.unrealizedPnl)} />
        <SummaryMetric label="遵循 / 覆盖" value={`${summary.followedCount} / ${summary.overriddenCount}`} />
      </View>

      <View style={styles.firewall}>
        <Text style={styles.firewallTitle}>投资判断防火墙</Text>
        <Text style={styles.firewallBody}>
          操作、盈亏和偏好只用于执行复盘与风险提示；不会改变股票评分、方向或证据可信度。
        </Text>
      </View>

      {showForm ? <JournalEntryForm onCancel={() => setShowForm(false)} onSave={saveEntry} /> : null}

      <SectionTitle eyebrow="分析输出" title="已保存方案" />
      {savedPlans.length === 0 ? (
        <EmptyState
          body="从个股顾问页保存建议后，会在这里形成执行前快照。"
          title="还没有保存的分析方案"
        />
      ) : (
        savedPlans.map((plan) => <SavedPlanCard key={plan.id} plan={plan} />)
      )}

      <SectionTitle eyebrow="用户事实" title="执行记录" />
      {journalEntries.length === 0 ? (
        <EmptyState
          body="记录真实成交与盈亏，用于检查滑点、纪律和执行偏差。"
          title="还没有执行记录"
        />
      ) : (
        journalEntries.map((entry) => <JournalEntryCard entry={entry} key={entry.id} />)
      )}
    </Screen>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.summaryMetric}>
      <Text style={styles.summaryLabel}>{label}</Text>
      <Text style={styles.summaryValue}>{value}</Text>
    </View>
  );
}

function SectionTitle({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <View>
      <Text style={styles.sectionEyebrow}>{eyebrow}</Text>
      <Text style={styles.sectionTitle}>{title}</Text>
    </View>
  );
}

function EmptyState({ body, title }: { body: string; title: string }) {
  return (
    <View style={styles.empty}>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyBody}>{body}</Text>
    </View>
  );
}

function JournalEntryCard({ entry }: { entry: JournalEntry }) {
  return (
    <View style={styles.entryCard}>
      <View style={styles.entryTop}>
        <Text style={styles.entrySymbol}>
          {entry.symbol} · {entry.side === "long" ? "做多" : "做空"}
        </Text>
        <Text style={[styles.entryPnl, entry.pnl < 0 && styles.entryLoss]}>
          {formatPnl(entry.pnl)}
        </Text>
      </View>
      <Text style={styles.entryMeta}>
        {entry.quantity} 股 · ${entry.executionPrice.toFixed(2)} ·{" "}
        {entry.pnlState === "realized" ? "已实现" : "未实现"} ·{" "}
        {entry.decision === "followed" ? "遵循方案" : "主动覆盖"}
      </Text>
      {entry.notes ? <Text style={styles.entryNotes}>{entry.notes}</Text> : null}
    </View>
  );
}

function formatPnl(value: number) {
  return `${value >= 0 ? "+" : "-"}$${Math.abs(value).toFixed(2)}`;
}

const styles = StyleSheet.create({
  screen: { gap: spacing.md, paddingTop: spacing.xs },
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  demoLabel: { color: colors.amber, fontSize: 11, fontWeight: "900" },
  eyebrow: { color: colors.muted, fontSize: 11, fontWeight: "800", marginTop: 2 },
  title: { color: colors.ink, fontSize: 23, fontWeight: "900", marginTop: spacing.xxs },
  addButton: {
    alignItems: "center",
    backgroundColor: colors.blue,
    borderRadius: radius.pill,
    justifyContent: "center",
    minHeight: 44,
    paddingHorizontal: spacing.md,
  },
  addText: { color: colors.card, fontSize: 11, fontWeight: "900" },
  summary: {
    backgroundColor: colors.navy,
    borderRadius: radius.lg,
    flexDirection: "row",
    justifyContent: "space-between",
    padding: spacing.md,
  },
  summaryMetric: { maxWidth: "25%" },
  summaryLabel: { color: colors.navyMuted, fontSize: 11, fontWeight: "800" },
  summaryValue: { color: colors.card, fontSize: 11, fontWeight: "900", marginTop: 3 },
  firewall: {
    backgroundColor: colors.blueSoft,
    borderColor: colors.blue,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    padding: spacing.md,
  },
  firewallTitle: { color: colors.blue, fontSize: 11, fontWeight: "900" },
  firewallBody: { color: colors.ink, fontSize: 11, lineHeight: 14, marginTop: 3 },
  sectionEyebrow: { color: colors.muted, fontSize: 11, fontWeight: "900" },
  sectionTitle: { color: colors.ink, fontSize: 15, fontWeight: "900", marginTop: 2 },
  empty: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: spacing.lg,
  },
  emptyTitle: { color: colors.ink, fontSize: 12, fontWeight: "900" },
  emptyBody: { color: colors.muted, fontSize: 11, lineHeight: 14, marginTop: 4, textAlign: "center" },
  entryCard: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    padding: spacing.md,
  },
  entryTop: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  entrySymbol: { color: colors.ink, fontSize: 13, fontWeight: "900" },
  entryPnl: { color: colors.green, fontSize: 14, fontWeight: "900" },
  entryLoss: { color: colors.red },
  entryMeta: { color: colors.muted, fontSize: 11, fontWeight: "800" },
  entryNotes: { color: colors.ink, fontSize: 11, lineHeight: 15 },
  pressed: { opacity: 0.66 },
});
