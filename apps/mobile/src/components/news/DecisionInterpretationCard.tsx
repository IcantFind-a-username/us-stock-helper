import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import type { AdviserUsage, Decision } from "@/domain/models";
import { serviceTextLabel } from "@/i18n/serverVocabulary";
import { radius, spacing } from "@/theme/tokens";

import type { NewsPalette } from "./newsPalette";

/**
 * The model's reading of the cited reports, or a straight answer about why
 * there isn't one.
 *
 * Four different absences used to render as the same sentence. They are kept
 * apart here because each one asks something different of the reader:
 *
 * - the analysis has not come back yet — wait;
 * - nobody asked for the interpretation — it costs money, so ask and pay;
 * - the model was asked and could not answer — retry, and in the meantime read
 *   the reports below, because a broken model is not a model with no view;
 * - the server has no such feature — the deployment is behind.
 *
 * Nothing here is ever filled in from the app's own guesses. Every sentence on
 * this card came from the server, and every conclusion carries the source it
 * was resolved against.
 */

type DecisionInterpretationCardProps = {
  /** null while the analysis request is unfinished or has failed. */
  decision: Decision | null;
  palette: NewsPalette;
};

export function DecisionInterpretationCard({
  decision,
  palette,
}: DecisionInterpretationCardProps) {
  const block = decision?.newsInterpretation ?? null;

  return (
    <View
      style={[
        styles.card,
        { backgroundColor: palette.surface, borderColor: palette.line },
      ]}
      testID="decision-interpretation">
      <Text style={[styles.title, { color: palette.ink }]}>模型解读</Text>

      {decision === null ? (
        <Notice
          body="解读随分析结果一起返回；分析还没有回来，这里就不该有结论。"
          palette={palette}
          testID="decision-interpretation-pending"
          title="等待分析结果"
          tone="inset"
        />
      ) : block === null ? (
        <Notice
          body="解读接口尚未部署：这个后端只返回结论与引用，不返回逐条消息的模型解读。"
          palette={palette}
          testID="decision-interpretation-not-deployed"
          title="解读接口尚未部署"
          tone="notice"
        />
      ) : block.status === "not-requested" ? (
        <Notice
          body={
            block.reason
              ? serviceTextLabel(block.reason)
              : "本次请求没有要求模型解读。"
          }
          footer="这不是模型失败，是本次没有调用模型。"
          palette={palette}
          testID="decision-interpretation-not-requested"
          title="未请求解读"
          tone="inset"
        />
      ) : block.status === "unavailable" || block.value === null ? (
        <Notice
          body={
            block.reason
              ? serviceTextLabel(block.reason)
              : "模型这次没有给出可用的解读。"
          }
          footer="这是模型调用失败，不是「没有观点」；上面的原始报道仍然可读。"
          palette={palette}
          testID="decision-interpretation-unavailable"
          title="解读不可用"
          tone="notice"
        />
      ) : (
        <>
          <Text
            style={[styles.reading, { color: palette.ink }]}
            testID="decision-interpretation-reading">
            {block.value.crossSourceReading}
          </Text>

          {block.value.investmentImpact.map((claim, index) => (
            <View
              key={`${index}-${claim.statement}`}
              style={[styles.claim, { borderLeftColor: palette.accent }]}
              testID={`decision-interpretation-claim-${index}`}>
              <Text style={[styles.claimText, { color: palette.ink }]}>
                {claim.statement}
              </Text>
              <Text style={[styles.confidence, { color: palette.muted }]}>
                {`模型自评置信度 ${claim.confidence}`}
              </Text>
              {claim.citations.map((source) => (
                <Pressable
                  accessibilityHint="在浏览器中打开被引用的原始报道"
                  accessibilityLabel={`打开引用来源：${source.publisher}`}
                  accessibilityRole="link"
                  key={source.evidenceId}
                  onPress={() => {
                    void Linking.openURL(source.url);
                  }}
                  style={({ pressed }) => [
                    styles.citation,
                    {
                      backgroundColor: palette.surfaceInset,
                      borderColor: palette.line,
                    },
                    pressed && styles.pressed,
                  ]}
                  testID={`decision-interpretation-citation-${index}-${source.evidenceId}`}>
                  <Text style={[styles.publisher, { color: palette.accent }]}>
                    {`${source.publisher}${
                      source.isCounterEvidence ? " · 反证" : ""
                    } ↗`}
                  </Text>
                  {/* The quote is verbatim from the source and was verified
                      there before it left the server; printing it is what lets
                      the reader check the conclusion without leaving. */}
                  <Text style={[styles.quote, { color: palette.muted }]}>
                    {`「${source.quote}」`}
                  </Text>
                </Pressable>
              ))}
            </View>
          ))}

          {block.value.unknowns.length > 0 ? (
            <View
              style={[styles.notice, { backgroundColor: palette.surfaceInset }]}
              testID="decision-interpretation-unknowns">
              <Text style={[styles.noticeTitle, { color: palette.ink }]}>
                证据回答不了的部分
              </Text>
              {block.value.unknowns.map((item) => (
                <Text
                  key={item}
                  style={[styles.noticeBody, { color: palette.muted }]}>
                  {`· ${item}`}
                </Text>
              ))}
            </View>
          ) : null}
        </>
      )}

      <UsageLine palette={palette} usage={decision?.adviserUsage ?? null} />
    </View>
  );
}

function UsageLine({
  palette,
  usage,
}: {
  palette: NewsPalette;
  usage: AdviserUsage | null;
}) {
  // Absent means no call reported what it spent. A zero would claim the call
  // was measured and was free, which is a different statement about money.
  if (usage === null) return null;
  return (
    <Text
      style={[styles.cost, { color: palette.muted }]}
      testID="decision-interpretation-cost">
      {`本次模型调用 ${usage.inputTokens + usage.outputTokens} tokens · 实测花费 US$${usage.costUsd.toFixed(4)}${
        usage.model === null ? "" : ` · ${usage.model}`
      }`}
    </Text>
  );
}

function Notice({
  body,
  footer,
  palette,
  testID,
  title,
  tone,
}: {
  body: string;
  footer?: string;
  palette: NewsPalette;
  testID: string;
  title: string;
  tone: "inset" | "notice";
}) {
  return (
    <View
      style={[
        styles.notice,
        {
          backgroundColor:
            tone === "notice" ? palette.noticeSurface : palette.surfaceInset,
        },
      ]}
      testID={testID}>
      <Text style={[styles.noticeTitle, { color: palette.ink }]}>{title}</Text>
      <Text style={[styles.noticeBody, { color: palette.muted }]}>{body}</Text>
      {footer === undefined ? null : (
        <Text style={[styles.noticeBody, { color: palette.muted }]}>
          {footer}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    padding: spacing.md,
  },
  title: { fontSize: 12, fontWeight: "900", letterSpacing: 0.4 },
  notice: { borderRadius: radius.md, gap: spacing.xxs, padding: spacing.sm },
  noticeTitle: { fontSize: 12, fontWeight: "800", lineHeight: 17 },
  noticeBody: { fontSize: 12, lineHeight: 18 },
  reading: { fontSize: 13, lineHeight: 19 },
  claim: { borderLeftWidth: 2, gap: spacing.xs, paddingLeft: spacing.sm },
  claimText: { fontSize: 13, fontWeight: "700", lineHeight: 18 },
  confidence: { fontSize: 12, fontWeight: "700" },
  citation: {
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.xxs,
    minHeight: 44,
    padding: spacing.sm,
  },
  publisher: { fontSize: 12, fontWeight: "800" },
  quote: { fontSize: 12, lineHeight: 18 },
  pressed: { opacity: 0.68 },
  cost: { fontSize: 12, fontVariant: ["tabular-nums"], lineHeight: 18 },
});
