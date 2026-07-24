# Approved Dashboard Visual Realignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the verbose white-card Dashboard with a native React Native translation of the approved compact browser prototype, preserve every evidence and safety path through progressive disclosure, and install the verified app on the user's physical iPhone.

**Architecture:** Keep the existing `DashboardSnapshot`, fixture repository, app state, routes, and evidence records. Replace only the Dashboard presentation layer with focused native components: compact header, segmented horizon control, navy market-regime hero, compact priority alert, three-column watchlist pulse, ranked candidate rows, and one reusable native detail sheet for supporting evidence. Lock the hierarchy with interaction tests and two iPhone-size screenshot baselines before completing an Xcode Personal Team device install.

**Tech Stack:** Expo SDK 57, React Native 0.86, React 19.2, Expo Router, TypeScript 6 strict mode, `react-native-svg` 15.15, React Native Testing Library, Jest Expo, Xcode 26.6, CocoaPods 1.17, Node.js 22.13 or newer.

## Global Constraints

- Visual authority: `docs/design-reference/approved-browser-prototypes/ios-dashboard-demo-v1.html`.
- Written authority: `docs/superpowers/specs/2026-07-24-approved-prototype-visual-realignment-design.md`.
- Build native React Native views; do not embed prototype HTML in a WebView.
- Preserve existing fixture, evidence, routing, state, and objective-score behavior.
- Supporting evidence must remain reachable through progressive disclosure.
- Show `演示数据 · 非实时行情` once in the Dashboard header; do not repeat amber `演示` markers on every card.
- The first 390 × 844 viewport must contain the market hero, priority alert, and watchlist heading.
- The nine full market drivers, counter-evidence, invalidation, and candidate research memos must not be expanded by default.
- All interactive controls retain a minimum 44-point target and useful accessibility labels.
- No live market, news, moomoo, LLM, authentication, cloud sync, or broker API calls.
- No order-submit, order-edit, or order-cancel action may exist.
- Do not change objective scores or confidence based on user preference.
- Do not copy proprietary assets or code from moomoo, 同花顺, or paid indicators.
- Do not commit Xcode signing credentials, provisioning profiles, or generated `apps/mobile/ios` content.
- Free Personal Team installation is temporary and normally requires re-signing after about seven days.

## Scope

This plan repairs the Dashboard that currently exists on the remote branch,
locks its approved visual language, and delivers that build to the physical
iPhone. Stock detail, full candlestick, and adviser visual translations are
separate follow-on implementation plans after the user approves the repaired
native Dashboard; their prototype sources are already preserved and must not
be redesigned independently.

## Execution Ruling

The user selected the green-branch TDD option after pre-flight review. Execute
Tasks 2–5 first using their focused red/green cycles. Then execute Task 1 and
Task 6 as one combined SDD unit: add the full Dashboard contract tests, record
their expected RED output, implement the composition, and commit only after
the focused and full Dashboard suites are GREEN. Do not publish an
intentionally failing intermediate commit.

## File Structure

```text
apps/mobile/src/
├── components/
│   ├── dashboard/
│   │   ├── DashboardDetailSheet.tsx    # One native sheet for full evidence and safety detail
│   │   ├── DashboardHeader.tsx         # Session, greeting, demo status, search, alerts
│   │   ├── DashboardSectionHeader.tsx  # Compact section title and 44-point action
│   │   ├── MarketRegimeHero.tsx        # Navy focal card with score and four collapsed drivers
│   │   ├── PriorityAlertCard.tsx       # Compact actionable-research summary
│   │   ├── WatchlistStrip.tsx          # Three-column pulse cards and sparklines
│   │   ├── CandidateList.tsx           # Compact ranked candidate rows
│   │   └── __tests__/
│   │       ├── DashboardDetailSheet.test.tsx
│   │       └── MarketRegimeHero.test.tsx
│   └── ui/
│       ├── ScoreRing.tsx               # SVG progress ring used by market hero
│       ├── MiniSparkline.tsx            # Deterministic demo sparkline
│       └── __tests__/ScoreRing.test.tsx
├── screens/
│   ├── DashboardScreen.tsx             # Composition and detail-sheet state
│   └── __tests__/
│       ├── DashboardScreen.test.tsx
│       └── DashboardVisualContract.test.tsx
└── theme/tokens.ts                     # Approved prototype colors, spacing, radius, shadow

docs/design-reference/
├── baselines/
│   ├── dashboard-approved-reference.png
│   ├── dashboard-native-390x844.png
│   └── dashboard-native-430x932.png
└── dashboard-visual-regression.md
```

---

### Task 1: Pin the compact Dashboard contract with failing tests

**Files:**
- Create: `apps/mobile/src/screens/__tests__/DashboardVisualContract.test.tsx`
- Modify: `apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx`

**Interfaces:**
- Consumes: `DashboardScreen`, `AppStateProvider`, current fixture repository
- Produces: test IDs `dashboard-header`, `market-regime-hero`, `priority-alert-card`, `watchlist-grid`, `candidate-list`, and button label `查看完整依据`

- [ ] **Step 1: Add the failing visual-contract test**

Create `apps/mobile/src/screens/__tests__/DashboardVisualContract.test.tsx`:

```tsx
import { beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { AppStateProvider } from "@/state/AppStateProvider";

import { DashboardScreen } from "../DashboardScreen";

const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  mockPush.mockClear();
});

it("renders the approved compact hierarchy and hides research detail by default", async () => {
  const view = render(
    <AppStateProvider>
      <DashboardScreen />
    </AppStateProvider>,
  );

  await waitFor(() => expect(view.getByTestId("market-regime-hero")).toBeTruthy());

  expect(view.getByTestId("dashboard-header")).toBeTruthy();
  expect(view.getByTestId("priority-alert-card")).toBeTruthy();
  expect(view.getByTestId("watchlist-grid")).toBeTruthy();
  expect(view.getByTestId("candidate-list")).toBeTruthy();
  expect(view.getAllByText("演示数据 · 非实时行情")).toHaveLength(1);

  expect(view.queryByText("为什么")).toBeNull();
  expect(view.queryByText("最强反证")).toBeNull();
  expect(view.queryByText("固定刻度 −100 至 +100")).toBeNull();
  expect(view.queryByText("宏观、信用、能源与商品")).toBeNull();
  expect(view.queryByText("流动性与相关性压力")).toBeNull();

  await fireEvent.press(view.getByRole("button", { name: "查看完整依据" }));
  expect(view.getByText("市场完整依据")).toBeTruthy();
  expect(view.getByText("最强反证")).toBeTruthy();
  expect(view.getByText("失效条件")).toBeTruthy();
  expect(view.getByText("宏观、信用、能源与商品")).toBeTruthy();
});

it("keeps alert, watchlist, and candidates actionable without expanding memos", async () => {
  const view = render(
    <AppStateProvider>
      <DashboardScreen />
    </AppStateProvider>,
  );

  await waitFor(() => expect(view.getByText("NVDA 接近量价确认区")).toBeTruthy());

  expect(view.queryByText("催化、量价和短线市场环境同向。")).toBeNull();
  expect(view.queryByText("估值拥挤，若成交量未确认则动量可能快速反转。")).toBeNull();

  await fireEvent.press(view.getByRole("button", { name: /查看 TSLA 行情详情/ }));
  expect(mockPush).toHaveBeenLastCalledWith({
    pathname: "/stocks/[symbol]",
    params: { symbol: "TSLA" },
  });

  await fireEvent.press(view.getByRole("button", { name: /查看 NVDA 候选依据/ }));
  expect(view.getByText("NVDA 候选依据")).toBeTruthy();
  expect(view.getByText("最强反例")).toBeTruthy();
  expect(view.getByText("收盘跌破 136.40 且大盘趋势同步转弱。")).toBeTruthy();
});
```

- [ ] **Step 2: Run the new test and verify the current design fails**

Run:

```bash
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm test -- src/screens/__tests__/DashboardVisualContract.test.tsx
```

Expected: FAIL because the current Dashboard has none of the new hierarchy test IDs, repeats `演示`, and expands all research detail.

- [ ] **Step 3: Rewrite obsolete expectations in the existing Dashboard test**

In `DashboardScreen.test.tsx`, retain horizon switching, evidence content,
navigation, accessibility, and objective fixture checks. Remove expectations
that require all nine drivers, every counter-case, and every invalidation to be
visible before interaction. Replace the opening assertions with:

```tsx
expect(view.getByText("谨慎偏多")).toBeTruthy();
expect(view.getByLabelText("市场评分 61")).toBeTruthy();
expect(view.getByText("今日建议")).toBeTruthy();
expect(view.getByText("需要关注")).toBeTruthy();
expect(view.getByText("我的关注")).toBeTruthy();
expect(view.getByText("潜力候选")).toBeTruthy();
expect(view.queryByText("最强反证")).toBeNull();
```

Move existing evidence assertions after:

```tsx
await fireEvent.press(view.getByRole("button", { name: "查看完整依据" }));
```

- [ ] **Step 4: Run both Dashboard tests and preserve the red state**

Run:

```bash
cd apps/mobile
npm test -- \
  src/screens/__tests__/DashboardVisualContract.test.tsx \
  src/screens/__tests__/DashboardScreen.test.tsx
```

Expected: FAIL only on missing compact components and new progressive-disclosure behavior, not on TypeScript or test syntax.

- [ ] **Step 5: Commit the contract tests**

```bash
git add \
  apps/mobile/src/screens/__tests__/DashboardVisualContract.test.tsx \
  apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx
git commit -m "test: pin approved dashboard visual hierarchy"
```

---

### Task 2: Add approved visual tokens and native chart primitives

**Files:**
- Modify: `apps/mobile/src/theme/tokens.ts`
- Create: `apps/mobile/src/components/ui/ScoreRing.tsx`
- Create: `apps/mobile/src/components/ui/MiniSparkline.tsx`
- Create: `apps/mobile/src/components/ui/__tests__/ScoreRing.test.tsx`

**Interfaces:**
- Consumes: `score: number`, `Direction`
- Produces: `ScoreRing({ score, size?, strokeWidth? })`, `MiniSparkline({ direction, width?, height? })`, `clampScore(score): number`

- [ ] **Step 1: Write the failing ScoreRing test**

```tsx
import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { clampScore, ScoreRing } from "../ScoreRing";

it("clamps the market score and exposes it accessibly", () => {
  expect(clampScore(-20)).toBe(0);
  expect(clampScore(61)).toBe(61);
  expect(clampScore(140)).toBe(100);

  const view = render(<ScoreRing score={61} />);
  expect(view.getByLabelText("市场评分 61")).toBeTruthy();
  expect(view.getByText("61")).toBeTruthy();
});
```

- [ ] **Step 2: Run the primitive test and verify it fails**

```bash
cd apps/mobile
npm test -- src/components/ui/__tests__/ScoreRing.test.tsx
```

Expected: FAIL because `ScoreRing` does not exist.

- [ ] **Step 3: Expand tokens to match the approved prototype**

Replace `tokens.ts` with the existing colors plus these exact additions:

```ts
export const colors = {
  background: "#EEF1F5",
  backgroundRaised: "#F7F9FC",
  card: "#FFFFFF",
  ink: "#0D1729",
  muted: "#718096",
  line: "#DCE2EB",
  navy: "#0B1424",
  navyRaised: "#111E33",
  navyLine: "#223A60",
  navyMuted: "#AABBD3",
  navyEyebrow: "#8DA2C2",
  blue: "#4285FF",
  blueBright: "#77B7FF",
  blueSoft: "#EAF2FF",
  green: "#20BF79",
  greenSoft: "#E8F8F0",
  red: "#EF5B62",
  redSoft: "#FFEDEF",
  amber: "#F4AD42",
  amberSoft: "#FFF4DF",
  purple: "#7860D9",
  purpleSoft: "#F0EDFF",
} as const;

export const spacing = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 17,
  round: 32,
  pill: 999,
} as const;

export const shadow = {
  card: {
    shadowColor: "#23324A",
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.05,
    shadowRadius: 12,
    elevation: 1,
  },
  hero: {
    shadowColor: "#0D1D37",
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.18,
    shadowRadius: 25,
    elevation: 4,
  },
} as const;
```

- [ ] **Step 4: Implement the SVG score ring**

Create `ScoreRing.tsx`:

```tsx
import { StyleSheet, Text, View } from "react-native";
import Svg, { Circle } from "react-native-svg";

import { colors } from "@/theme/tokens";

type ScoreRingProps = {
  score: number;
  size?: number;
  strokeWidth?: number;
};

export const clampScore = (score: number) =>
  Math.min(100, Math.max(0, score));

export function ScoreRing({
  score,
  size = 54,
  strokeWidth = 6,
}: ScoreRingProps) {
  const normalized = clampScore(score);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = circumference * (normalized / 100);

  return (
    <View
      accessibilityLabel={`市场评分 ${normalized}`}
      style={[styles.container, { height: size, width: size }]}>
      <Svg height={size} width={size}>
        <Circle
          cx={size / 2}
          cy={size / 2}
          fill={colors.navyRaised}
          r={radius}
          stroke="#243653"
          strokeWidth={strokeWidth}
        />
        <Circle
          cx={size / 2}
          cy={size / 2}
          fill="none"
          r={radius}
          rotation="-90"
          origin={`${size / 2}, ${size / 2}`}
          stroke={colors.green}
          strokeDasharray={`${progress} ${circumference - progress}`}
          strokeLinecap="round"
          strokeWidth={strokeWidth}
        />
      </Svg>
      <Text style={styles.score}>{normalized}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: "center", justifyContent: "center" },
  score: {
    color: "#EFF6FF",
    fontSize: 15,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
    position: "absolute",
  },
});
```

- [ ] **Step 5: Implement the deterministic demo sparkline**

Create `MiniSparkline.tsx`:

```tsx
import type { Direction } from "@/domain/models";
import { colors } from "@/theme/tokens";
import Svg, { Path } from "react-native-svg";

type MiniSparklineProps = {
  direction: Direction;
  width?: number;
  height?: number;
};

const paths: Record<Direction, string> = {
  bullish: "M1 18 L10 15 L19 16 L28 9 L37 12 L46 5 L55 8 L64 2",
  neutral: "M1 12 L10 10 L19 13 L28 9 L37 12 L46 10 L55 11 L64 8",
  bearish: "M1 3 L10 7 L19 5 L28 12 L37 9 L46 16 L55 14 L64 20",
};

const tones: Record<Direction, string> = {
  bullish: colors.green,
  neutral: colors.muted,
  bearish: colors.red,
};

export function MiniSparkline({
  direction,
  width = 66,
  height = 22,
}: MiniSparklineProps) {
  return (
    <Svg
      accessibilityElementsHidden
      height={height}
      importantForAccessibility="no-hide-descendants"
      viewBox="0 0 66 22"
      width={width}>
      <Path
        d={paths[direction]}
        fill="none"
        stroke={tones[direction]}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
      />
    </Svg>
  );
}
```

- [ ] **Step 6: Run primitive tests, typecheck, and lint**

```bash
cd apps/mobile
npm test -- src/components/ui/__tests__/ScoreRing.test.tsx
npm run typecheck
npm run lint
```

Expected: all three commands exit 0.

- [ ] **Step 7: Commit primitives**

```bash
git add \
  apps/mobile/src/theme/tokens.ts \
  apps/mobile/src/components/ui/ScoreRing.tsx \
  apps/mobile/src/components/ui/MiniSparkline.tsx \
  apps/mobile/src/components/ui/__tests__/ScoreRing.test.tsx
git commit -m "feat: add approved dashboard visual primitives"
```

---

### Task 3: Add the reusable progressive-disclosure detail sheet

**Files:**
- Create: `apps/mobile/src/components/dashboard/DashboardDetailSheet.tsx`
- Create: `apps/mobile/src/components/dashboard/__tests__/DashboardDetailSheet.test.tsx`

**Interfaces:**
- Consumes: `visible`, `title`, `sections`, `citations`, `onClose`
- Produces: `DetailSection`, `DashboardDetailSheet`

```ts
export type DetailSection = {
  label: string;
  body: string;
};
```

- [ ] **Step 1: Write the failing detail-sheet test**

```tsx
import { expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";

import { DashboardDetailSheet } from "../DashboardDetailSheet";

it("hides detail until opened and closes through a 44-point action", () => {
  const onClose = jest.fn();
  const hidden = render(
    <DashboardDetailSheet
      citations={[]}
      onClose={onClose}
      sections={[{ label: "最强反证", body: "市场广度尚未确认" }]}
      title="市场完整依据"
      visible={false}
    />,
  );
  expect(hidden.queryByText("最强反证")).toBeNull();

  const visible = render(
    <DashboardDetailSheet
      citations={[]}
      onClose={onClose}
      sections={[{ label: "最强反证", body: "市场广度尚未确认" }]}
      title="市场完整依据"
      visible
    />,
  );
  expect(visible.getByText("最强反证")).toBeTruthy();
  fireEvent.press(visible.getByRole("button", { name: "关闭市场完整依据" }));
  expect(onClose).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
cd apps/mobile
npm test -- \
  src/components/dashboard/__tests__/DashboardDetailSheet.test.tsx
```

Expected: FAIL because the sheet does not exist.

- [ ] **Step 3: Implement the native modal sheet**

Create `DashboardDetailSheet.tsx` with this public structure:

```tsx
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { CitationRow } from "@/components/evidence/CitationRow";
import type { Citation } from "@/domain/models";
import { colors, radius, spacing } from "@/theme/tokens";

export type DetailSection = { label: string; body: string };

type DashboardDetailSheetProps = {
  visible: boolean;
  title: string;
  sections: DetailSection[];
  citations: Citation[];
  onClose(): void;
};

export function DashboardDetailSheet({
  visible,
  title,
  sections,
  citations,
  onClose,
}: DashboardDetailSheetProps) {
  if (!visible) return null;

  return (
    <Modal
      animationType="slide"
      onRequestClose={onClose}
      presentationStyle="pageSheet"
      visible>
      <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
        <View style={styles.header}>
          <Text style={styles.title}>{title}</Text>
          <Pressable
            accessibilityLabel={`关闭${title}`}
            accessibilityRole="button"
            onPress={onClose}
            style={styles.close}>
            <Text style={styles.closeText}>完成</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={styles.content}>
          <Text style={styles.demo}>演示数据 · 非实时行情</Text>
          {sections.map((section) => (
            <View key={section.label} style={styles.section}>
              <Text style={styles.label}>{section.label}</Text>
              <Text style={styles.body}>{section.body}</Text>
            </View>
          ))}
          <Text style={styles.citationHeading}>引用</Text>
          {citations.length ? (
            citations.map((citation) => (
              <CitationRow citation={citation} key={citation.id} />
            ))
          ) : (
            <Text style={styles.empty}>暂无可用引用</Text>
          )}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.backgroundRaised, flex: 1 },
  header: {
    alignItems: "center",
    borderBottomColor: colors.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
  },
  title: { color: colors.ink, flex: 1, fontSize: 18, fontWeight: "800" },
  close: { alignItems: "center", justifyContent: "center", minHeight: 44, paddingLeft: spacing.lg },
  closeText: { color: colors.blue, fontSize: 15, fontWeight: "800" },
  content: { gap: spacing.md, padding: spacing.lg, paddingBottom: spacing.xl },
  demo: { alignSelf: "flex-start", color: colors.amber, fontSize: 11, fontWeight: "800" },
  section: { backgroundColor: colors.card, borderRadius: radius.md, padding: spacing.md },
  label: { color: colors.ink, fontSize: 13, fontWeight: "800" },
  body: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: spacing.xs },
  citationHeading: { color: colors.ink, fontSize: 15, fontWeight: "800", marginTop: spacing.sm },
  empty: { color: colors.muted, fontSize: 13 },
});
```

- [ ] **Step 4: Run the sheet test and complete checks**

```bash
cd apps/mobile
npm test -- \
  src/components/dashboard/__tests__/DashboardDetailSheet.test.tsx
npm run typecheck
npm run lint
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit the detail sheet**

```bash
git add \
  apps/mobile/src/components/dashboard/DashboardDetailSheet.tsx \
  apps/mobile/src/components/dashboard/__tests__/DashboardDetailSheet.test.tsx
git commit -m "feat: add dashboard evidence detail sheet"
```

---

### Task 4: Build the compact header and navy market-regime hero

**Files:**
- Create: `apps/mobile/src/components/dashboard/DashboardHeader.tsx`
- Create: `apps/mobile/src/components/dashboard/MarketRegimeHero.tsx`
- Create: `apps/mobile/src/components/dashboard/__tests__/MarketRegimeHero.test.tsx`
- Modify: `apps/mobile/src/components/ui/HorizonSwitch.tsx`

**Interfaces:**
- Consumes: session, updated time, data health, market score, conclusion, rationale, advice, four leading drivers
- Produces: `DashboardHeader`, `MarketRegimeHero`, `onOpenDetail()`

- [ ] **Step 1: Write the failing hero test**

```tsx
import { expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";

import { dashboardFixtures } from "@/fixtures/dashboard";

import { MarketRegimeHero } from "../MarketRegimeHero";

it("shows one decision frame and collapses the full research packet", () => {
  const onOpenDetail = jest.fn();
  const view = render(
    <MarketRegimeHero
      advice={dashboardFixtures.short.marketAdvice}
      conclusion={dashboardFixtures.short.marketConclusion}
      drivers={dashboardFixtures.short.marketDrivers}
      onOpenDetail={onOpenDetail}
      rationale={dashboardFixtures.short.marketRationale}
      score={dashboardFixtures.short.marketScore}
      updatedAt={dashboardFixtures.short.updatedAt}
    />,
  );

  expect(view.getByText("谨慎偏多")).toBeTruthy();
  expect(view.getByLabelText("市场评分 61")).toBeTruthy();
  expect(view.getAllByTestId("market-driver-chip")).toHaveLength(4);
  expect(view.queryByText("宏观、信用、能源与商品")).toBeNull();

  fireEvent.press(view.getByRole("button", { name: "查看完整依据" }));
  expect(onOpenDetail).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Run the hero test and verify it fails**

```bash
cd apps/mobile
npm test -- \
  src/components/dashboard/__tests__/MarketRegimeHero.test.tsx
```

Expected: FAIL because the compact hero does not exist.

- [ ] **Step 3: Implement `DashboardHeader`**

Create a header with this interface and visible copy:

```tsx
import type { DataHealth } from "@/domain/models";

const healthLabels: Record<DataHealth, string> = {
  fresh: "数据新鲜",
  stale: "数据延迟",
  conflict: "数据冲突",
  insufficient: "数据不足",
};

type DashboardHeaderProps = {
  marketSession: string;
  health: DataHealth;
  updatedAt: string;
  onSearch(): void;
  onAlerts(): void;
};
```

Render:

```tsx
<View testID="dashboard-header">
  <View>
    <Text>
      {marketSession} · {healthLabels[health]} · 更新 {updatedAt.slice(11, 16)}
    </Text>
    <Text>早上好，Franz</Text>
    <Text>演示数据 · 非实时行情</Text>
  </View>
  <View>
    <Pressable accessibilityLabel="搜索股票" style={styles.iconButton}>
      <SymbolView name="magnifyingglass" size={18} tintColor={colors.ink} />
    </Pressable>
    <Pressable accessibilityLabel="查看提醒" style={styles.iconButton}>
      <SymbolView name="bell" size={18} tintColor={colors.ink} />
    </Pressable>
  </View>
</View>
```

Use `fontSize: 10` for the session, `18` for the greeting, `10` for demo
status, 32-point visible circles with `minHeight: 44` and `minWidth: 44`
press targets.

- [ ] **Step 4: Implement `MarketRegimeHero`**

Create the component with this exact prop contract:

```tsx
type MarketRegimeHeroProps = {
  score: number;
  conclusion: string;
  rationale: string;
  advice: string;
  drivers: MarketDriver[];
  updatedAt: string;
  onOpenDetail(): void;
};
```

Use:

```tsx
const compactDrivers = drivers.slice(0, 4);
```

The visible hierarchy must be:

```tsx
<View testID="market-regime-hero" style={styles.hero}>
  <View style={styles.topRow}>
    <View style={styles.copy}>
      <Text style={styles.eyebrow}>市场情绪结论 · 最近更新</Text>
      <Text style={styles.conclusion}>{conclusion}</Text>
      <Text numberOfLines={2} style={styles.rationale}>{rationale}</Text>
    </View>
    <ScoreRing score={score} />
  </View>
  <View style={styles.playbook}>
    <Text style={styles.playbookLabel}>今日建议</Text>
    <Text numberOfLines={3} style={styles.advice}>{advice}</Text>
  </View>
  <View style={styles.driverRow}>
    {compactDrivers.map((driver) => (
      <View key={driver.id} style={styles.driverChip} testID="market-driver-chip">
        <Text style={styles.driverText}>
          {driver.label} {driver.score > 0 ? "+" : ""}{driver.score}
        </Text>
      </View>
    ))}
  </View>
  <Pressable
    accessibilityLabel="查看完整依据"
    accessibilityRole="button"
    onPress={onOpenDetail}
    style={styles.detailAction}>
    <Text style={styles.detailActionText}>查看依据 ›</Text>
  </Pressable>
</View>
```

Required hero styles:

```ts
hero: {
  backgroundColor: colors.navy,
  borderRadius: radius.lg,
  gap: spacing.sm,
  padding: 13,
  ...shadow.hero,
},
eyebrow: {
  color: colors.navyEyebrow,
  fontSize: 9,
  fontWeight: "800",
  letterSpacing: 0.8,
},
conclusion: { color: "#EFF6FF", fontSize: 20, fontWeight: "800", marginTop: 4 },
rationale: { color: colors.navyMuted, fontSize: 11, lineHeight: 16, marginTop: 3 },
playbook: {
  backgroundColor: "rgba(53, 113, 194, 0.18)",
  borderColor: "rgba(79, 155, 255, 0.28)",
  borderRadius: 10,
  borderWidth: StyleSheet.hairlineWidth,
  flexDirection: "row",
  gap: spacing.xs,
  paddingHorizontal: 10,
  paddingVertical: 9,
},
playbookLabel: { color: colors.blueBright, fontSize: 10, fontWeight: "800" },
advice: { color: "#D7E4F5", flex: 1, fontSize: 10, lineHeight: 15 },
driverChip: {
  backgroundColor: "rgba(255,255,255,0.07)",
  borderRadius: 6,
  paddingHorizontal: 6,
  paddingVertical: 4,
},
driverText: { color: "#D7E4F5", fontSize: 8, fontWeight: "700" },
```

- [ ] **Step 5: Make the horizon switch compact without shrinking touch targets**

Change only visible sizing:

```ts
switch: {
  backgroundColor: "#E4E9F1",
  borderRadius: 10,
  flexDirection: "row",
  padding: 3,
},
option: {
  alignItems: "center",
  borderRadius: 8,
  flex: 1,
  minHeight: 44,
  justifyContent: "center",
  paddingHorizontal: 4,
},
label: { color: colors.muted, fontSize: 10, fontWeight: "700" },
```

- [ ] **Step 6: Run hero, horizon, type, and lint checks**

```bash
cd apps/mobile
npm test -- \
  src/components/dashboard/__tests__/MarketRegimeHero.test.tsx \
  src/components/ui/__tests__/HorizonSwitch.test.tsx
npm run typecheck
npm run lint
```

Expected: all commands exit 0.

- [ ] **Step 7: Commit header and hero**

```bash
git add \
  apps/mobile/src/components/dashboard/DashboardHeader.tsx \
  apps/mobile/src/components/dashboard/MarketRegimeHero.tsx \
  apps/mobile/src/components/dashboard/__tests__/MarketRegimeHero.test.tsx \
  apps/mobile/src/components/ui/HorizonSwitch.tsx
git commit -m "feat: restore approved dashboard focal hierarchy"
```

---

### Task 5: Compact the priority alert and watchlist pulse

**Files:**
- Create: `apps/mobile/src/components/dashboard/DashboardSectionHeader.tsx`
- Modify: `apps/mobile/src/components/dashboard/PriorityAlertCard.tsx`
- Modify: `apps/mobile/src/components/dashboard/WatchlistStrip.tsx`
- Modify: `apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx`

**Interfaces:**
- Consumes: existing `AlertThread`, `WatchlistQuote[]`, `MiniSparkline`
- Produces: `DashboardSectionHeader`, compact alert with `onOpenDetail`, three-column `watchlist-grid`

- [ ] **Step 1: Add failing compact-card assertions**

Add:

```tsx
const alert = view.getByTestId("priority-alert-card");
expect(alert).toBeTruthy();
expect(view.getByText("证据 5 · 反证 2 · 新鲜")).toBeTruthy();
expect(view.queryByText("来源覆盖：盘中报价、期权与量价演示快照")).toBeNull();
expect(view.queryByText("顾问有限调整 +2 · 不能独立触发")).toBeNull();
expect(view.queryByText("收盘跌破 136.40")).toBeNull();

expect(view.getByTestId("watchlist-grid")).toBeTruthy();
expect(view.queryByTestId("watchlist-scroll")).toBeNull();
expect(view.getAllByTestId("watchlist-quote")).toHaveLength(3);
```

- [ ] **Step 2: Run the Dashboard test and verify failure**

```bash
cd apps/mobile
npm test -- src/screens/__tests__/DashboardScreen.test.tsx
```

Expected: FAIL because alert detail remains expanded and watchlist uses a horizontal scroll.

- [ ] **Step 3: Replace alert markup with the approved compact card**

Change the alert prop from `onOpenEvidence(title, citationIds)` to
`onOpenDetail()` and render:

```tsx
<View testID="priority-alert-card" style={styles.card}>
  <Pressable
    accessibilityLabel={`查看 ${alert.symbol} 提醒详情：${alert.title}`}
    accessibilityRole="button"
    onPress={onPress}
    style={styles.mainAction}>
    <View style={styles.copy}>
      <View style={styles.tickerLine}>
        <Text style={styles.symbol}>{alert.symbol}</Text>
        <Text style={styles.badge}>{alert.currentState}</Text>
      </View>
      <Text numberOfLines={1} style={styles.title}>{alert.title}</Text>
      <Text numberOfLines={2} style={styles.summary}>{alert.summary}</Text>
      <Text style={styles.meta}>
        证据 {alert.evidenceCount} · 反证 {alert.counterEvidenceCount} ·
        {" "}{freshnessLabel[alert.sourceFreshness]}
      </Text>
    </View>
    <View style={styles.scorePill}>
      <Text style={styles.score}>
        {alert.baseScoreContribution > 0 ? "+" : ""}
        {alert.baseScoreContribution}
      </Text>
      <Text style={styles.scoreLabel}>基础贡献</Text>
    </View>
  </Pressable>
  <Pressable
    accessibilityLabel={`查看 ${alert.symbol} 提醒依据`}
    accessibilityRole="button"
    onPress={onOpenDetail}
    style={styles.evidenceAction}>
    <Text style={styles.evidenceText}>依据 ›</Text>
  </Pressable>
</View>
```

The full source coverage, adviser adjustment, timestamps, and invalidation are
passed to `DashboardDetailSheet` by `DashboardScreen` in Task 6.

- [ ] **Step 4: Add the reusable compact Dashboard section header**

Create `DashboardSectionHeader.tsx`:

```tsx
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors } from "@/theme/tokens";

type DashboardSectionHeaderProps = {
  title: string;
  actionLabel: string;
  onAction(): void;
};

export function DashboardSectionHeader({
  title,
  actionLabel,
  onAction,
}: DashboardSectionHeaderProps) {
  return (
    <View style={styles.row}>
      <Text style={styles.title}>{title}</Text>
      <Pressable
        accessibilityLabel={actionLabel}
        accessibilityRole="button"
        onPress={onAction}
        style={styles.action}>
        <Text style={styles.actionText}>{actionLabel}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  title: { color: colors.ink, fontSize: 12, fontWeight: "800" },
  action: { alignItems: "flex-end", justifyContent: "center", minHeight: 44 },
  actionText: { color: colors.blue, fontSize: 10, fontWeight: "700" },
});
```

- [ ] **Step 5: Replace horizontal watchlist rows with three compact cards**

Remove `ScrollView`. Render:

```tsx
<View accessibilityLabel="自选行情，演示">
  <DashboardSectionHeader
    actionLabel="来自 moomoo ›"
    onAction={() => undefined}
    title="我的关注"
  />
  <View style={styles.grid} testID="watchlist-grid">
    {quotes.slice(0, 3).map((quote) => (
      <Pressable
        accessibilityLabel={`查看 ${quote.symbol} 行情详情：$${quote.price.toFixed(2)}，${quote.changePercent >= 0 ? "+" : ""}${quote.changePercent.toFixed(2)}%，${directionCopy[quote.direction]}，当前脉冲 ${quote.summary}`}
        accessibilityRole="button"
        key={quote.symbol}
        onPress={() => onPress(quote.symbol)}
        style={styles.quote}
        testID="watchlist-quote">
        <View style={styles.quoteTop}>
          <Text style={styles.symbol}>{quote.symbol}</Text>
          <Text style={[styles.change, toneFor(quote.direction)]}>
            {quote.changePercent >= 0 ? "+" : ""}
            {quote.changePercent.toFixed(1)}%
          </Text>
        </View>
        <MiniSparkline direction={quote.direction} width={74} />
        <Text numberOfLines={1} style={styles.pulse}>{quote.summary}</Text>
      </Pressable>
    ))}
  </View>
</View>
```

Use `flex: 1`, `minWidth: 0`, `gap: 7`, `padding: 9`, `borderRadius: 12`, and
`minHeight: 86` so three cards fit at 390 points.

- [ ] **Step 6: Run the Dashboard test and full checks**

```bash
cd apps/mobile
npm test -- src/screens/__tests__/DashboardScreen.test.tsx
npm run typecheck
npm run lint
```

Expected: all commands exit 0.

- [ ] **Step 7: Commit compact cards**

```bash
git add \
  apps/mobile/src/components/dashboard/DashboardSectionHeader.tsx \
  apps/mobile/src/components/dashboard/PriorityAlertCard.tsx \
  apps/mobile/src/components/dashboard/WatchlistStrip.tsx \
  apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx
git commit -m "feat: compact dashboard alert and watchlist"
```

---

### Task 6: Compact candidates and compose the complete approved Dashboard

**Files:**
- Modify: `apps/mobile/src/components/dashboard/CandidateList.tsx`
- Modify: `apps/mobile/src/screens/DashboardScreen.tsx`
- Modify: `apps/mobile/src/components/ui/Screen.tsx`
- Delete: `apps/mobile/src/components/dashboard/MarketPlaybookCard.tsx`
- Modify: `apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx`
- Modify: `apps/mobile/src/screens/__tests__/DashboardVisualContract.test.tsx`

**Interfaces:**
- Consumes: `DashboardDetailSheet`, new header, new hero, compact alert/watchlist, existing repository and router
- Produces: final approved Dashboard composition and a discriminated local detail-sheet state

- [ ] **Step 1: Replace expanded candidate memos with ranked rows**

Change the prop contract:

```ts
type CandidateListProps = {
  candidates: Candidate[];
  onPress(symbol: string): void;
  onOpenEvidence(candidate: Candidate): void;
  onOpenDiscover(): void;
};
```

Render only:

```tsx
<View accessibilityLabel="潜力候选，演示" style={styles.section} testID="candidate-list">
  <DashboardSectionHeader
    actionLabel="发现器 ›"
    onAction={onOpenDiscover}
    title="潜力候选"
  />
  {candidates.slice(0, 2).map((candidate, index) => (
    <View key={candidate.symbol} style={styles.row}>
      <Pressable
        accessibilityLabel={`查看 ${candidate.symbol} 候选详情`}
        accessibilityRole="button"
        onPress={() => onPress(candidate.symbol)}
        style={styles.mainAction}>
        <View style={styles.logo}>
          <Text style={styles.logoText}>{candidate.symbol.slice(0, 2)}</Text>
        </View>
        <View style={styles.copy}>
          <Text style={styles.symbol}>
            {candidate.symbol} · {stateLabels[candidate.state]}
          </Text>
          <Text numberOfLines={1} style={styles.catalyst}>{candidate.catalyst}</Text>
        </View>
      </Pressable>
      <Pressable
        accessibilityLabel={`查看 ${candidate.symbol} 候选依据`}
        accessibilityRole="button"
        onPress={() => onOpenEvidence(candidate)}
        style={styles.rankAction}>
        <Text style={styles.rank}>{candidate.score}</Text>
        <Text style={styles.evidenceCount}>证据 {candidate.evidenceCount}</Text>
      </Pressable>
    </View>
  ))}
</View>
```

Use a 34-point visible monogram, 44-point minimum main/rank targets, 12-point
row radius, and `8` vertical padding.

- [ ] **Step 2: Add a typed detail-sheet state in `DashboardScreen`**

Add:

```tsx
type DetailState = {
  title: string;
  sections: DetailSection[];
  citations: Citation[];
} | null;

const [detail, setDetail] = useState<DetailState>(null);

const openDetail = (
  title: string,
  sections: DetailSection[],
  citationIds: string[],
) => {
  setDetail({
    title,
    sections,
    citations: fixtureRepository.getCitations(citationIds),
  });
};
```

Market sections:

```tsx
const marketSections: DetailSection[] = [
  { label: "为什么", body: snapshot.marketRationale },
  { label: "当前策略 / 风险姿态", body: snapshot.marketRiskPosture },
  { label: "最强反证", body: snapshot.contradictions.join("\n") },
  { label: "失效条件", body: snapshot.marketInvalidation },
  ...snapshot.marketDrivers.map((driver) => ({
    label: driver.label,
    body: `${driver.conclusion} · 评分 ${driver.score > 0 ? "+" : ""}${driver.score} · 新鲜度 ${driver.freshness}`,
  })),
];
```

Candidate sections:

```tsx
const openCandidateEvidence = (candidate: Candidate) =>
  openDetail(
    `${candidate.symbol} 候选依据`,
    [
      { label: "原因", body: candidate.reason },
      { label: "最强反例", body: candidate.counterCase },
      { label: "失效条件", body: candidate.invalidation },
      {
        label: "证据状态",
        body: `证据 ${candidate.evidenceCount} · 反证 ${candidate.counterEvidenceCount} · ${candidate.evidenceFreshness}`,
      },
    ],
    candidate.citationIds,
  );
```

- [ ] **Step 3: Compose the Dashboard in approved order**

Replace the return value with:

```tsx
<Screen hideGlobalHeader style={styles.dashboard}>
  <DashboardHeader
    health={snapshot.dataHealth}
    marketSession={snapshot.marketSession}
    onAlerts={() => router.push("/alerts")}
    onSearch={() => undefined}
    updatedAt={snapshot.updatedAt}
  />
  <HorizonSwitch value={horizon} onChange={changeHorizon} />
  <MarketRegimeHero
    advice={snapshot.marketAdvice}
    conclusion={snapshot.marketConclusion}
    drivers={snapshot.marketDrivers}
    onOpenDetail={() =>
      openDetail(
        "市场完整依据",
        marketSections,
        [
          ...snapshot.dataHealthCitationIds,
          ...snapshot.marketDrivers.flatMap((driver) => driver.citationIds),
        ],
      )
    }
    rationale={snapshot.marketRationale}
    score={snapshot.marketScore}
    updatedAt={snapshot.updatedAt}
  />
  <View style={styles.section}>
    <DashboardSectionHeader
      actionLabel="全部提醒 ›"
      onAction={() => router.push("/alerts")}
      title="需要关注"
    />
    <PriorityAlertCard
      alert={snapshot.priorityAlert}
      onOpenDetail={() =>
        openDetail(
          `${snapshot.priorityAlert.symbol} 提醒依据`,
          [
            { label: "当前状态", body: snapshot.priorityAlert.currentState },
            { label: "来源覆盖", body: snapshot.priorityAlert.sourceCoverage },
            { label: "失效条件", body: snapshot.priorityAlert.invalidation },
          ],
          snapshot.priorityAlert.citations.map((citation) => citation.id),
        )
      }
      onPress={() => openStock(snapshot.priorityAlert.symbol)}
    />
  </View>
  <WatchlistStrip onPress={openStock} quotes={snapshot.watchlist} />
  <CandidateList
    candidates={snapshot.candidates}
    onOpenDiscover={() => router.push("/discover")}
    onOpenEvidence={openCandidateEvidence}
    onPress={openStock}
  />
  <DashboardDetailSheet
    citations={detail?.citations ?? []}
    onClose={() => setDetail(null)}
    sections={detail?.sections ?? []}
    title={detail?.title ?? ""}
    visible={detail !== null}
  />
</Screen>
```

When horizon changes, call `setDetail(null)`.

- [ ] **Step 4: Tighten Dashboard screen spacing**

Do not change other screen defaults. Pass Dashboard-specific style:

```ts
const styles = StyleSheet.create({
  dashboard: {
    gap: 10,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xs,
  },
  section: { gap: 7 },
});
```

Modify `Screen` so a caller-provided content style does not remove safe-area
behavior and set `keyboardShouldPersistTaps="handled"`:

```tsx
<ScrollView
  contentContainerStyle={styles.scrollContent}
  keyboardShouldPersistTaps="handled">
  {content}
</ScrollView>
```

- [ ] **Step 5: Delete the obsolete expanded market card**

Delete:

```text
apps/mobile/src/components/dashboard/MarketPlaybookCard.tsx
```

Verify no import remains:

```bash
rg "MarketPlaybookCard" apps/mobile/src
```

Expected: no matches.

- [ ] **Step 6: Run all Dashboard tests**

```bash
cd apps/mobile
npm test -- \
  src/screens/__tests__/DashboardVisualContract.test.tsx \
  src/screens/__tests__/DashboardScreen.test.tsx \
  src/components/dashboard/__tests__/MarketRegimeHero.test.tsx \
  src/components/dashboard/__tests__/DashboardDetailSheet.test.tsx
```

Expected: all tests pass.

- [ ] **Step 7: Run complete automated checks**

```bash
cd apps/mobile
npm test -- --runInBand
npm run typecheck
npm run lint
```

Expected: all suites pass; typecheck and lint exit 0.

- [ ] **Step 8: Commit the completed Dashboard**

```bash
git add \
  apps/mobile/src/components/dashboard \
  apps/mobile/src/components/ui/Screen.tsx \
  apps/mobile/src/screens/DashboardScreen.tsx \
  apps/mobile/src/screens/__tests__
git commit -m "feat: realign dashboard with approved prototype"
```

---

### Task 7: Polish native tab navigation and create visual baselines

**Files:**
- Modify: `apps/mobile/src/app/(tabs)/_layout.tsx`
- Create: `docs/design-reference/dashboard-visual-regression.md`
- Create: `docs/design-reference/baselines/dashboard-approved-reference.png`
- Create: `docs/design-reference/baselines/dashboard-native-390x844.png`
- Create: `docs/design-reference/baselines/dashboard-native-430x932.png`

**Interfaces:**
- Consumes: approved prototype, completed Expo Dashboard
- Produces: stable tab style and three reviewable screenshot artifacts

- [ ] **Step 1: Apply the approved tab-bar appearance**

Set:

```tsx
<Tabs
  screenOptions={{
    headerShown: false,
    tabBarActiveTintColor: "#4285FF",
    tabBarInactiveTintColor: "#8A96A8",
    tabBarLabelStyle: {
      fontSize: 10,
      fontWeight: "700",
    },
    tabBarStyle: {
      backgroundColor: "rgba(255,255,255,0.98)",
      borderTopColor: "rgba(18,33,55,0.07)",
      height: 66,
      paddingBottom: 8,
      paddingTop: 6,
    },
  }}>
```

Keep the existing five routes and native `SymbolView` icons.

- [ ] **Step 2: Run route and navigation tests**

```bash
cd apps/mobile
npm test -- src/app/__tests__/routes.test.ts
npm run typecheck
npm run lint
```

Expected: all commands exit 0.

- [ ] **Step 3: Serve the approved reference and capture the phone design**

Run from the repository root:

```bash
/usr/bin/python3 -m http.server 55635 \
  --bind 127.0.0.1 \
  --directory docs/design-reference/approved-browser-prototypes
```

Open:

```text
http://127.0.0.1:55635/ios-dashboard-demo-v1.html
```

Capture the `.screen` content at the prototype's 390-point phone width and
save it as:

```text
docs/design-reference/baselines/dashboard-approved-reference.png
```

- [ ] **Step 4: Capture the implementation at two iPhone sizes**

Run:

```bash
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  CI=1 npm run start -- --web --port 8087
```

Capture `http://127.0.0.1:8087/` at:

```text
390 × 844 → docs/design-reference/baselines/dashboard-native-390x844.png
430 × 932 → docs/design-reference/baselines/dashboard-native-430x932.png
```

The screenshots must show the top of the Dashboard, not an arbitrary scrolled
position.

- [ ] **Step 5: Write the visual regression checklist**

Create `docs/design-reference/dashboard-visual-regression.md`:

```markdown
# Dashboard Visual Regression

Reference: `approved-browser-prototypes/ios-dashboard-demo-v1.html`

## 390 × 844

- Header, horizon switch, navy hero, priority alert, and `我的关注` heading are
  visible before the first viewport ends.
- Navy hero is the only dominant surface.
- Exactly four driver chips are visible.
- Full drivers, counter-evidence, and invalidation are hidden until
  `查看依据`.
- Three watchlist cards fit across the content width without horizontal scroll.
- Candidate rows are compact and do not expose full memos.
- Only one visible `演示数据 · 非实时行情` marker appears on the Dashboard.

## 430 × 932

- Layout remains centered and does not stretch cards into tablet proportions.
- Bottom tabs remain above the safe area.
- No text clips at the default iOS text size.

## Native confirmation

Web screenshots are iteration aids. Repeat the same checklist in iOS Simulator
or on the physical iPhone before acceptance.
```

- [ ] **Step 6: Compare and correct only measured visual differences**

Compare:

```text
dashboard-approved-reference.png
dashboard-native-390x844.png
dashboard-native-430x932.png
```

Correct only deviations in hierarchy, density, clipping, spacing, color, or
fold position. Do not add new Dashboard features during this step.

- [ ] **Step 7: Re-run all automated checks after visual corrections**

```bash
cd apps/mobile
npm test -- --runInBand
npm run typecheck
npm run lint
```

Expected: all commands exit 0.

- [ ] **Step 8: Commit navigation and baselines**

```bash
git add \
  apps/mobile/src/app/'(tabs)'/_layout.tsx \
  docs/design-reference/dashboard-visual-regression.md \
  docs/design-reference/baselines
git commit -m "test: add approved dashboard visual baselines"
```

---

### Task 8: Verify the native build, push, and install on the physical iPhone

**Files:**
- Modify only if prebuild exposes a source-controlled configuration problem:
  `apps/mobile/app.json`
- Do not commit: `apps/mobile/ios/**`

**Interfaces:**
- Consumes: completed branch, Node.js 22, Xcode 26.6, CocoaPods 1.17, user's Apple Account and iPhone
- Produces: remote feature branch, unsigned simulator build evidence, signed Personal Team device install, Home Screen launch, Fast Refresh verification

- [ ] **Step 1: Run the final automated gate**

```bash
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm test -- --runInBand
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm run typecheck
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm run lint
```

Expected: all tests pass; typecheck and lint exit 0.

- [ ] **Step 2: Regenerate the ignored iOS project**

```bash
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npx expo prebuild --platform ios
cd ios
pod install
```

Expected: prebuild and Pods complete without error. `Podfile.lock` exists in
the ignored `ios` directory.

- [ ] **Step 3: Verify an unsigned simulator build**

Discover the generated workspace and scheme:

```bash
cd apps/mobile/ios
xcodebuild -list -workspace USStockHelper.xcworkspace
```

Then run:

```bash
xcodebuild \
  -workspace USStockHelper.xcworkspace \
  -scheme USStockHelper \
  -configuration Debug \
  -sdk iphonesimulator \
  CODE_SIGNING_ALLOWED=NO \
  build
```

Expected: `xcodebuild -list` reports the `USStockHelper` scheme and the build
ends with `** BUILD SUCCEEDED **`. If a later Expo prebuild intentionally
renames the native project, update both commands to the exact generated names
reported by `xcodebuild -list`.

- [ ] **Step 4: Verify Git scope before pushing**

```bash
git status -sb
git diff --check
git log --oneline --max-count=12
```

Expected: no generated `apps/mobile/ios` files are staged and no unrelated
user files are changed.

- [ ] **Step 5: Push the feature branch**

```bash
git push origin feature/iphone-demo
```

Expected: the remote branch points to the final local commit.

- [ ] **Step 6: Complete the user-owned Xcode signing actions**

On the Mac:

1. Open `apps/mobile/ios/USStockHelper.xcworkspace`.
2. Open Xcode → Settings → Accounts and sign in with the user's Apple Account.
3. Select the app target → Signing & Capabilities.
4. Enable automatic signing.
5. Choose the user's Personal Team.
6. Keep `com.franz.usstockhelper.dev` unless Xcode reports it is unavailable;
   if unavailable, change only the bundle identifier to another user-owned
   unique identifier and mirror it in `app.json`.
7. Connect the iPhone by cable or approved wireless debugging.
8. Trust the Mac on the iPhone.
9. Enable Settings → Privacy & Security → Developer Mode on the iPhone.
10. Select the physical iPhone as the run destination.
11. Press Run and wait for installation.

Expected: `US Stock Helper` appears on the iPhone Home Screen and opens to the
compact Dashboard.

- [ ] **Step 7: Verify Fast Refresh**

Run on the Mac:

```bash
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm run start:dev-client
```

With the iPhone and Mac on a reachable network:

1. Open the installed app.
2. Confirm it connects to the local development server.
3. Make a harmless temporary text change in a Dashboard fixture label.
4. Confirm the phone updates without reinstalling.
5. revert the temporary text change.
6. run `git status -sb` and confirm no temporary change remains.

Expected: Fast Refresh updates the physical phone and the worktree returns
clean.

- [ ] **Step 8: Record acceptance without committing credentials**

Report:

```text
- automated test count and failures: 0
- typecheck: passed
- lint: passed
- simulator build: BUILD SUCCEEDED
- physical install: succeeded or exact blocker
- Home Screen launch: succeeded or exact blocker
- Fast Refresh: succeeded or exact blocker
- free Personal Team expiry reminder: approximately 7 days
```

Do not commit Apple IDs, certificates, provisioning profiles, device
identifiers, or signing logs containing private data.
