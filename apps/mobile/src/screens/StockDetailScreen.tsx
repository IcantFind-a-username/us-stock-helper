import { useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { PriceChart } from "@/components/chart/PriceChart";
import {
  DashboardDetailSheet,
  type DetailSection,
} from "@/components/dashboard/DashboardDetailSheet";
import { IndicatorStrip } from "@/components/stock/IndicatorStrip";
import { MarketContextCard } from "@/components/stock/MarketContextCard";
import { ParticipationCard } from "@/components/stock/ParticipationCard";
import { PatternCard } from "@/components/stock/PatternCard";
import { StockHeader } from "@/components/stock/StockHeader";
import { HorizonSwitch } from "@/components/ui/HorizonSwitch";
import { Screen } from "@/components/ui/Screen";
import type { Citation } from "@/domain/models";
import { fixtureRepository } from "@/fixtures/repository";
import { useAppState } from "@/state/AppStateProvider";
import { colors, radius, spacing } from "@/theme/tokens";

type DetailState = {
  title: string;
  sections: DetailSection[];
  citations: Citation[];
} | null;

const tools = ["MA5", "九转", "预测区间", "机构流代理", "形态"] as const;
type Tool = (typeof tools)[number];

export function StockDetailScreen() {
  const params = useLocalSearchParams<{ symbol?: string | string[] }>();
  const router = useRouter();
  const { horizon, setHorizon } = useAppState();
  const symbolParam = Array.isArray(params.symbol) ? params.symbol[0] : params.symbol;
  const symbol = (symbolParam ?? "NVDA").toUpperCase();
  const stock = fixtureRepository.getStock(symbol, horizon);
  const [detail, setDetail] = useState<DetailState>(null);
  const [visibleTools, setVisibleTools] = useState<Record<Tool, boolean>>({
    MA5: true,
    九转: true,
    预测区间: true,
    机构流代理: true,
    形态: true,
  });

  const openEvidence = (title: string, sections: DetailSection[], citationIds: string[]) =>
    setDetail({
      title,
      sections,
      citations: fixtureRepository.getCitations(citationIds),
    });

  return (
    <Screen hideGlobalHeader style={styles.screen}>
      <StockHeader onBack={() => router.back()} stock={stock} />
      <HorizonSwitch
        onChange={(next) => {
          setHorizon(next);
          setDetail(null);
        }}
        value={horizon}
      />

      <View style={styles.verdict}>
        <View style={styles.verdictCopy}>
          <Text style={styles.eyebrow}>
            客观{horizon === "short" ? "短线" : horizon === "swing" ? "波段" : "中长期"}结论 ·
            调整后 {stock.adjustedScore}
          </Text>
          <Text style={styles.verdictTitle}>{stock.conclusion}</Text>
          <Text style={styles.counter}>{stock.counterCase}</Text>
        </View>
        <View style={styles.score}>
          <Text style={styles.scoreValue}>{stock.adjustedScore}</Text>
          <Text style={styles.scoreLabel}>综合分</Text>
        </View>
      </View>

      <View accessibilityLabel="图表工具" style={styles.tools}>
        {tools.map((tool) => {
          const visible = visibleTools[tool];
          return (
            <Pressable
              accessibilityLabel={`${tool}，${visible ? "已显示" : "已隐藏"}`}
              accessibilityRole="button"
              accessibilityState={{ selected: visible }}
              key={tool}
              onPress={() =>
                setVisibleTools((current) => ({ ...current, [tool]: !current[tool] }))
              }
              style={({ pressed }) => [
                styles.tool,
                visible && styles.toolActive,
                pressed && styles.pressed,
              ]}>
              <Text style={[styles.toolText, visible && styles.toolTextActive]}>{tool}</Text>
            </Pressable>
          );
        })}
      </View>

      <PriceChart
        compact
        showForecast={visibleTools["预测区间"]}
        showMagicNine={visibleTools.九转}
        showMovingAverage={visibleTools.MA5}
        stock={stock}
      />
      {visibleTools["预测区间"] ? <View style={styles.forecastNotice}>
        <Text style={styles.forecastTitle}>概率预测，不是未来价格承诺</Text>
        <Text style={styles.forecastBody}>
          {stock.forecast.horizon} · 中位路径 + 50% / 80% 区间 · 模型{" "}
          {stock.forecast.modelVersion} · 失效：{stock.forecast.invalidation}
        </Text>
      </View> : null}

      <IndicatorStrip macd={stock.indicators.macd} rsi={stock.indicators.rsi} />
      {visibleTools["机构流代理"] ? (
        <ParticipationCard
          proxy={stock.participationProxy}
          reported={stock.reportedOwnership}
        />
      ) : null}
      <PatternCard
        dragonTrend={stock.dragonTrend}
        fundamentals={stock.fundamentals}
        magicNine={stock.magicNine}
        patterns={stock.patterns}
        showTechnical={visibleTools.形态}
      />
      <MarketContextCard context={stock.marketContext} />

      <View style={styles.actions}>
        <Pressable
          accessibilityLabel="查看完整图表"
          accessibilityRole="button"
          onPress={() =>
            router.push({
              pathname: "/stocks/[symbol]/chart",
              params: { symbol },
            })
          }
          style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}>
          <Text style={styles.secondaryText}>查看大图</Text>
        </Pressable>
        <Pressable
          accessibilityLabel="查看证据"
          accessibilityRole="button"
          onPress={() =>
            openEvidence(
              `${symbol} 证据包`,
              [
                { label: "客观结论", body: stock.conclusion },
                { label: "最强反证", body: stock.counterCase },
                { label: "预测失效", body: stock.forecast.invalidation },
                {
                  label: "市场调整",
                  body: `${stock.marketContext.scoreAdjustment} 分 · ${stock.marketContext.planChanges.join("\n")}`,
                },
              ],
              stock.citations.map(({ id }) => id),
            )
          }
          style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}>
          <Text style={styles.secondaryText}>查看证据</Text>
        </Pressable>
      </View>
      <Pressable
        accessibilityLabel="问顾问 / 制定方案"
        accessibilityRole="button"
        onPress={() =>
          router.push({
            pathname: "/stocks/[symbol]/advisers",
            params: { symbol },
          })
        }
        style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}>
        <Text style={styles.primaryText}>问顾问 / 制定方案</Text>
      </Pressable>
      <Text style={styles.boundary}>仅分析与建议 · 不连接券商 · 不会自动下单</Text>

      <DashboardDetailSheet
        citations={detail?.citations ?? []}
        onClose={() => setDetail(null)}
        sections={detail?.sections ?? []}
        title={detail?.title ?? ""}
        visible={detail !== null}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { gap: spacing.md, paddingTop: spacing.xs },
  verdict: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    gap: spacing.md,
    padding: spacing.md,
  },
  verdictCopy: { flex: 1 },
  eyebrow: { color: colors.muted, fontSize: 9, fontWeight: "800" },
  verdictTitle: { color: colors.ink, fontSize: 15, fontWeight: "900", lineHeight: 20, marginTop: 3 },
  counter: { color: colors.muted, fontSize: 10, lineHeight: 15, marginTop: 4 },
  score: {
    alignItems: "center",
    backgroundColor: colors.blueSoft,
    borderRadius: radius.round,
    height: 56,
    justifyContent: "center",
    width: 56,
  },
  scoreValue: { color: colors.blue, fontSize: 20, fontVariant: ["tabular-nums"], fontWeight: "900" },
  scoreLabel: { color: colors.blue, fontSize: 8, fontWeight: "800" },
  tools: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  tool: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderRadius: radius.pill,
    justifyContent: "center",
    minHeight: 44,
    paddingHorizontal: 12,
  },
  toolActive: { backgroundColor: colors.navyRaised },
  toolText: { color: colors.muted, fontSize: 9, fontWeight: "800" },
  toolTextActive: { color: colors.card },
  forecastNotice: { backgroundColor: colors.blueSoft, borderRadius: radius.md, gap: 3, padding: spacing.sm },
  forecastTitle: { color: colors.blue, fontSize: 10, fontWeight: "900" },
  forecastBody: { color: "#3B5F91", fontSize: 9, lineHeight: 14 },
  actions: { flexDirection: "row", gap: spacing.sm },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: 1,
    flex: 1,
    justifyContent: "center",
    minHeight: 44,
  },
  secondaryText: { color: colors.ink, fontSize: 12, fontWeight: "800" },
  primaryButton: {
    alignItems: "center",
    backgroundColor: colors.blue,
    borderRadius: radius.md,
    justifyContent: "center",
    minHeight: 48,
  },
  primaryText: { color: colors.card, fontSize: 13, fontWeight: "900" },
  pressed: { opacity: 0.68 },
  boundary: { color: colors.muted, fontSize: 9, fontWeight: "700", textAlign: "center" },
});
