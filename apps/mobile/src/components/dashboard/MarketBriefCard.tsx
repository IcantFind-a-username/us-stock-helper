import { useState } from "react";
import {
  Linking,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { DataHealthBanner } from "@/components/ui/DataHealthBanner";
import { PlainReadingCard } from "@/components/ui/PlainReadingCard";
import type { MarketDataError } from "@/data/marketRepository";
import type {
  MarketBrief,
  MarketBriefDriverCoverage,
  MarketDriverCategory,
} from "@/domain/models";
import { describeMarketError } from "@/i18n/marketErrorCopy";
import { readBreadthDriver, readSectorDriver } from "@/i18n/plainLanguage";
import { serviceTextLabel } from "@/i18n/serverVocabulary";
import { colors, radius, spacing } from "@/theme/tokens";

/**
 * The Dashboard's real-mode market hero -- what replaces the
 * "市场分析尚未接入真实数据" placeholder now that `GET /market-brief`
 * (799d6c4) and its decoder (cf3c66e) both exist. It renders exactly what the
 * server states and nothing it does not: a conclusion the packet actually
 * measured, a driver list that names its own gaps instead of inventing
 * scores for the eight categories nothing sources yet, and the server's own
 * words when the brief could not be produced at all -- never the fixture
 * hero this card stands in for.
 */

const CATEGORY_LABELS: Record<MarketDriverCategory, string> = {
  "news-sentiment": "新闻与社交情绪",
  breadth: "市场广度",
  "volatility-options": "波动率、期权与期限结构",
  sector: "板块强弱",
  "rates-dollar": "利率、收益率曲线与美元",
  "macro-credit-energy": "宏观、信用、能源与商品",
  "liquidity-correlation": "流动性与相关性压力",
  "broad-market-trend": "大盘趋势",
  geopolitics: "地缘政治",
};

export const MARKET_SESSION_LABELS: Record<MarketBrief["marketSession"], string> = {
  premarket: "盘前",
  regular: "盘中",
  afterhours: "盘后",
  closed: "休市",
};

function formatActionScore(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

/**
 * Only breadth and sector have an actual computed state to classify (自选
 * 广度's 多数走强/走弱/涨跌互现, sector RS's leading/lagging leader) -- the
 * other seven driver categories are still unsourced, so there is nothing a
 * plain-language reading could say beyond the missingReason already shown.
 */
function driverPlainReading(entry: MarketBriefDriverCoverage) {
  if (entry.category === "breadth") return readBreadthDriver(entry);
  if (entry.category === "sector") return readSectorDriver(entry);
  return null;
}

function formatCitationTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", { hour12: false });
}

type MarketBriefCardProps = {
  status: "loading" | "live" | "stale" | "unavailable" | "demo";
  brief: MarketBrief | null;
  error: MarketDataError | null;
  onRetry(): void;
};

export function MarketBriefCard({ status, brief, error, onRetry }: MarketBriefCardProps) {
  const [citationsVisible, setCitationsVisible] = useState(false);

  if (brief === null) {
    if (status === "loading" || status === "demo") {
      return (
        <View style={styles.loadingCard} testID="market-brief-loading">
          <Text style={styles.loadingText}>正在读取市场简报…</Text>
        </View>
      );
    }
    // The request itself never came back with a body to read -- a transport
    // failure, not a business verdict, so the reason comes from the same
    // vocabulary the watchlist already uses for a failed request rather than
    // from anything the market-brief route said.
    const failure = describeMarketError(error?.category ?? "offline");
    return (
      <View style={styles.unavailableCard} testID="market-brief-unavailable">
        <Text style={styles.unavailableTitle}>市场简报不可用 · {failure.label}</Text>
        <Text style={styles.unavailableBody} testID="market-brief-unavailable-reason">
          {failure.body}
        </Text>
        <Pressable
          accessibilityLabel="重试市场简报"
          accessibilityRole="button"
          onPress={onRetry}
          style={styles.retryAction}>
          <Text style={styles.retryText}>重试</Text>
        </Pressable>
      </View>
    );
  }

  if (brief.status === "unavailable") {
    // The fail-closed path: the server read through every configured source
    // and still had nothing, and said so in its own words. That sentence is
    // shown verbatim -- it already names every source that failed -- rather
    // than paraphrased into a shorter one that could drift from what
    // actually happened.
    return (
      <View style={styles.unavailableCard} testID="market-brief-unavailable">
        <Text style={styles.unavailableTitle}>市场简报不可用</Text>
        <Text style={styles.unavailableBody} testID="market-brief-unavailable-reason">
          {brief.reason ? serviceTextLabel(brief.reason) : brief.reason}
        </Text>
        <Pressable
          accessibilityLabel="重试市场简报"
          accessibilityRole="button"
          onPress={onRetry}
          style={styles.retryAction}>
          <Text style={styles.retryText}>重试</Text>
        </Pressable>
      </View>
    );
  }

  const { sentiment, driverCoverage, citations, dataHealth, marketSession, sourceGaps, notes } = brief;
  if (!sentiment || !dataHealth) {
    // The contract guarantees both are present whenever status is
    // "available" -- this is an unreachable defensive fallback, not a state
    // the server can actually produce.
    return null;
  }

  return (
    <View style={styles.card} testID="market-brief-card">
      <Text style={styles.eyebrow}>市场情绪结论 · 真实数据</Text>
      <Text style={styles.conclusion}>{sentiment.conclusion}</Text>
      <Text style={styles.actionScore}>
        情绪打分 {formatActionScore(sentiment.actionScore)}
      </Text>
      {sentiment.uncertainty.length > 0 ? (
        <View style={styles.uncertaintyRow}>
          {sentiment.uncertainty.map((item) => (
            <View key={item} style={styles.uncertaintyChip}>
              <Text style={styles.uncertaintyText}>{item}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <DataHealthBanner
        citationIds={citations.map((citation) => citation.id)}
        evidenceTitle="市场简报引用"
        health={dataHealth}
        marketSession={MARKET_SESSION_LABELS[marketSession]}
        onOpenEvidence={() => setCitationsVisible(true)}
      />

      <View style={styles.coverageList} testID="market-brief-driver-coverage">
        <Text style={styles.coverageHeading}>驱动覆盖</Text>
        {driverCoverage.map((entry) => {
          const plainReading = driverPlainReading(entry);
          return (
            <View key={entry.category} style={styles.coverageRow}>
              <Text style={styles.coverageLabel}>{CATEGORY_LABELS[entry.category]}</Text>
              {entry.available ? (
                <Text style={styles.coverageValue}>
                  {entry.conclusion} · {formatActionScore(entry.actionScore!)}
                </Text>
              ) : (
                <Text style={styles.coverageMissing}>{entry.missingReason}</Text>
              )}
              {plainReading ? (
                <PlainReadingCard
                  explanation={plainReading.explanation}
                  headline={plainReading.headline}
                  numbers={plainReading.numbers}
                  testID={`plain-reading-card-${entry.category}`}
                />
              ) : null}
            </View>
          );
        })}
      </View>

      {sourceGaps.length > 0 ? (
        <Text style={styles.sourceGaps} testID="market-brief-source-gaps">
          本轮未能读取：{sourceGaps.join("、")}
        </Text>
      ) : null}

      {notes.map((note) => (
        <Text key={note} style={styles.note} testID="market-brief-note">
          · {serviceTextLabel(note)}
        </Text>
      ))}

      <Modal
        animationType="slide"
        onRequestClose={() => setCitationsVisible(false)}
        presentationStyle="pageSheet"
        visible={citationsVisible}>
        <SafeAreaView edges={["top", "bottom"]} style={styles.sheetSafeArea}>
          <View style={styles.sheetHeader}>
            <Text style={styles.sheetTitle}>市场简报引用</Text>
            <Pressable
              accessibilityLabel="关闭市场简报引用"
              accessibilityRole="button"
              onPress={() => setCitationsVisible(false)}
              style={styles.sheetClose}>
              <Text style={styles.sheetCloseText}>完成</Text>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={styles.sheetContent}>
            {citations.length ? (
              citations.map((citation) => (
                <Pressable
                  accessibilityHint="在浏览器中打开来源"
                  accessibilityLabel={`打开来源：${citation.publisher}`}
                  accessibilityRole="link"
                  key={citation.id}
                  onPress={() => {
                    void Linking.openURL(citation.url);
                  }}
                  style={styles.citationRow}>
                  <Text style={styles.citationHeadline}>{citation.headline}</Text>
                  <Text style={styles.citationMeta}>
                    {citation.publisher} · {formatCitationTime(citation.availableAt)}
                    {citation.stale ? " · 可能延迟" : ""}
                  </Text>
                </Pressable>
              ))
            ) : (
              <Text style={styles.sheetEmpty}>暂无可用引用</Text>
            )}
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  loadingCard: {
    backgroundColor: colors.blueSoft,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  loadingText: { color: colors.muted, fontSize: 12, fontWeight: "700" },
  unavailableCard: {
    backgroundColor: colors.amberSoft,
    borderRadius: radius.md,
    gap: spacing.xs,
    padding: spacing.md,
  },
  unavailableTitle: { color: colors.ink, fontSize: 14, fontWeight: "800" },
  unavailableBody: { color: "#8B5C08", fontSize: 12, lineHeight: 18 },
  retryAction: { alignItems: "flex-start", justifyContent: "center", minHeight: 44 },
  retryText: { color: colors.blue, fontSize: 12, fontWeight: "800" },
  card: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.md,
  },
  eyebrow: { color: colors.muted, fontSize: 11, fontWeight: "800", letterSpacing: 0.5 },
  conclusion: { color: colors.ink, fontSize: 22, fontWeight: "800", marginTop: 2 },
  actionScore: { color: colors.muted, fontSize: 12, fontWeight: "700" },
  uncertaintyRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  uncertaintyChip: {
    backgroundColor: colors.purpleSoft,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
  },
  uncertaintyText: { color: colors.purple, fontSize: 11, fontWeight: "800" },
  coverageList: { gap: spacing.xs },
  coverageHeading: { color: colors.ink, fontSize: 13, fontWeight: "800" },
  coverageRow: {
    borderBottomColor: colors.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: spacing.xxs,
    paddingVertical: spacing.xs,
  },
  coverageLabel: { color: colors.ink, fontSize: 12, fontWeight: "700" },
  coverageValue: { color: colors.muted, fontSize: 12 },
  coverageMissing: { color: colors.muted, fontSize: 12, fontStyle: "italic" },
  sourceGaps: { color: colors.amber, fontSize: 11, fontWeight: "700", lineHeight: 16 },
  note: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  sheetSafeArea: { backgroundColor: colors.backgroundRaised, flex: 1 },
  sheetHeader: {
    alignItems: "center",
    borderBottomColor: colors.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
  },
  sheetTitle: { color: colors.ink, flex: 1, fontSize: 18, fontWeight: "800" },
  sheetClose: { alignItems: "center", justifyContent: "center", minHeight: 44, minWidth: 44, paddingLeft: spacing.lg },
  sheetCloseText: { color: colors.blue, fontSize: 15, fontWeight: "800" },
  sheetContent: { gap: spacing.sm, padding: spacing.lg, paddingBottom: spacing.xl },
  citationRow: {
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xxs,
    minHeight: 44,
    padding: spacing.md,
  },
  citationHeadline: { color: colors.ink, fontSize: 13, fontWeight: "700" },
  citationMeta: { color: colors.muted, fontSize: 11 },
  sheetEmpty: { color: colors.muted, fontSize: 13 },
});
