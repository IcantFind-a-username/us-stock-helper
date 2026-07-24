# iPhone Product Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Expo development app that installs on the user's iPhone with a free Apple Personal Team, supports Fast Refresh, and implements the approved U.S. stock helper demo with deterministic fixture data.

**Architecture:** Keep the existing Python indicator package untouched and add the mobile product under `apps/mobile`. Expo Router route files remain thin; focused screen, component, domain, fixture, and state modules hold behavior. All financial content comes from typed local fixtures in this phase, with repository interfaces that can later be replaced by real APIs.

**Tech Stack:** Expo SDK 57, React Native 0.86, React 19.2, TypeScript, Expo Router, `expo-dev-client`, `react-native-svg`, `expo-screen-orientation`, AsyncStorage, Jest Expo, React Native Testing Library, Xcode 26.4 or newer, Node.js 22.13 or newer.

## Global Constraints

- Project 1 contains no live market, moomoo, news, LLM, or broker API calls.
- Every financial screen must visibly say that values are demo data.
- Dashboard defaults to `short`; horizon identifiers are exactly `short`, `swing`, and `long`.
- Stock detail must visibly include a candlestick chart, Magic Nine, original Dragon Trend, probability forecast band with calibration metadata, pattern prompt, RSI, MACD, fundamentals, dated reported ownership, and estimated institutional/retail activity.
- RSI and MACD remain visible in portrait even when another landscape sub-chart is selected.
- Intraday institution/retail values must say `估算代理` and show confidence; reported ownership must show its reporting date.
- Adviser opinions are style simulations, not statements or endorsements from the named people.
- Objective scores and confidence never change when the risk preference changes.
- Long and short plans are analysis-only. No order-submit, order-edit, or order-cancel action may exist.
- The only moomoo action is copying a plan or opening moomoo for manual entry.
- Free Apple Personal Team provisioning expires after 7 days and must never be described as permanent distribution.
- Preserve the existing untracked Python, tests, skills, and documentation; commits for this plan stage only `apps/mobile` and plan-specific documentation.
- Bundle identifier for the local demo is `com.franz.usstockhelper.dev`; it can be changed before paid distribution.

## File Structure

```text
apps/mobile/
├── app.json                         # Expo identity, bundle ID, orientation, scheme
├── babel.config.js                  # Expo Router Babel preset
├── jest.config.js                   # Jest Expo configuration
├── jest.setup.ts                    # Testing Library and native mocks
├── package.json                     # Mobile-only commands and dependencies
├── tsconfig.json                    # Strict TypeScript configuration
├── assets/                          # Generated Expo icons/splash assets
└── src/
    ├── app/
    │   ├── _layout.tsx              # Root providers and stack
    │   ├── (tabs)/
    │   │   ├── _layout.tsx          # Five-tab navigation
    │   │   ├── index.tsx            # Dashboard route
    │   │   ├── discover.tsx         # Discover route
    │   │   ├── alerts.tsx           # Alerts route
    │   │   ├── journal.tsx          # Journal route
    │   │   └── agent.tsx            # Agent route
    │   └── stocks/[symbol]/
    │       ├── index.tsx            # Stock detail route
    │       ├── chart.tsx            # Full-screen chart route
    │       └── advisers.tsx         # Adviser and plan route
    ├── components/
    │   ├── ui/                      # Small reusable visual primitives
    │   ├── dashboard/               # Dashboard-specific cards
    │   ├── chart/                   # Candles, axes, overlays, indicators
    │   ├── stock/                   # Indicator and ownership cards
    │   ├── advisers/                # Adviser, risk, and plan controls
    │   └── evidence/                # Citation and evidence presentation
    ├── domain/
    │   ├── models.ts                # Shared domain types
    │   ├── chart.ts                 # Pure chart geometry
    │   └── plan.ts                  # Pure plan-selection rules
    ├── fixtures/
    │   ├── repository.ts            # Typed fixture access contract
    │   ├── dashboard.ts             # Three-horizon dashboard fixtures
    │   ├── stocks.ts                # Price, indicator, ownership fixtures
    │   ├── advisers.ts              # Thirteen style advisers and opinions
    │   ├── alerts.ts                # Alert threads and evidence
    │   └── conversations.ts         # Safe Agent fixture turns
    ├── screens/                     # Route-independent screen composition
    ├── state/
    │   ├── AppStateProvider.tsx     # Horizon, saved plans, journal state
    │   └── persistence.ts           # AsyncStorage adapter
    └── theme/
        └── tokens.ts                # Approved colors, type, spacing
```

---

### Task 1: Install the iOS toolchain and scaffold the mobile workspace

**Files:**
- Create: `apps/mobile/**` using the Expo SDK 57 template
- Modify: `apps/mobile/app.json`
- Modify: `apps/mobile/package.json`
- Modify: `apps/mobile/tsconfig.json`
- Create: `apps/mobile/jest.config.js`
- Create: `apps/mobile/jest.setup.ts`

**Interfaces:**
- Consumes: macOS 26.5.2, free Apple Account, existing repository root
- Produces: an SDK 57 app runnable through `npm run start:dev-client`, with strict typecheck and Jest commands

- [ ] **Step 1: Install full Xcode from the Mac App Store**

Open the official Xcode listing:

```text
https://apps.apple.com/app/xcode/id497799835
```

Install Xcode 26.4 or newer. Launch it once, accept the license, and allow it to install the iOS platform components. In Xcode → Settings → Accounts, sign in with the user's Apple Account. Xcode must show a `Personal Team`.

- [ ] **Step 2: Activate and verify the complete Xcode toolchain**

Run:

```bash
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
xcodebuild -runFirstLaunch
xcodebuild -version
xcode-select -p
```

Expected:

```text
Xcode 26.4 or newer
/Applications/Xcode.app/Contents/Developer
```

- [ ] **Step 3: Upgrade Node.js for Expo SDK 57**

The current `/usr/local/bin/node` is 20.17.0; SDK 57 requires Node 22.13 or newer.

Run:

```bash
/opt/homebrew/bin/brew install node@22
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin node --version
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin npm --version
```

Expected: Node prints `v22.13.0` or newer.

- [ ] **Step 4: Scaffold the Expo application**

Run from the repository root:

```bash
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin npx create-expo-app@latest apps/mobile --template default@sdk-57
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin npx expo install expo-dev-client react-native-svg expo-screen-orientation @react-native-async-storage/async-storage
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin npm install --save-dev jest-expo @testing-library/react-native @types/jest @types/node
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin npx expo install --dev react-test-renderer @types/react-test-renderer
```

Expected: `apps/mobile/package.json` contains Expo 57 and no install error.

- [ ] **Step 5: Configure the application identity**

Replace `apps/mobile/app.json` with:

```json
{
  "expo": {
    "name": "US Stock Helper",
    "slug": "us-stock-helper",
    "version": "0.1.0",
    "orientation": "portrait",
    "scheme": "usstockhelper",
    "userInterfaceStyle": "light",
    "newArchEnabled": true,
    "ios": {
      "supportsTablet": false,
      "bundleIdentifier": "com.franz.usstockhelper.dev"
    },
    "plugins": [
      "expo-router",
      "expo-dev-client",
      [
        "expo-screen-orientation",
        {
          "initialOrientation": "PORTRAIT_UP"
        }
      ]
    ],
    "experiments": {
      "typedRoutes": true
    }
  }
}
```

- [ ] **Step 6: Add deterministic development commands**

Ensure `apps/mobile/package.json` contains these scripts:

```json
{
  "scripts": {
    "start": "expo start",
    "start:dev-client": "expo start --dev-client",
    "ios:device": "expo run:ios --device",
    "typecheck": "tsc --noEmit",
    "lint": "expo lint",
    "test": "jest --runInBand",
    "test:watch": "jest --watch"
  }
}
```

Create `apps/mobile/jest.config.js`:

```js
module.exports = {
  preset: "jest-expo",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  testPathIgnorePatterns: ["/node_modules/", "/ios/"],
};
```

Create `apps/mobile/jest.setup.ts`:

```ts
jest.mock("expo-screen-orientation", () => ({
  lockAsync: jest.fn(),
  unlockAsync: jest.fn(),
  OrientationLock: {
    PORTRAIT_UP: 1,
    LANDSCAPE: 6,
  },
}));
```

- [ ] **Step 7: Enable strict TypeScript**

Merge into `apps/mobile/tsconfig.json`:

```json
{
  "extends": "expo/tsconfig.base",
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src/**/*.ts", "src/**/*.tsx", ".expo/types/**/*.ts", "expo-env.d.ts"]
}
```

- [ ] **Step 8: Verify the clean scaffold**

Run:

```bash
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin npm run typecheck
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin npm run lint
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin npm test -- --passWithNoTests
```

Expected: all three commands exit 0.

- [ ] **Step 9: Commit the scaffold without unrelated files**

```bash
git add apps/mobile
git commit -m "build: scaffold expo iphone demo"
```

Expected: existing Python and `.agents` files remain unstaged unless they were already tracked.

---

### Task 2: Define domain contracts and typed demo fixtures

**Files:**
- Create: `apps/mobile/src/domain/models.ts`
- Create: `apps/mobile/src/fixtures/repository.ts`
- Create: `apps/mobile/src/fixtures/dashboard.ts`
- Create: `apps/mobile/src/fixtures/stocks.ts`
- Create: `apps/mobile/src/fixtures/advisers.ts`
- Create: `apps/mobile/src/fixtures/alerts.ts`
- Create: `apps/mobile/src/fixtures/conversations.ts`
- Test: `apps/mobile/src/fixtures/__tests__/repository.test.ts`

**Interfaces:**
- Consumes: no runtime input
- Produces: `FixtureRepository`, `Horizon`, `DashboardSnapshot`, `StockSnapshot`, `AdviserOpinion`, `TradePlan`, `AlertThread`

- [ ] **Step 1: Write the failing fixture-contract test**

Create `apps/mobile/src/fixtures/__tests__/repository.test.ts`:

```ts
import { fixtureRepository } from "@/fixtures/repository";

describe("fixtureRepository", () => {
  it.each(["short", "swing", "long"] as const)(
    "returns a complete %s dashboard",
    (horizon) => {
      const dashboard = fixtureRepository.getDashboard(horizon);

      expect(dashboard.horizon).toBe(horizon);
      expect(dashboard.demoData).toBe(true);
      expect(dashboard.marketConclusion.length).toBeGreaterThan(0);
      expect(dashboard.marketDrivers.length).toBeGreaterThanOrEqual(4);
      expect(dashboard.watchlist.length).toBeGreaterThanOrEqual(3);
    },
  );

  it("keeps RSI, MACD, reported ownership, and participation proxy", () => {
    const stock = fixtureRepository.getStock("NVDA", "short");

    expect(stock.indicators.rsi.value).toBeGreaterThan(0);
    expect(stock.indicators.macd.histogram.length).toBeGreaterThan(0);
    expect(stock.candles).toHaveLength(28);
    expect(stock.forecast.points).toHaveLength(8);
    expect(stock.dragonTrend.methodVersion).toBe("original-demo-v1");
    expect(stock.patterns[0]?.complete).toBe(false);
    expect(stock.fundamentals.materialRisks.length).toBeGreaterThan(0);
    expect(stock.reportedOwnership.reportedAt).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(stock.participationProxy.label).toBe("估算代理");
    expect(stock.participationProxy.sourceCoverage.length).toBeGreaterThan(0);
    expect(
      stock.participationProxy.institutionalPercent +
        stock.participationProxy.retailPercent,
    ).toBe(100);
  });

  it("keeps alert invalidation and objective conversation order", () => {
    expect(fixtureRepository.getAlerts()[0]).toMatchObject({
      currentState: "等待量价确认",
      invalidation: "收盘跌破 136.40",
    });
    expect(
      fixtureRepository
        .getConversation()[0]
        ?.sections?.map((section) => section.title),
    ).toEqual([
      "客观结论",
      "证据",
      "最强反证",
      "缺失信息与不确定性",
      "个性化风险场景",
      "引用",
    ]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd apps/mobile
npm test -- src/fixtures/__tests__/repository.test.ts
```

Expected: FAIL because `@/fixtures/repository` does not exist.

- [ ] **Step 3: Define the shared domain types**

Create `apps/mobile/src/domain/models.ts`:

```ts
export type Horizon = "short" | "swing" | "long";
export type Direction = "bullish" | "neutral" | "bearish";
export type EvidenceKind = "fact" | "inference" | "scenario" | "rumor";
export type RiskPreference = "conservative" | "balanced" | "aggressive";
export type PlanSide = "long" | "short";
export type DataHealth = "fresh" | "stale" | "conflict" | "insufficient";
export type MarketDriverCategory =
  | "news-sentiment"
  | "breadth"
  | "volatility-options"
  | "sector"
  | "rates-dollar"
  | "geopolitics";

export interface Citation {
  id: string;
  title: string;
  publisher: string;
  url: string;
  publishedAt: string;
  firstSeenAt: string;
  kind: EvidenceKind;
}

export interface MarketDriver {
  id: string;
  category: MarketDriverCategory;
  label: string;
  score: number;
  conclusion: string;
  freshness: "fresh" | "stale" | "conflict";
  citationIds: string[];
}

export interface DashboardSnapshot {
  demoData: true;
  horizon: Horizon;
  updatedAt: string;
  marketSession: string;
  dataHealth: DataHealth;
  marketScore: number;
  marketConfidence: number;
  marketScoreChange: number;
  marketConclusion: string;
  marketAdvice: string;
  contradictions: string[];
  marketDrivers: MarketDriver[];
  priorityAlert: AlertThread;
  watchlist: WatchlistQuote[];
  candidates: Candidate[];
}

export interface WatchlistQuote {
  symbol: string;
  price: number;
  changePercent: number;
  direction: Direction;
  summary: string;
}

export interface Candidate {
  symbol: string;
  company: string;
  horizon: Horizon;
  side: PlanSide;
  score: number;
  state: "observation" | "action-eligible" | "risk";
  catalyst: string;
  evidenceFreshness: "fresh" | "stale" | "conflict";
  institutionalProxy: string;
  technicalState: string;
  fundamentalState: string;
  volatilityState: string;
  liquidityRisk: "low" | "medium" | "high";
  reason: string;
  evidenceCount: number;
  counterEvidenceCount: number;
}

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ForecastPoint {
  timestamp: string;
  median: number;
  lower50: number;
  upper50: number;
  lower80: number;
  upper80: number;
}

export interface ForecastSnapshot {
  horizon: string;
  points: ForecastPoint[];
  probability: { up: number; flat: number; down: number };
  calibrationError: number;
  predictedAt: string;
  modelVersion: string;
  invalidation: string;
}

export interface RsiSnapshot {
  value: number;
  period: number;
  interval: string;
  state: "oversold" | "neutral" | "near-overbought" | "overbought";
  direction: "rising" | "flat" | "falling";
  divergence: "bullish" | "none" | "bearish";
}

export interface MacdSnapshot {
  dif: number;
  dea: number;
  interval: string;
  histogram: number[];
  state: "bull-expanding" | "bull-contracting" | "bear-expanding" | "bear-contracting";
  crossover: "golden-cross" | "death-cross" | "none";
}

export interface ReportedOwnership {
  institutionalPercent: number;
  insiderPercent: number;
  otherPercent: number;
  reportedAt: string;
  changes: string[];
  citationIds: string[];
}

export interface ParticipationProxy {
  label: "估算代理";
  institutionalPercent: number;
  retailPercent: number;
  confidence: "low" | "medium" | "high";
  estimatedAt: string;
  methodVersion: string;
  sourceCoverage: string;
  citationIds: string[];
}

export interface MarketContext {
  marketDirection: string;
  sectorState: string;
  macroState: string;
  geopoliticalState: string;
  scoreAdjustment: number;
  planChanges: string[];
  citationIds: string[];
}

export interface PatternSignal {
  name: string;
  status: "forming" | "confirmed" | "invalidated";
  complete: boolean;
  invalidation: string;
  horizon: Horizon;
}

export interface FundamentalSnapshot {
  financialHealth: string;
  cash: string;
  debt: string;
  dilution: string;
  runway: string;
  margins: string;
  growth: string;
  valuation: string;
  materialRisks: string[];
  industryContext: string;
  supplyChainContext: string;
  citationIds: string[];
}

export interface StockSnapshot {
  demoData: true;
  symbol: string;
  company: string;
  exchange: string;
  marketSession: string;
  watchlisted: boolean;
  horizon: Horizon;
  price: number;
  changePercent: number;
  quoteLatencyMs: number;
  candles: Candle[];
  forecast: ForecastSnapshot;
  magicNine: { count: number; complete: boolean; invalidation: string; horizon: Horizon };
  dragonTrend: { state: Direction; score: number; methodVersion: string; invalidation: string };
  patterns: PatternSignal[];
  indicators: { rsi: RsiSnapshot; macd: MacdSnapshot };
  reportedOwnership: ReportedOwnership;
  participationProxy: ParticipationProxy;
  marketContext: MarketContext;
  fundamentals: FundamentalSnapshot;
  baseScore: number;
  adjustedScore: number;
  conclusion: string;
  counterCase: string;
  citations: Citation[];
}

export interface AdviserOpinion {
  id: string;
  displayName: string;
  focus: string;
  direction: Direction;
  confidence: number;
  active: boolean;
  abstained: boolean;
  thesis: string;
  counterargument: string;
  evidenceIds: string[];
}

export interface TradePlan {
  id: string;
  symbol: string;
  side: PlanSide;
  preference: RiskPreference;
  objectiveScore: number;
  confidence: number;
  entryMethod: string;
  entryRange: [number, number];
  quantity: number;
  riskBudgetPercent: number;
  leverage: number;
  maximumLeverage: number;
  invalidationPrice: number;
  stopLogic: string;
  targetRange: [number, number];
  estimatedRewardRisk: number;
  holdingWindow: string;
  cancelConditions: string[];
  riskWarning: string;
  evidenceSnapshotId: string;
  shortRisk: {
    borrowAvailable: boolean;
    checkedAt: string;
    estimatedBorrowFeePercent: number;
    shortInterestPercent: number;
    crowding: "low" | "medium" | "high";
    warnings: string[];
  } | null;
}

export interface AlertThread {
  id: string;
  symbol: string;
  horizon: Horizon;
  severity: "info" | "observation" | "action" | "risk";
  title: string;
  summary: string;
  triggeredAt: string;
  sourceFreshness: "fresh" | "stale" | "conflict";
  currentState: string;
  invalidation: string;
  baseScoreContribution: number;
  adviserAdjustment: number | null;
  evidenceCount: number;
  counterEvidenceCount: number;
  updatedAt: string;
  citations: Citation[];
}

export interface JournalEntry {
  id: string;
  symbol: string;
  side: PlanSide;
  quantity: number;
  executionPrice: number;
  executedAt: string;
  executionDelaySeconds: number;
  pnl: number;
  pnlState: "realized" | "unrealized";
  decision: "followed" | "overridden";
  slippage: number;
  notes: string;
}

export interface ConversationSection {
  title:
    | "客观结论"
    | "证据"
    | "最强反证"
    | "缺失信息与不确定性"
    | "个性化风险场景"
    | "引用";
  body: string;
}

export interface ConversationTurn {
  id: string;
  role: "user" | "assistant";
  text?: string;
  sections?: ConversationSection[];
  citationIds: string[];
}
```

- [ ] **Step 4: Create complete deterministic fixtures**

Create fixture modules with these required records:

```ts
// apps/mobile/src/fixtures/advisers.ts
import type {
  AdviserOpinion,
  PlanSide,
  RiskPreference,
  TradePlan,
} from "@/domain/models";

export const adviserOpinions: AdviserOpinion[] = [
  ["damodaran", "Damodaran 风格", "估值叙事"],
  ["graham", "Graham 风格", "安全边际"],
  ["ackman", "Ackman 风格", "集中与催化"],
  ["wood", "Cathie Wood 风格", "创新成长"],
  ["munger", "Munger 风格", "企业质量"],
  ["burry", "Burry 风格", "逆向与泡沫"],
  ["pabrai", "Pabrai 风格", "低风险高不对称"],
  ["taleb", "Taleb 风格", "尾部风险"],
  ["lynch", "Peter Lynch 风格", "成长与可理解性"],
  ["fisher", "Phil Fisher 风格", "深度成长研究"],
  ["jhunjhunwala", "Jhunjhunwala 风格", "长期成长"],
  ["druckenmiller", "Druckenmiller 风格", "宏观动量"],
  ["buffett", "Buffett 风格", "质量与合理价格"],
].map(([id, displayName, focus], index): AdviserOpinion => ({
  id,
  displayName,
  focus,
  direction: index === 5 || index === 7 ? "bearish" : "bullish",
  confidence: index < 4 ? 0.72 : 0.58,
  active: index < 4,
  abstained: index === 12,
  thesis: "基于演示证据包的风格化观点。",
  counterargument: "估值拥挤与事件不确定性可能削弱结论。",
  evidenceIds: ["nvda-source-1"],
}));

const preferences: RiskPreference[] = ["conservative", "balanced", "aggressive"];
const sides: PlanSide[] = ["long", "short"];

export const tradePlanFixtures: TradePlan[] = sides.flatMap((side) =>
  preferences.map((preference, index): TradePlan => ({
    id: `NVDA-${side}-${preference}`,
    symbol: "NVDA",
    side,
    preference,
    objectiveScore: 72,
    confidence: 0.68,
    entryMethod: preference === "aggressive" ? "突破限价" : "回踩分批限价",
    entryRange: side === "long" ? [139.8, 141.2] : [143.4, 144.6],
    quantity: [20, 35, 50][index] ?? 20,
    riskBudgetPercent: [0.5, 0.8, 1.0][index] ?? 0.5,
    leverage: [1, 1.25, 1.5][index] ?? 1,
    maximumLeverage: 1.5,
    invalidationPrice: side === "long" ? 136.4 : 148.2,
    stopLogic: "触及失效价后取消原假设；跳空时按首个可执行价格重新评估。",
    targetRange: side === "long" ? [148, 153] : [134, 137],
    estimatedRewardRisk: [1.6, 2.1, 2.6][index] ?? 1.6,
    holdingWindow: "盘中至 5 个交易日",
    cancelConditions: ["证据包过期", "大盘环境转为空头", "关键消息被证伪"],
    riskWarning:
      side === "short"
        ? "演示方案；需确认借券可用性，做空存在理论上的无限损失风险。"
        : "演示方案；跳空可能使实际亏损超过计划止损。",
    evidenceSnapshotId: "NVDA-short-2026-07-24T10:30:00Z",
    shortRisk: side === "short" ? {
      borrowAvailable: true,
      checkedAt: "2026-07-24T10:29:00-04:00",
      estimatedBorrowFeePercent: 0.35,
      shortInterestPercent: 1.2,
      crowding: "low",
      warnings: ["逼空与跳空风险", "停牌与召回风险", "理论上的无限损失风险"],
    } : null,
  })),
);
```

Create the other fixtures from deterministic typed builders. The exact fixture
requirements and keys are:

```ts
// apps/mobile/src/fixtures/stocks.ts
import type { Candle, Horizon, StockSnapshot } from "@/domain/models";

const closes = [
  132.1, 132.8, 131.9, 133.2, 134.1, 133.6, 135.0, 136.2,
  135.7, 136.8, 137.6, 137.1, 138.4, 139.0, 138.5, 139.7,
  140.2, 139.8, 141.1, 141.8, 141.2, 142.0, 141.6, 142.4,
  142.9, 142.2, 143.1, 143.8,
];

const candles: Candle[] = closes.map((close, index) => {
  const open = index === 0 ? 131.6 : (closes[index - 1] ?? close);
  return {
    timestamp: `2026-07-24T${String(9 + Math.floor(index / 12)).padStart(2, "0")}:${String((index * 5) % 60).padStart(2, "0")}:00-04:00`,
    open,
    high: Math.max(open, close) + 0.7,
    low: Math.min(open, close) - 0.6,
    close,
    volume: 420_000 + index * 31_000,
  };
});

const buildStock = (horizon: Horizon): StockSnapshot => ({
  demoData: true,
  symbol: "NVDA",
  company: "NVIDIA",
  exchange: "NASDAQ",
  marketSession: "美股盘中",
  watchlisted: true,
  horizon,
  price: 143.8,
  changePercent: 2.46,
  quoteLatencyMs: 850,
  candles,
  forecast: {
    horizon: "未来 5 个交易日",
    points: Array.from({ length: 8 }, (_, index) => ({
      timestamp: `T+${index + 1}`,
      median: 144.2 + index * 0.7,
      lower50: 142.8 + index * 0.35,
      upper50: 145.6 + index * 1.05,
      lower80: 140.9 + index * 0.1,
      upper80: 147.3 + index * 1.45,
    })),
    probability: { up: 0.58, flat: 0.18, down: 0.24 },
    calibrationError: 0.084,
    predictedAt: "2026-07-24T10:30:00-04:00",
    modelVersion: "demo-calibrated-v1",
    invalidation: "收盘跌破 136.40 或大盘环境转为空头",
  },
  magicNine: {
    count: 7,
    complete: false,
    invalidation: "序列中断则重新计数",
    horizon,
  },
  dragonTrend: {
    state: "bullish",
    score: 64,
    methodVersion: "original-demo-v1",
    invalidation: "趋势强度跌破 45",
  },
  patterns: [
    {
      name: "回踩五日线后企稳",
      status: "forming",
      complete: false,
      invalidation: "收盘跌破 136.40",
      horizon,
    },
    {
      name: "三日底分型",
      status: "confirmed",
      complete: true,
      invalidation: "跌破分型最低点",
      horizon,
    },
    {
      name: "W底",
      status: "forming",
      complete: false,
      invalidation: "右底跌破左底",
      horizon,
    },
    {
      name: "头肩顶",
      status: "invalidated",
      complete: false,
      invalidation: "价格重新站上右肩",
      horizon,
    },
    {
      name: "回眸一笑",
      status: "forming",
      complete: false,
      invalidation: "均线重新转弱",
      horizon,
    },
  ],
  indicators: {
    rsi: {
      value: 63.8,
      period: 14,
      interval: "5分钟",
      state: "near-overbought",
      direction: "rising",
      divergence: "none",
    },
    macd: {
      dif: 1.42,
      dea: 1.08,
      interval: "5分钟",
      histogram: [0.08, 0.12, 0.18, 0.25, 0.31, 0.34],
      state: "bull-expanding",
      crossover: "golden-cross",
    },
  },
  reportedOwnership: {
    institutionalPercent: 65,
    insiderPercent: 4,
    otherPercent: 31,
    reportedAt: "2026-06-30",
    changes: ["演示：Top 20 报告机构净增持 1.8%", "演示：内部人持仓无重大变化"],
    citationIds: ["nvda-source-1"],
  },
  participationProxy: {
    label: "估算代理",
    institutionalPercent: 58,
    retailPercent: 42,
    confidence: "medium",
    estimatedAt: "2026-07-24T10:30:00-04:00",
    methodVersion: "demo-v1",
    sourceCoverage: "演示成交与盘口特征覆盖 82%",
    citationIds: ["nvda-source-2"],
  },
  marketContext: {
    marketDirection: "纳指短线偏强，但广度一般",
    sectorState: "半导体板块相对强势",
    macroState: "利率与美元对高估值板块仍有压制",
    geopoliticalState: "出口限制消息构成双向事件风险",
    scoreAdjustment: -3,
    planChanges: ["杠杆上限从 1.75x 降至 1.5x", "要求大盘广度同步改善"],
    citationIds: ["nvda-source-2"],
  },
  fundamentals: {
    financialHealth: "演示：现金流健康，估值偏高",
    cash: "$31.4B",
    debt: "$11.0B",
    dilution: "低",
    runway: "充足",
    margins: "毛利率 74%（演示）",
    growth: "收入同比 +122%（演示）",
    valuation: "远期估值高于行业中位数（演示）",
    materialRisks: ["出口限制", "客户集中", "高估值回撤"],
    industryContext: "AI 加速器需求强，但竞争与周期性存在。",
    supplyChainContext: "先进制程与封装产能是关键约束。",
    citationIds: ["nvda-source-1"],
  },
  baseScore: 70,
  adjustedScore: 72,
  conclusion: "谨慎偏多；等待量价确认，不追高。",
  counterCase: "若指数转弱或出口限制升级，当前形态可能失效。",
  citations: [
    {
      id: "nvda-source-1",
      title: "演示：机构持仓报告",
      publisher: "SEC",
      url: "https://www.sec.gov/",
      publishedAt: "2026-07-20T14:00:00Z",
      firstSeenAt: "2026-07-20T14:01:00Z",
      kind: "fact",
    },
    {
      id: "nvda-source-2",
      title: "演示：市场与成交结构快照",
      publisher: "Demo Market Feed",
      url: "https://example.com/demo-market-feed",
      publishedAt: "2026-07-24T14:30:00Z",
      firstSeenAt: "2026-07-24T14:30:01Z",
      kind: "inference",
    },
  ],
});

export const stockFixtures: Record<string, StockSnapshot> = {
  "NVDA:short": buildStock("short"),
  "NVDA:swing": buildStock("swing"),
  "NVDA:long": buildStock("long"),
};
```

```ts
// apps/mobile/src/fixtures/dashboard.ts
import type { DashboardSnapshot, Horizon } from "@/domain/models";
import { alertThreads } from "./alerts";

const labels: Record<Horizon, string> = {
  short: "谨慎偏多",
  swing: "波段环境",
  long: "中长期质量优先",
};

const buildDashboard = (horizon: Horizon): DashboardSnapshot => ({
  demoData: true,
  horizon,
  updatedAt: "2026-07-24T10:30:00-04:00",
  marketSession: "美股盘中 · 演示状态",
  dataHealth: "fresh",
  marketScore: horizon === "short" ? 61 : horizon === "swing" ? 56 : 68,
  marketConfidence: 0.67,
  marketScoreChange: 4,
  marketConclusion: labels[horizon],
  marketAdvice: "优先等回踩确认；单一方案风险预算不超过演示账户的 1%。",
  contradictions: ["指数上涨但市场广度扩散有限", "板块强势但利率端仍有压制"],
  marketDrivers: [
    ["news-sentiment", "新闻与整体情绪", 22, "情绪偏多但拥挤"],
    ["breadth", "市场广度", 6, "上涨扩散有限"],
    ["volatility-options", "波动率与期权", -8, "尾部保护需求上升"],
    ["sector", "板块强弱", 31, "半导体相对强势"],
    ["rates-dollar", "利率与美元", -18, "估值端仍受压制"],
    ["geopolitics", "地缘政治", -12, "出口限制风险待确认"],
  ].map(([category, label, score, conclusion], index) => ({
    id: `driver-${index}`,
    category: category as DashboardSnapshot["marketDrivers"][number]["category"],
    label: String(label),
    score: Number(score),
    conclusion: String(conclusion),
    freshness: category === "geopolitics" ? "conflict" : "fresh",
    citationIds: ["nvda-source-2"],
  })),
  priorityAlert: alertThreads[0]!,
  watchlist: [
    { symbol: "NVDA", price: 143.8, changePercent: 2.46, direction: "bullish", summary: "量价待确认" },
    { symbol: "TSLA", price: 318.2, changePercent: -1.2, direction: "bearish", summary: "事件波动高" },
    { symbol: "PLTR", price: 86.4, changePercent: 0.8, direction: "neutral", summary: "高估值观察" },
  ],
  candidates: [
    {
      symbol: "NVDA",
      company: "NVIDIA",
      horizon,
      side: "long",
      score: 72,
      state: "action-eligible",
      catalyst: "板块动量与事件窗口",
      evidenceFreshness: "fresh",
      institutionalProxy: "估算机构参与 58% · 中置信",
      technicalState: "九转 7；MACD 多头扩张",
      fundamentalState: "增长强，估值偏高",
      volatilityState: "中等偏高",
      liquidityRisk: "low",
      reason: "催化、量价和市场环境同向，但尚未排除事件风险。",
      evidenceCount: 5,
      counterEvidenceCount: 2,
    },
    {
      symbol: "TSLA",
      company: "Tesla",
      horizon,
      side: "short",
      score: 58,
      state: "observation",
      catalyst: "交付预期变化",
      evidenceFreshness: "conflict",
      institutionalProxy: "覆盖不足",
      technicalState: "反弹遇阻，等待确认",
      fundamentalState: "利润率与现金流待验证",
      volatilityState: "高",
      liquidityRisk: "medium",
      reason: "仅进入观察池，证据尚不足以触发行动研究。",
      evidenceCount: 3,
      counterEvidenceCount: 3,
    },
    {
      symbol: "PLTR",
      company: "Palantir",
      horizon,
      side: "long",
      score: 49,
      state: "risk",
      catalyst: "订单消息",
      evidenceFreshness: "stale",
      institutionalProxy: "估算机构参与 46% · 低置信",
      technicalState: "RSI 接近超买",
      fundamentalState: "增长较快，估值拥挤",
      volatilityState: "高",
      liquidityRisk: "high",
      reason: "估值、拥挤度和消息确认度带来较高回撤风险。",
      evidenceCount: 2,
      counterEvidenceCount: 5,
    },
  ],
});

export const dashboardFixtures: Record<Horizon, DashboardSnapshot> = {
  short: buildDashboard("short"),
  swing: buildDashboard("swing"),
  long: buildDashboard("long"),
};
```

```ts
// apps/mobile/src/fixtures/alerts.ts
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
```

```ts
// apps/mobile/src/fixtures/conversations.ts
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
```

The repository test asserts the alert state, invalidation, and the exact six
conversation section titles, so missing fields fail before UI work starts.

- [ ] **Step 5: Implement the repository interface**

Create `apps/mobile/src/fixtures/repository.ts`:

```ts
import type {
  AdviserOpinion,
  AlertThread,
  Citation,
  ConversationTurn,
  DashboardSnapshot,
  Horizon,
  StockSnapshot,
  TradePlan,
} from "@/domain/models";
import { dashboardFixtures } from "./dashboard";
import { stockFixtures } from "./stocks";
import { adviserOpinions, tradePlanFixtures } from "./advisers";
import { alertThreads } from "./alerts";
import { conversationTurns } from "./conversations";

export interface FixtureRepository {
  getDashboard(horizon: Horizon): DashboardSnapshot;
  getStock(symbol: string, horizon: Horizon): StockSnapshot;
  getAdvisers(symbol: string, horizon: Horizon): AdviserOpinion[];
  getTradePlans(symbol: string): TradePlan[];
  getAlerts(): AlertThread[];
  getConversation(): ConversationTurn[];
  getCitations(ids: string[]): Citation[];
}

export const fixtureRepository: FixtureRepository = {
  getDashboard: (horizon) => dashboardFixtures[horizon],
  getStock: (symbol, horizon) => {
    const key = `${symbol.toUpperCase()}:${horizon}`;
    const stock = stockFixtures[key];
    if (!stock) throw new Error(`Missing stock fixture: ${key}`);
    return stock;
  },
  getAdvisers: () => adviserOpinions,
  getTradePlans: (symbol) =>
    tradePlanFixtures.filter((plan) => plan.symbol === symbol.toUpperCase()),
  getAlerts: () => alertThreads,
  getConversation: () => conversationTurns,
  getCitations: (ids) => {
    const all = [
      ...Object.values(stockFixtures).flatMap((stock) => stock.citations),
      ...alertThreads.flatMap((alert) => alert.citations),
    ];
    return ids.flatMap((id) => {
      const citation = all.find((candidate) => candidate.id === id);
      return citation ? [citation] : [];
    });
  },
};
```

- [ ] **Step 6: Run the tests**

Run:

```bash
cd apps/mobile
npm test -- src/fixtures/__tests__/repository.test.ts
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/mobile/src/domain apps/mobile/src/fixtures
git commit -m "feat: add typed mobile demo fixtures"
```

---

### Task 3: Build the visual system and safety primitives

**Files:**
- Create: `apps/mobile/src/theme/tokens.ts`
- Create: `apps/mobile/src/components/ui/Screen.tsx`
- Create: `apps/mobile/src/components/ui/DemoDataBadge.tsx`
- Create: `apps/mobile/src/components/ui/HorizonSwitch.tsx`
- Create: `apps/mobile/src/components/ui/SectionHeader.tsx`
- Create: `apps/mobile/src/components/ui/ScoreBadge.tsx`
- Create: `apps/mobile/src/components/ui/GlobalHeader.tsx`
- Create: `apps/mobile/src/components/ui/DataHealthBanner.tsx`
- Create: `apps/mobile/src/components/evidence/CitationRow.tsx`
- Create: `apps/mobile/src/components/evidence/EvidenceSheet.tsx`
- Test: `apps/mobile/src/components/ui/__tests__/HorizonSwitch.test.tsx`
- Test: `apps/mobile/src/components/evidence/__tests__/EvidenceSheet.test.tsx`

**Interfaces:**
- Consumes: `Horizon`, `Citation`
- Produces: approved color/spacing tokens and reusable safety/evidence UI

- [ ] **Step 1: Write failing component tests**

Create `HorizonSwitch.test.tsx`:

```tsx
import { fireEvent, render } from "@testing-library/react-native";
import { HorizonSwitch } from "../HorizonSwitch";

it("selects a horizon without changing the labels", () => {
  const onChange = jest.fn();
  const view = render(<HorizonSwitch value="short" onChange={onChange} />);

  fireEvent.press(view.getByText("波段 · 1–8周"));
  expect(onChange).toHaveBeenCalledWith("swing");
  expect(view.getByText("短线 · 0–5日")).toBeTruthy();
});
```

Create `EvidenceSheet.test.tsx`:

```tsx
import { render } from "@testing-library/react-native";
import { EvidenceSheet } from "../EvidenceSheet";

it("labels facts and rumors separately", () => {
  const view = render(
    <EvidenceSheet
      title="证据"
      citations={[
        {
          id: "a",
          title: "Official filing",
          publisher: "SEC",
          url: "https://www.sec.gov/",
          publishedAt: "2026-07-20T10:00:00Z",
          firstSeenAt: "2026-07-20T10:01:00Z",
          kind: "fact",
        },
        {
          id: "b",
          title: "Unconfirmed report",
          publisher: "Example",
          url: "https://example.com/",
          publishedAt: "2026-07-20T10:02:00Z",
          firstSeenAt: "2026-07-20T10:03:00Z",
          kind: "rumor",
        },
      ]}
    />,
  );

  expect(view.getByText("事实")).toBeTruthy();
  expect(view.getByText("传闻")).toBeTruthy();
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/mobile
npm test -- src/components/ui/__tests__/HorizonSwitch.test.tsx src/components/evidence/__tests__/EvidenceSheet.test.tsx
```

Expected: FAIL because the components do not exist.

- [ ] **Step 3: Define the approved design tokens**

Create `apps/mobile/src/theme/tokens.ts`:

```ts
export const colors = {
  background: "#F5F7FA",
  card: "#FFFFFF",
  ink: "#0D1729",
  muted: "#718096",
  line: "#DFE5ED",
  navy: "#0B1424",
  navyRaised: "#111E33",
  blue: "#4285FF",
  blueSoft: "#EAF2FF",
  green: "#20B878",
  greenSoft: "#E8F8F0",
  red: "#ED5C63",
  redSoft: "#FFEDEF",
  amber: "#F1AA3F",
  amberSoft: "#FFF4DF",
  purple: "#7860D9",
  purpleSoft: "#F0EDFF",
} as const;

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 } as const;
export const radius = { sm: 8, md: 12, lg: 17, pill: 999 } as const;
```

- [ ] **Step 4: Implement the primitives**

`HorizonSwitch` must render these immutable mappings:

```ts
const horizonLabels = {
  short: "短线 · 0–5日",
  swing: "波段 · 1–8周",
  long: "中长线 · 2–24月",
} as const;
```

`DemoDataBadge` text is exactly `演示数据 · 非实时建议`.
`DataHealthBanner` accepts `{ health: DataHealth; marketSession: string }`.
`EvidenceSheet` renders each citation with its source type, publisher,
publication time, and an accessible `Linking.openURL` action.

`GlobalHeader` is used by `Screen` unless explicitly hidden by the landscape
chart. It exposes two 44×44-point buttons:

```tsx
<Pressable accessibilityRole="button" accessibilityLabel="搜索股票" onPress={onSearch}>
  <Ionicons name="search-outline" />
</Pressable>
<Pressable accessibilityRole="button" accessibilityLabel="查看提醒" onPress={onAlerts}>
  <Ionicons name="notifications-outline" />
</Pressable>
```

In Project 1, search filters fixture symbols only and the notification button
navigates to `/(tabs)/alerts`; neither action performs a network request.

- [ ] **Step 5: Run tests and static checks**

```bash
cd apps/mobile
npm test -- src/components/ui src/components/evidence
npm run typecheck
npm run lint
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/mobile/src/theme apps/mobile/src/components/ui apps/mobile/src/components/evidence
git commit -m "feat: add mobile design and evidence primitives"
```

---

### Task 4: Add local state, persistence, navigation, and the first device build

**Files:**
- Create: `apps/mobile/src/state/persistence.ts`
- Create: `apps/mobile/src/state/AppStateProvider.tsx`
- Create: `apps/mobile/src/app/_layout.tsx`
- Create: `apps/mobile/src/app/(tabs)/_layout.tsx`
- Create: thin route files under `apps/mobile/src/app`
- Create: temporary screen modules under `apps/mobile/src/screens`
- Test: `apps/mobile/src/state/__tests__/AppStateProvider.test.tsx`
- Test: `apps/mobile/src/app/__tests__/routes.test.ts`

**Interfaces:**
- Consumes: `Horizon`, `TradePlan`
- Produces: `useAppState()` with `horizon`, `setHorizon`, `savedPlans`, `savePlan`, `journalEntries`, `addJournalEntry`

- [ ] **Step 1: Write the failing state test**

```tsx
import { fireEvent, render } from "@testing-library/react-native";
import { Button, Text } from "react-native";
import { AppStateProvider, useAppState } from "../AppStateProvider";

function Probe() {
  const { horizon, setHorizon } = useAppState();
  return (
    <>
      <Text>{horizon}</Text>
      <Button title="swing" onPress={() => setHorizon("swing")} />
    </>
  );
}

it("defaults to short and switches horizons", () => {
  const view = render(
    <AppStateProvider>
      <Probe />
    </AppStateProvider>,
  );
  expect(view.getByText("short")).toBeTruthy();
  fireEvent.press(view.getByText("swing"));
  expect(view.getByText("swing")).toBeTruthy();
});
```

- [ ] **Step 2: Run the test to verify failure**

```bash
cd apps/mobile
npm test -- src/state/__tests__/AppStateProvider.test.tsx
```

Expected: FAIL because the provider does not exist.

- [ ] **Step 3: Implement persistence and state**

`persistence.ts` exports:

```ts
export interface StorageAdapter {
  get<T>(key: string): Promise<T | null>;
  set<T>(key: string, value: T): Promise<void>;
}

export const storage: StorageAdapter;
```

`AppStateProvider` must persist only saved plans, journal entries, and explicit UI preferences. It must not persist a modified objective score.

Use this public context shape and allowlist:

```ts
interface AppStateValue {
  horizon: Horizon;
  setHorizon(value: Horizon): void;
  savedPlans: TradePlan[];
  savePlan(plan: TradePlan): void;
  journalEntries: JournalEntry[];
  addJournalEntry(entry: JournalEntry): void;
}

const persistedKeys = {
  savedPlans: "us-stock-helper/saved-plans",
  journalEntries: "us-stock-helper/journal-entries",
  horizon: "us-stock-helper/horizon",
} as const;
```

`savePlan` stores the selected immutable fixture plan as-is. There is no setter
for `objectiveScore`, `confidence`, `StockSnapshot.baseScore`, or
`StockSnapshot.adjustedScore`.

- [ ] **Step 4: Add five-tab navigation**

The tab titles and icons are:

```ts
[
  ["index", "首页", "home-outline"],
  ["discover", "发现", "scan-outline"],
  ["alerts", "提醒", "flash-outline"],
  ["journal", "复盘", "document-text-outline"],
  ["agent", "Agent", "sparkles-outline"],
] as const;
```

Root stack routes for stock detail, chart, and advisers hide the default header. Thin route files import and export corresponding modules from `src/screens`.

- [ ] **Step 5: Run navigation and state tests**

```bash
cd apps/mobile
npm test -- src/state src/app
npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Generate the local iOS project**

Connect the iPhone by USB, unlock it, tap Trust, and enable Settings → Privacy & Security → Developer Mode.

Run:

```bash
cd apps/mobile
npx expo prebuild --platform ios
open ios/*.xcworkspace
```

In Xcode:

1. Select the app target.
2. Open Signing & Capabilities.
3. Enable Automatically manage signing.
4. Select the user's Personal Team.
5. Confirm bundle identifier `com.franz.usstockhelper.dev`.
6. Select the connected iPhone and press Run.

Expected: `US Stock Helper` appears as an independent Home Screen app.

- [ ] **Step 7: Verify Fast Refresh**

Run:

```bash
cd apps/mobile
npm run start:dev-client
```

Open the installed app, select the displayed local development server, change the temporary Dashboard heading from `US Stock Helper` to `US Stock Helper · Live Edit`, save, and confirm the iPhone updates without a rebuild. Revert the heading after verification.

- [ ] **Step 8: Commit**

Do not commit Personal Team credentials or generated signing files. If Expo's managed `.gitignore` excludes `ios/`, leave it excluded.

```bash
git add apps/mobile
git commit -m "feat: add mobile navigation and local state"
```

---

### Task 5: Implement the short-first Dashboard

**Files:**
- Create: `apps/mobile/src/components/dashboard/MarketPlaybookCard.tsx`
- Create: `apps/mobile/src/components/dashboard/PriorityAlertCard.tsx`
- Create: `apps/mobile/src/components/dashboard/WatchlistStrip.tsx`
- Create: `apps/mobile/src/components/dashboard/CandidateList.tsx`
- Create: `apps/mobile/src/screens/DashboardScreen.tsx`
- Modify: `apps/mobile/src/app/(tabs)/index.tsx`
- Test: `apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx`

**Interfaces:**
- Consumes: `DashboardSnapshot`, `useAppState()`, `fixtureRepository.getDashboard`
- Produces: navigable Dashboard with conclusion-first sentiment presentation

- [ ] **Step 1: Write the failing Dashboard test**

```tsx
import { fireEvent, render } from "@testing-library/react-native";
import { DashboardScreen } from "../DashboardScreen";
import { AppStateProvider } from "@/state/AppStateProvider";

it("shows the short market conclusion and actionable context", () => {
  const view = render(
    <AppStateProvider>
      <DashboardScreen />
    </AppStateProvider>,
  );

  expect(view.getByText("演示数据 · 非实时建议")).toBeTruthy();
  expect(view.getByText("短线 · 0–5日")).toBeTruthy();
  expect(view.getByText("谨慎偏多")).toBeTruthy();
  expect(view.getByText(/今日建议/)).toBeTruthy();
  expect(view.getByText("来自 moomoo · 演示同步")).toBeTruthy();
  expect(view.getByText("潜力候选")).toBeTruthy();

  fireEvent.press(view.getByText("波段 · 1–8周"));
  expect(view.getByText("波段环境")).toBeTruthy();
});
```

- [ ] **Step 2: Run the test to verify failure**

```bash
cd apps/mobile
npm test -- src/screens/__tests__/DashboardScreen.test.tsx
```

Expected: FAIL because `DashboardScreen` does not exist.

- [ ] **Step 3: Implement the market playbook**

`MarketPlaybookCard` renders:

- conclusion and score;
- one-sentence explanation;
- `今日建议`;
- market-news, breadth, volatility/options, sector, rates/dollar, and geopolitical drivers;
- updated time and evidence access.

Driver bars use a fixed `-100..100` scale and retain textual conclusions so color is not the only signal.

The card contract is:

```tsx
interface MarketPlaybookCardProps {
  score: number;
  confidence: number;
  scoreChange: number;
  conclusion: string;
  advice: string;
  contradictions: string[];
  drivers: MarketDriver[];
  updatedAt: string;
  onOpenEvidence(citationIds: string[]): void;
}

const normalizedWidth = (score: number) =>
  `${Math.min(Math.abs(score), 100)}%` as `${number}%`;
```

Render one row per `MarketDriver`; use `normalizedWidth(driver.score)` for the
bar, and always render `driver.conclusion` beside it.

- [ ] **Step 4: Implement alerts, watchlist, and candidates**

Pressing an alert or quote calls:

```ts
router.push({ pathname: "/stocks/[symbol]", params: { symbol } });
```

Candidate state labels map exactly:

```ts
{
  observation: "观察池",
  "action-eligible": "达到行动研究门槛",
  risk: "风险升高",
}
```

Compose the route-independent screen with the repository as its only data
source:

```tsx
export function DashboardScreen() {
  const router = useRouter();
  const { horizon, setHorizon } = useAppState();
  const snapshot = fixtureRepository.getDashboard(horizon);
  const [evidence, setEvidence] = useState<Citation[]>([]);

  return (
    <Screen>
      <DemoDataBadge />
      <HorizonSwitch value={horizon} onChange={setHorizon} />
      <DataHealthBanner
        health={snapshot.dataHealth}
        marketSession={snapshot.marketSession}
      />
      <MarketPlaybookCard
        score={snapshot.marketScore}
        confidence={snapshot.marketConfidence}
        scoreChange={snapshot.marketScoreChange}
        conclusion={snapshot.marketConclusion}
        advice={snapshot.marketAdvice}
        contradictions={snapshot.contradictions}
        drivers={snapshot.marketDrivers}
        updatedAt={snapshot.updatedAt}
        onOpenEvidence={(ids) => setEvidence(fixtureRepository.getCitations(ids))}
      />
      <PriorityAlertCard
        alert={snapshot.priorityAlert}
        onPress={() =>
          router.push({
            pathname: "/stocks/[symbol]",
            params: { symbol: snapshot.priorityAlert.symbol },
          })
        }
      />
      <WatchlistStrip
        title="来自 moomoo · 演示同步"
        quotes={snapshot.watchlist}
        onPress={(symbol) =>
          router.push({ pathname: "/stocks/[symbol]", params: { symbol } })
        }
      />
      <CandidateList
        title="潜力候选"
        candidates={snapshot.candidates}
        onPress={(symbol) =>
          router.push({ pathname: "/stocks/[symbol]", params: { symbol } })
        }
      />
      <EvidenceSheet title="市场证据" citations={evidence} />
    </Screen>
  );
}
```

- [ ] **Step 5: Compose and verify Dashboard**

```bash
cd apps/mobile
npm test -- src/screens/__tests__/DashboardScreen.test.tsx
npm run typecheck
npm run lint
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/mobile/src/components/dashboard apps/mobile/src/screens/DashboardScreen.tsx apps/mobile/src/app/'(tabs)'/index.tsx
git commit -m "feat: build short-first mobile dashboard"
```

---

### Task 6: Build the clear candlestick and indicator chart system

**Files:**
- Create: `apps/mobile/src/domain/chart.ts`
- Create: `apps/mobile/src/components/chart/CandlestickChart.tsx`
- Create: `apps/mobile/src/components/chart/ChartToolbar.tsx`
- Create: `apps/mobile/src/components/chart/ForecastBand.tsx`
- Create: `apps/mobile/src/components/chart/VolumePane.tsx`
- Create: `apps/mobile/src/components/chart/MacdPane.tsx`
- Create: `apps/mobile/src/components/chart/RsiPane.tsx`
- Create: `apps/mobile/src/screens/FullChartScreen.tsx`
- Modify: `apps/mobile/src/app/stocks/[symbol]/chart.tsx`
- Test: `apps/mobile/src/domain/__tests__/chart.test.ts`
- Test: `apps/mobile/src/components/chart/__tests__/CandlestickChart.test.tsx`

**Interfaces:**
- Consumes: `Candle[]`, `ForecastPoint[]`, interval, main overlays, sub-chart selection
- Produces: `buildChartGeometry()` and an accessible portrait/landscape chart

- [ ] **Step 1: Write failing chart-geometry tests**

```ts
import { buildChartGeometry, chartWidthForViewport } from "../chart";

const candles = [
  { timestamp: "10:00", open: 100, high: 105, low: 98, close: 103, volume: 10 },
  { timestamp: "10:05", open: 103, high: 108, low: 101, close: 102, volume: 20 },
];

it("maps the highest price above the lowest price", () => {
  const geometry = buildChartGeometry(candles, 300, 180, 12);
  expect(geometry.priceToY(108)).toBeLessThan(geometry.priceToY(98));
  expect(geometry.candles).toHaveLength(2);
});

it("keeps candle bodies at least one pixel high", () => {
  const geometry = buildChartGeometry(
    [{ timestamp: "10:00", open: 100, high: 101, low: 99, close: 100, volume: 1 }],
    300,
    180,
    12,
  );
  expect(geometry.candles[0]?.bodyHeight).toBeGreaterThanOrEqual(1);
});

it.each([320, 375, 393])("fits current compact and standard widths: %i", (width) => {
  expect(chartWidthForViewport(width) + 32).toBeLessThanOrEqual(width);
});
```

- [ ] **Step 2: Run the geometry test to verify failure**

```bash
cd apps/mobile
npm test -- src/domain/__tests__/chart.test.ts
```

Expected: FAIL because `buildChartGeometry` does not exist.

- [ ] **Step 3: Implement pure chart geometry**

Create `chart.ts` with:

```ts
export interface CandleGeometry {
  x: number;
  wickTop: number;
  wickBottom: number;
  bodyTop: number;
  bodyHeight: number;
  bodyWidth: number;
  rising: boolean;
}

export interface ChartGeometry {
  candles: CandleGeometry[];
  priceToY(price: number): number;
  minPrice: number;
  maxPrice: number;
}

export function chartWidthForViewport(viewportWidth: number) {
  return Math.max(Math.min(viewportWidth - 32, 720), 288);
}

export function buildChartGeometry(
  candles: Candle[],
  width: number,
  height: number,
  padding: number,
  extraPrices: number[] = [],
): ChartGeometry {
  if (candles.length === 0) {
    throw new Error("buildChartGeometry requires at least one candle");
  }
  const visibleLow = Math.min(
    ...candles.map((candle) => candle.low),
    ...extraPrices,
  );
  const visibleHigh = Math.max(
    ...candles.map((candle) => candle.high),
    ...extraPrices,
  );
  const priceRange = Math.max(visibleHigh - visibleLow, 0.01);
  const minPrice = visibleLow - priceRange * 0.05;
  const maxPrice = visibleHigh + priceRange * 0.05;
  const drawableWidth = Math.max(width - padding * 2, 1);
  const drawableHeight = Math.max(height - padding * 2, 1);
  const slotWidth = drawableWidth / candles.length;
  const priceToY = (price: number) =>
    padding + ((maxPrice - price) / (maxPrice - minPrice)) * drawableHeight;

  return {
    minPrice,
    maxPrice,
    priceToY,
    candles: candles.map((candle, index) => {
      const openY = priceToY(candle.open);
      const closeY = priceToY(candle.close);
      return {
        x: padding + slotWidth * index + slotWidth / 2,
        wickTop: priceToY(candle.high),
        wickBottom: priceToY(candle.low),
        bodyTop: Math.min(openY, closeY),
        bodyHeight: Math.max(Math.abs(closeY - openY), 1),
        bodyWidth: Math.max(Math.min(slotWidth * 0.62, 12), 2),
        rising: candle.close >= candle.open,
      };
    }),
  };
}
```

Import `Candle` from `models.ts`. The implementation above uses the visible
high and low plus 5% vertical padding and keeps `bodyHeight >= 1`.

- [ ] **Step 4: Write the failing rendered-chart test**

```tsx
import { fireEvent, render } from "@testing-library/react-native";
import { CandlestickChart } from "../CandlestickChart";
import { fixtureRepository } from "@/fixtures/repository";

it("renders candles, forecast distinction, and mandatory event markers", () => {
  const stock = fixtureRepository.getStock("NVDA", "short");
  const view = render(
    <CandlestickChart
      candles={stock.candles}
      forecast={stock.forecast}
      magicNine={stock.magicNine}
      dragonTrend={stock.dragonTrend}
      patterns={stock.patterns}
      width={360}
      height={280}
    />,
  );

  expect(view.getByLabelText("K线主图")).toBeTruthy();
  expect(view.getByText("预测起点")).toBeTruthy();
  expect(view.getByText("九转 7 · 未完成")).toBeTruthy();
  expect(view.getByText("50% / 80% 概率区间")).toBeTruthy();
  fireEvent.press(view.getByLabelText("展开形态：回踩五日线后企稳"));
  expect(view.getByText("收盘跌破 136.40")).toBeTruthy();
});
```

- [ ] **Step 5: Implement chart rendering**

Use `react-native-svg`:

- `Line` and `Rect` for wicks and bodies;
- right price axis and bottom time axis;
- grid lines with low contrast;
- moving-average/VWAP paths;
- dashed "now" boundary;
- separate 50% and 80% forecast polygons;
- event markers `N`, `G`, and Magic Nine count;
- press/move crosshair that displays OHLC, time, volume;
- explicit text `预测区间不是保证`.

Do not place long analysis text over candles.

The main SVG loop is:

```tsx
interface CandlestickChartProps {
  candles: Candle[];
  forecast: ForecastSnapshot;
  magicNine: StockSnapshot["magicNine"];
  dragonTrend: StockSnapshot["dragonTrend"];
  patterns: PatternSignal[];
  width: number;
  height: number;
}

const forecastPrices = forecast.points.flatMap((point) => [
  point.lower80,
  point.upper80,
]);
const geometry = buildChartGeometry(candles, width, height, 16, forecastPrices);

return (
  <View accessibilityLabel="K线主图">
    <Svg width={width} height={height}>
      {geometry.candles.map((candle, index) => (
        <G key={candles[index]!.timestamp}>
          <Line
            x1={candle.x}
            x2={candle.x}
            y1={candle.wickTop}
            y2={candle.wickBottom}
            stroke={candle.rising ? colors.green : colors.red}
          />
          <Rect
            x={candle.x - candle.bodyWidth / 2}
            y={candle.bodyTop}
            width={candle.bodyWidth}
            height={candle.bodyHeight}
            fill={candle.rising ? colors.green : colors.red}
          />
        </G>
      ))}
      <ForecastBand
        points={forecast.points}
        width={width}
        padding={16}
        priceToY={geometry.priceToY}
      />
    </Svg>
    <Text>预测起点</Text>
    <Text>{`九转 ${magicNine.count} · ${magicNine.complete ? "完成" : "未完成"}`}</Text>
    <Text>{`神龙趋势 · ${dragonTrend.state} · ${dragonTrend.methodVersion}`}</Text>
    <Text>50% / 80% 概率区间</Text>
    <Text>{`上涨 ${(forecast.probability.up * 100).toFixed(0)}% · 横盘 ${(forecast.probability.flat * 100).toFixed(0)}% · 下跌 ${(forecast.probability.down * 100).toFixed(0)}%`}</Text>
    <Text>{`历史校准误差 ${(forecast.calibrationError * 100).toFixed(1)}% · ${forecast.modelVersion}`}</Text>
    <Text>{`${forecast.horizon} · 生成于 ${forecast.predictedAt}`}</Text>
    <Text>{`预测失效：${forecast.invalidation}`}</Text>
    <Text>预测区间不是保证</Text>
  </View>
);
```

`ForecastBand` maps each forecast index evenly between `padding` and
`width - padding`; it draws the 80% polygon first at lower opacity and the 50%
polygon second at higher opacity.
The crosshair is component-local state and does not write to `AppStateProvider`.
Each derived pattern marker has
`accessibilityLabel={\`展开形态：${pattern.name}\`}` and sets local
`selectedPattern`; a small sheet then renders `status`, `complete`, `horizon`,
and `invalidation` without covering the candle viewport.

- [ ] **Step 6: Add the indicator panes and toolbar**

Main overlay identifiers:

```ts
type ChartInterval = "1m" | "5m" | "15m" | "30m" | "1h" | "1d" | "1w";
type MainOverlay =
  | "ma"
  | "ema"
  | "vwap"
  | "boll"
  | "magic-nine"
  | "dragon-trend"
  | "forecast"
  | "patterns"
  | "support-resistance";
type SubPane = "volume" | "macd" | "rsi" | "participation";
```

The full chart defaults to `macd`, but toolbar selection must allow `rsi` and `participation`.

```tsx
const [subPane, setSubPane] = useState<SubPane>("macd");
const [evidence, setEvidence] = useState<Citation[]>([]);
const panes: Record<SubPane, React.ReactNode> = {
  volume: <VolumePane candles={stock.candles} />,
  macd: <MacdPane histogram={stock.indicators.macd.histogram} />,
  rsi: <RsiPane value={stock.indicators.rsi} />,
  participation: (
    <ParticipationCard
      value={stock.participationProxy}
      onOpenEvidence={(ids) =>
        setEvidence(fixtureRepository.getCitations(ids))
      }
    />
  ),
};
```

Render `<EvidenceSheet title="图表证据" citations={evidence} />` below the
selected pane.

- [ ] **Step 7: Implement orientation lifecycle**

```ts
useEffect(() => {
  void ScreenOrientation.lockAsync(
    ScreenOrientation.OrientationLock.LANDSCAPE,
  );
  return () => {
    void ScreenOrientation.lockAsync(
      ScreenOrientation.OrientationLock.PORTRAIT_UP,
    );
  };
}, []);
```

- [ ] **Step 8: Run chart tests**

```bash
cd apps/mobile
npm test -- src/domain/__tests__/chart.test.ts src/components/chart
npm run typecheck
npm run lint
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/mobile/src/domain/chart.ts apps/mobile/src/domain/__tests__/chart.test.ts apps/mobile/src/components/chart apps/mobile/src/screens/FullChartScreen.tsx apps/mobile/src/app/stocks
git commit -m "feat: add professional mobile candlestick charts"
```

---

### Task 7: Build stock detail with mandatory RSI, MACD, and ownership views

**Files:**
- Create: `apps/mobile/src/components/stock/StockHeader.tsx`
- Create: `apps/mobile/src/components/stock/RsiCard.tsx`
- Create: `apps/mobile/src/components/stock/MacdCard.tsx`
- Create: `apps/mobile/src/components/stock/ParticipationCard.tsx`
- Create: `apps/mobile/src/components/stock/ReportedOwnershipCard.tsx`
- Create: `apps/mobile/src/components/stock/SignalSummaryCard.tsx`
- Create: `apps/mobile/src/components/stock/MarketContextCard.tsx`
- Create: `apps/mobile/src/components/stock/FundamentalsCard.tsx`
- Create: `apps/mobile/src/components/stock/EventChainCard.tsx`
- Create: `apps/mobile/src/screens/StockDetailScreen.tsx`
- Modify: `apps/mobile/src/app/stocks/[symbol]/index.tsx`
- Test: `apps/mobile/src/screens/__tests__/StockDetailScreen.test.tsx`

**Interfaces:**
- Consumes: `fixtureRepository.getStock(symbol, horizon)`
- Produces: portrait stock detail and navigation to chart, evidence, and advisers

- [ ] **Step 1: Write the failing mandatory-content test**

```tsx
import { render } from "@testing-library/react-native";
import { StockDetailScreen } from "../StockDetailScreen";
import { AppStateProvider } from "@/state/AppStateProvider";

it("never omits RSI, MACD, and both ownership views", () => {
  const view = render(
    <AppStateProvider>
      <StockDetailScreen symbol="NVDA" />
    </AppStateProvider>,
  );

  expect(view.getByText("RSI · 14")).toBeTruthy();
  expect(view.getByText("63.8")).toBeTruthy();
  expect(view.getByText("MACD")).toBeTruthy();
  expect(view.getByText("盘中参与结构 · 估算代理")).toBeTruthy();
  expect(view.getByText("置信度：中")).toBeTruthy();
  expect(view.getByText("正式披露持仓")).toBeTruthy();
  expect(view.getByText(/报告期/)).toBeTruthy();
  expect(view.getByText("财务健康与基本面")).toBeTruthy();
  expect(view.getByText(/神龙趋势/)).toBeTruthy();
});
```

- [ ] **Step 2: Run the test to verify failure**

```bash
cd apps/mobile
npm test -- src/screens/__tests__/StockDetailScreen.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Implement the default-visible indicator cards**

`RsiCard` always displays value, period, state, direction, and divergence. `MacdCard` always displays DIF, DEA, histogram, and state. Neither card is conditional on landscape sub-pane state.

```tsx
export function RsiCard({ value }: { value: RsiSnapshot }) {
  return (
    <View accessibilityLabel={`RSI ${value.period}，${value.value}`}>
      <Text accessibilityRole="header">RSI · {value.period}</Text>
      <Text>{value.value.toFixed(1)}</Text>
      <Text>{`${value.interval} · ${value.state} · ${value.direction} · 背离 ${value.divergence}`}</Text>
    </View>
  );
}

export function MacdCard({ value }: { value: MacdSnapshot }) {
  return (
    <View accessibilityLabel={`MACD，${value.state}`}>
      <Text accessibilityRole="header">MACD</Text>
      <Text>{`${value.interval} · DIF ${value.dif.toFixed(2)} · DEA ${value.dea.toFixed(2)}`}</Text>
      <MacdPane histogram={value.histogram} />
      <Text>{`${value.state} · ${value.crossover}`}</Text>
    </View>
  );
}
```

- [ ] **Step 4: Implement both ownership interpretations**

`ParticipationCard` text includes:

```text
盘中参与结构 · 估算代理
并非真实账户标签
置信度：中
```

`ReportedOwnershipCard` text includes:

```text
正式披露持仓
报告期：YYYY-MM-DD
披露数据存在滞后
```

Both render institution, retail/other, and citation access without implying exact real-time ownership.

Their public props are deliberately different so the two concepts cannot be
accidentally merged:

```ts
interface ParticipationCardProps {
  value: ParticipationProxy;
  onOpenEvidence(citationIds: string[]): void;
}

interface ReportedOwnershipCardProps {
  value: ReportedOwnership;
  onOpenEvidence(citationIds: string[]): void;
}
```

`ParticipationCard` renders a labeled stacked histogram whose two widths are
`institutionalPercent%` and `retailPercent%`, followed by `methodVersion`,
`sourceCoverage`, `estimatedAt`, and confidence. `ReportedOwnershipCard`
renders a separate dated histogram plus every item in `changes`; the two cards
must not share a title or timestamp label.

- [ ] **Step 5: Compose the stock detail**

Order:

1. demo badge and stock header;
2. compact chart with timeframe and overlay toggles;
3. RSI and MACD side-by-side;
4. participation proxy;
5. reported ownership;
6. market/macro/geopolitical context;
7. current event chain and company filings;
8. financial health, cash, debt, dilution, runway, margins, growth, valuation,
   industry/supply-chain context, and material risks;
9. algorithm conclusion, counter-case, evidence counts;
10. `查看证据` and `问顾问 / 制定方案`.

`StockHeader` renders `symbol`, `company`, `exchange`, `price`,
`changePercent`, `marketSession`, `quoteLatencyMs`, `watchlisted`, and
`horizon`; none of those values are inferred in the component.
`MarketContextCard` renders the raw `baseScore`,
`marketContext.scoreAdjustment`, final `adjustedScore`, and every
`marketContext.planChanges` item so context never changes the recommendation
silently.

```tsx
export function StockDetailScreen({ symbol }: { symbol: string }) {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { horizon } = useAppState();
  const stock = fixtureRepository.getStock(symbol, horizon);
  const chartWidth = chartWidthForViewport(width);
  const [evidence, setEvidence] = useState<Citation[]>([]);
  const openEvidence = (ids: string[]) =>
    setEvidence(fixtureRepository.getCitations(ids));

  return (
    <Screen>
      <DemoDataBadge />
      <StockHeader stock={stock} />
      <CandlestickChart
        candles={stock.candles}
        forecast={stock.forecast}
        magicNine={stock.magicNine}
        dragonTrend={stock.dragonTrend}
        patterns={stock.patterns}
        width={chartWidth}
        height={260}
      />
      <View style={{ flexDirection: "row" }}>
        <RsiCard value={stock.indicators.rsi} />
        <MacdCard value={stock.indicators.macd} />
      </View>
      <ParticipationCard value={stock.participationProxy} onOpenEvidence={openEvidence} />
      <ReportedOwnershipCard value={stock.reportedOwnership} onOpenEvidence={openEvidence} />
      <MarketContextCard stock={stock} />
      <EventChainCard citations={stock.citations} />
      <FundamentalsCard value={stock.fundamentals} />
      <SignalSummaryCard stock={stock} />
      <Button
        title="查看证据"
        onPress={() => setEvidence(stock.citations)}
      />
      <Button
        title="问顾问 / 制定方案"
        onPress={() =>
          router.push({
            pathname: "/stocks/[symbol]/advisers",
            params: { symbol: stock.symbol },
          })
        }
      />
      <EvidenceSheet title={`${stock.symbol} 证据`} citations={evidence} />
    </Screen>
  );
}
```

- [ ] **Step 6: Verify**

```bash
cd apps/mobile
npm test -- src/screens/__tests__/StockDetailScreen.test.tsx
npm run typecheck
npm run lint
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/mobile/src/components/stock apps/mobile/src/screens/StockDetailScreen.tsx apps/mobile/src/app/stocks
git commit -m "feat: add complete stock analysis detail"
```

---

### Task 8: Add adviser selection and deterministic long/short plans

**Files:**
- Create: `apps/mobile/src/domain/plan.ts`
- Create: `apps/mobile/src/components/advisers/AdviserSelector.tsx`
- Create: `apps/mobile/src/components/advisers/ConsensusBar.tsx`
- Create: `apps/mobile/src/components/advisers/RiskPreferenceSelector.tsx`
- Create: `apps/mobile/src/components/advisers/TradePlanCard.tsx`
- Create: `apps/mobile/src/components/advisers/RiskGuardrail.tsx`
- Create: `apps/mobile/src/screens/AdviserPlanScreen.tsx`
- Modify: `apps/mobile/src/app/stocks/[symbol]/advisers.tsx`
- Test: `apps/mobile/src/domain/__tests__/plan.test.ts`
- Test: `apps/mobile/src/screens/__tests__/AdviserPlanScreen.test.tsx`

**Interfaces:**
- Consumes: `StockSnapshot`, `AdviserOpinion[]`, `PlanSide`, `RiskPreference`
- Produces: `selectTradePlan(plans, side, preference)` with invariant objective score and confidence

- [ ] **Step 1: Write the failing plan-invariant test**

```ts
import { selectTradePlan } from "../plan";
import { tradePlanFixtures } from "@/fixtures/advisers";

it("changes execution parameters without changing objective analysis", () => {
  const conservative = selectTradePlan(tradePlanFixtures, "long", "conservative");
  const aggressive = selectTradePlan(tradePlanFixtures, "long", "aggressive");

  expect(aggressive.leverage).toBeGreaterThanOrEqual(conservative.leverage);
  expect(aggressive.leverage).toBeLessThanOrEqual(aggressive.maximumLeverage);
  expect(aggressive.objectiveScore).toBe(conservative.objectiveScore);
  expect(aggressive.confidence).toBe(conservative.confidence);
  expect(aggressive.riskWarning.length).toBeGreaterThan(0);
  expect(new Set(tradePlanFixtures.map((plan) => plan.objectiveScore)).size).toBe(1);
  expect(new Set(tradePlanFixtures.map((plan) => plan.confidence)).size).toBe(1);
});

it("adds borrow and unlimited-loss warnings to short plans", () => {
  const plan = selectTradePlan(tradePlanFixtures, "short", "balanced");
  expect(plan.shortRisk?.borrowAvailable).toBe(true);
  expect(plan.riskWarning).toMatch(/借券/);
  expect(plan.riskWarning).toMatch(/无限损失/);
});
```

- [ ] **Step 2: Run the test to verify failure**

```bash
cd apps/mobile
npm test -- src/domain/__tests__/plan.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement exact selection**

```ts
export function selectTradePlan(
  plans: TradePlan[],
  side: PlanSide,
  preference: RiskPreference,
): TradePlan {
  const plan = plans.find(
    (candidate) => candidate.side === side && candidate.preference === preference,
  );
  if (!plan) throw new Error(`Missing ${side}/${preference} trade plan`);
  return plan;
}
```

All six long/short × preference fixtures share the same `objectiveScore` and `confidence`.

- [ ] **Step 4: Implement the adviser UI**

The screen displays all 13 available styles but activates only the four fixture-selected advisers by default. It shows:

- `风格模型，非本人意见`;
- evidence snapshot identifier;
- base score;
- bounded adviser adjustment;
- active, abstained, and opposing states;
- strongest adviser conflict;
- `只调整方案，不调整事实`.

Use local selection state only; adviser selection never mutates the repository:

```tsx
const [activeIds, setActiveIds] = useState(
  () => new Set(opinions.filter((opinion) => opinion.active).map((opinion) => opinion.id)),
);
const activeOpinions = opinions.filter((opinion) => activeIds.has(opinion.id));
const boundedAdjustment = Math.max(
  -5,
  Math.min(5, activeOpinions.reduce(
    (sum, opinion) => sum + (opinion.direction === "bullish" ? 1 : -1),
    0,
  )),
);
```

Display both `stock.baseScore` and
`stock.baseScore + boundedAdjustment`; label the latter `顾问软因子调整后`.

- [ ] **Step 5: Implement plan controls and hard warnings**

Long/short and risk preference controls update:

- entry range;
- entry method;
- quantity;
- risk budget and estimated reward/risk;
- leverage;
- maximum leverage;
- invalidation;
- stop logic and cancellation conditions;
- target range;
- holding window;
- risk warning.

For short plans, `TradePlanCard` additionally renders borrow availability and
timestamp, estimated borrow fee, short interest, crowding, squeeze/gap,
halt/recall, and unbounded-loss warnings from `plan.shortRisk`.

The only actions are:

```text
保存分析方案
复制参数，前往 moomoo 手动下单
```

No button may use the Chinese text `下单`, except inside the explicit phrase `手动下单`, and no handler may call an order API.

```tsx
const [side, setSide] = useState<PlanSide>("long");
const [preference, setPreference] = useState<RiskPreference>("balanced");
const plan = selectTradePlan(plans, side, preference);
const formatPlanForClipboard = (value: TradePlan) =>
  [
    `${value.symbol} ${value.side}`,
    `限价 ${value.entryRange[0]}–${value.entryRange[1]}`,
    `数量 ${value.quantity}`,
    `杠杆 ${value.leverage}x（上限 ${value.maximumLeverage}x）`,
    `失效价 ${value.invalidationPrice}`,
    `目标 ${value.targetRange[0]}–${value.targetRange[1]}`,
    "仅供分析，请在 moomoo 独立核对后手动输入。",
  ].join("\n");

return (
  <>
    <AdviserSelector opinions={opinions} activeIds={activeIds} onChange={setActiveIds} />
    <ConsensusBar baseScore={stock.baseScore} adjustment={boundedAdjustment} />
    <RiskPreferenceSelector
      side={side}
      preference={preference}
      onSideChange={setSide}
      onPreferenceChange={setPreference}
    />
    <Text>只调整方案，不调整事实</Text>
    <TradePlanCard plan={plan} />
    <RiskGuardrail plan={plan} />
    <Button title="保存分析方案" onPress={() => savePlan(plan)} />
    <Button
      title="复制参数，前往 moomoo 手动下单"
      onPress={() => Clipboard.setStringAsync(formatPlanForClipboard(plan))}
    />
  </>
);
```

Install `expo-clipboard` with `npx expo install expo-clipboard`. The second
button only copies text; it does not deep-link until the user approves that
behavior in a later project.

- [ ] **Step 6: Run tests**

```bash
cd apps/mobile
npm test -- src/domain/__tests__/plan.test.ts src/screens/__tests__/AdviserPlanScreen.test.tsx
npm run typecheck
npm run lint
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/mobile/src/domain/plan.ts apps/mobile/src/domain/__tests__/plan.test.ts apps/mobile/src/components/advisers apps/mobile/src/screens/AdviserPlanScreen.tsx apps/mobile/src/app/stocks
git commit -m "feat: add adviser and risk plan demo"
```

---

### Task 9: Implement Discover and alert threads

**Files:**
- Create: `apps/mobile/src/components/discover/CandidateFilterBar.tsx`
- Create: `apps/mobile/src/components/discover/CandidateCard.tsx`
- Create: `apps/mobile/src/screens/DiscoverScreen.tsx`
- Create: `apps/mobile/src/components/alerts/AlertThreadCard.tsx`
- Create: `apps/mobile/src/screens/AlertsScreen.tsx`
- Modify: `apps/mobile/src/app/(tabs)/discover.tsx`
- Modify: `apps/mobile/src/app/(tabs)/alerts.tsx`
- Test: `apps/mobile/src/screens/__tests__/DiscoverScreen.test.tsx`
- Test: `apps/mobile/src/screens/__tests__/AlertsScreen.test.tsx`

**Interfaces:**
- Consumes: `Candidate[]`, `AlertThread[]`
- Produces: side/horizon filters, observation/action/risk states, navigable deduplicated alert threads

- [ ] **Step 1: Write failing discovery and alert tests**

```tsx
it("does not call an observation candidate an action alert", () => {
  const view = render(<DiscoverScreen />);
  expect(view.getByText("观察池")).toBeTruthy();
  expect(view.queryByText("保证翻倍")).toBeNull();
});

it("shows evidence and counter-evidence counts", () => {
  const view = render(<AlertsScreen />);
  expect(view.getByText(/证据 \d+/)).toBeTruthy();
  expect(view.getByText(/反证 \d+/)).toBeTruthy();
});
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd apps/mobile
npm test -- src/screens/__tests__/DiscoverScreen.test.tsx src/screens/__tests__/AlertsScreen.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Implement Discover**

Filters:

```ts
type SideFilter = "all" | "long" | "short";
type CandidateStateFilter = "all" | "observation" | "action-eligible" | "risk";
interface CandidateFilters {
  side: SideFilter;
  state: CandidateStateFilter;
  horizon: Horizon | "all";
  freshness: Candidate["evidenceFreshness"] | "all";
  liquidity: Candidate["liquidityRisk"] | "all";
  query: string;
}
```

Candidate cards show score, catalyst, evidence freshness, institutional proxy,
technical state, fundamental state, volatility, liquidity/risk label,
evidence/counter-evidence count, and reason. `CandidateFilterBar` provides
horizon, long/short, state, freshness, liquidity, and text filters; catalyst,
institutional, technical, fundamental, volatility, and risk fields are all
visible for manual inspection in the first demo.

```tsx
const [filters, setFilters] = useState<CandidateFilters>({
  side: "all",
  state: "all",
  horizon: "all",
  freshness: "all",
  liquidity: "all",
  query: "",
});
const visibleCandidates = candidates.filter((candidate) =>
  (filters.side === "all" || candidate.side === filters.side) &&
  (filters.state === "all" || candidate.state === filters.state) &&
  (filters.horizon === "all" || candidate.horizon === filters.horizon) &&
  (filters.freshness === "all" || candidate.evidenceFreshness === filters.freshness) &&
  (filters.liquidity === "all" || candidate.liquidityRisk === filters.liquidity) &&
  `${candidate.symbol} ${candidate.company} ${candidate.catalyst}`
    .toLowerCase()
    .includes(filters.query.trim().toLowerCase()),
);

return (
  <>
    <CandidateFilterBar value={filters} onChange={setFilters} />
    <FlatList
      data={visibleCandidates}
      keyExtractor={(candidate) => `${candidate.symbol}-${candidate.side}`}
      renderItem={({ item }) => (
        <CandidateCard
          candidate={item}
          onPress={() =>
            router.push({
              pathname: "/stocks/[symbol]",
              params: { symbol: item.symbol },
            })
          }
        />
      )}
    />
  </>
);
```

- [ ] **Step 4: Implement alert threads**

Group related alert fixture updates by `AlertThread.id`. Show severity, horizon,
trigger time, source freshness, current state, updated time,
base-score contribution, bounded adviser adjustment, evidence/counter-evidence,
invalidation, and citation drawer.

```tsx
const alerts = latestAlertThreads(fixtureRepository.getAlerts());
const [evidence, setEvidence] = useState<Citation[]>([]);

return (
  <>
    <FlatList
      data={alerts}
      keyExtractor={(alert) => alert.id}
      renderItem={({ item }) => (
        <AlertThreadCard
          alert={item}
          onPress={() =>
            router.push({
              pathname: "/stocks/[symbol]",
              params: { symbol: item.symbol },
            })
          }
          onOpenEvidence={() => setEvidence(item.citations)}
        />
      )}
    />
    <EvidenceSheet title="提醒证据" citations={evidence} />
  </>
);
```

No time-window event may become a second card when its `id` already exists;
replace the prior array entry before rendering.

```ts
export function latestAlertThreads(alerts: AlertThread[]) {
  const byId = new Map<string, AlertThread>();
  for (const alert of alerts) {
    const previous = byId.get(alert.id);
    if (!previous || alert.updatedAt > previous.updatedAt) {
      byId.set(alert.id, alert);
    }
  }
  return [...byId.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}
```

- [ ] **Step 5: Verify and commit**

```bash
cd apps/mobile
npm test -- src/screens/__tests__/DiscoverScreen.test.tsx src/screens/__tests__/AlertsScreen.test.tsx
npm run typecheck
npm run lint
git add apps/mobile/src/components/discover apps/mobile/src/components/alerts apps/mobile/src/screens/DiscoverScreen.tsx apps/mobile/src/screens/AlertsScreen.tsx apps/mobile/src/app/'(tabs)'
git commit -m "feat: add discovery and alert workflows"
```

---

### Task 10: Implement Journal and the objective Agent conversation

**Files:**
- Create: `apps/mobile/src/components/journal/JournalEntryForm.tsx`
- Create: `apps/mobile/src/components/journal/JournalEntryCard.tsx`
- Create: `apps/mobile/src/screens/JournalScreen.tsx`
- Create: `apps/mobile/src/components/agent/ConversationMessage.tsx`
- Create: `apps/mobile/src/components/agent/PromptBar.tsx`
- Create: `apps/mobile/src/screens/AgentScreen.tsx`
- Modify: `apps/mobile/src/app/(tabs)/journal.tsx`
- Modify: `apps/mobile/src/app/(tabs)/agent.tsx`
- Test: `apps/mobile/src/screens/__tests__/JournalScreen.test.tsx`
- Test: `apps/mobile/src/screens/__tests__/AgentScreen.test.tsx`

**Interfaces:**
- Consumes: `useAppState()` journal actions and safe conversation fixtures
- Produces: locally persisted journal and deterministic, cited conversation demo

- [ ] **Step 1: Write failing behavior tests**

```tsx
it("records an operation without changing market confidence", () => {
  const view = render(
    <AppStateProvider>
      <JournalScreen />
    </AppStateProvider>,
  );
  fireEvent.changeText(view.getByLabelText("股票代码"), "NVDA");
  fireEvent.changeText(view.getByLabelText("成交价格"), "141.20");
  fireEvent.press(view.getByText("保存复盘"));
  expect(view.getByText("NVDA")).toBeTruthy();
  expect(view.getByText(/仅用于执行复盘/)).toBeTruthy();
});

it("puts objective analysis before personalization", () => {
  const view = render(<AgentScreen />);
  const headings = view.getAllByRole("header").map((node) => node.props.children);
  expect(headings.indexOf("客观结论")).toBeLessThan(headings.indexOf("个性化风险场景"));
  expect(view.getByText("最强反证")).toBeTruthy();
  expect(view.getByText("引用")).toBeTruthy();
});
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd apps/mobile
npm test -- src/screens/__tests__/JournalScreen.test.tsx src/screens/__tests__/AgentScreen.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Implement the Journal**

Fields: symbol, side, quantity, execution price, timestamp, realized/unrealized
P&L, plan followed/overridden, execution delay, slippage, and notes. Show:

```text
用户日志仅用于执行复盘、风险提醒和界面偏好，不进入股票方向评分。
```

`JournalEntryForm` owns controlled string inputs, validates finite numeric
values, and submits this exact domain object:

```ts
const entry: JournalEntry = {
  id: `${symbol}-${executedAt}`,
  symbol: symbol.trim().toUpperCase(),
  side,
  quantity: Number(quantity),
  executionPrice: Number(executionPrice),
  executedAt,
  executionDelaySeconds: Number(executionDelaySeconds),
  pnl: Number(pnl),
  pnlState,
  decision,
  slippage: Number(slippage),
  notes: notes.trim(),
};

const valid =
  entry.symbol.length > 0 &&
  Number.isFinite(entry.quantity) &&
  entry.quantity > 0 &&
  Number.isFinite(entry.executionPrice) &&
  entry.executionPrice > 0 &&
  Number.isFinite(entry.executionDelaySeconds) &&
  entry.executionDelaySeconds >= 0;
```

Disable `保存复盘` while `valid` is false. `addJournalEntry(entry)` is the only
submit effect.

- [ ] **Step 4: Implement the Agent fixture conversation**

Every assistant fixture renders these sections in order:

1. 客观结论
2. 证据
3. 最强反证
4. 缺失信息与不确定性
5. 个性化风险场景
6. 引用

Prompt shortcuts:

```text
为什么偏多？
给我做空反方论证
查看全部引用
换成稳健方案
申请补充调查
```

The UI records user messages locally but never mutates fixture base scores.

```tsx
const turns = fixtureRepository.getConversation();
const [localMessages, setLocalMessages] = useState<string[]>([]);
const appendLocalUserMessage = (message: string) => {
  setLocalMessages((current) => [...current, message]);
  if (message === "申请补充调查") {
    setLocalMessages((current) => [
      ...current,
      "演示请求已记录；真实信息层尚未接入",
    ]);
  }
};

return (
  <Screen>
    <DemoDataBadge />
    {turns.map((turn) => (
      <ConversationMessage key={turn.id} turn={turn} />
    ))}
    {localMessages.map((message, index) => (
      <Text key={`${index}-${message}`}>{message}</Text>
    ))}
    <PromptBar
      shortcuts={["为什么偏多？", "给我做空反方论证", "查看全部引用", "换成稳健方案", "申请补充调查"]}
      onSubmit={appendLocalUserMessage}
    />
  </Screen>
);
```

`ConversationMessage` renders `turn.sections` in array order with
`accessibilityRole="header"` on every title. It does not reorder sections based
on user preference. In Project 1, `申请补充调查` appends
`演示请求已记录；真实信息层尚未接入` locally; it makes no network call.

- [ ] **Step 5: Verify and commit**

```bash
cd apps/mobile
npm test -- src/screens/__tests__/JournalScreen.test.tsx src/screens/__tests__/AgentScreen.test.tsx
npm run typecheck
npm run lint
git add apps/mobile/src/components/journal apps/mobile/src/components/agent apps/mobile/src/screens/JournalScreen.tsx apps/mobile/src/screens/AgentScreen.tsx apps/mobile/src/app/'(tabs)'
git commit -m "feat: add journal and objective agent demo"
```

---

### Task 11: Add degraded states, safety assertions, accessibility, and full verification

**Files:**
- Modify: `apps/mobile/src/components/ui/DataHealthBanner.tsx`
- Create: `apps/mobile/src/components/ui/EmptyState.tsx`
- Create: `apps/mobile/src/components/ui/ErrorBoundary.tsx`
- Create: `apps/mobile/src/__tests__/safety.test.ts`
- Create: `apps/mobile/src/__tests__/app-smoke.test.tsx`
- Create: `apps/mobile/README.md`
- Modify: screens to use degraded-state components

**Interfaces:**
- Consumes: data-health fixture state
- Produces: explicit stale, conflict, missing proxy, and unavailable forecast states; installation/refresh documentation

- [ ] **Step 1: Write the failing global safety test**

```ts
import fs from "node:fs";
import path from "node:path";

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return entry.name === "__tests__" ? [] : sourceFiles(full);
    }
    return /\.(ts|tsx)$/.test(entry.name) ? [full] : [];
  });
}

it("contains no broker order API or autonomous trading copy", () => {
  const text = sourceFiles(path.join(process.cwd(), "src"))
    .map((file) => fs.readFileSync(file, "utf8"))
    .join("\n");

  expect(text).not.toMatch(/submitOrder|placeOrder|cancelOrder|自动下单|保证翻倍/);
});
```

- [ ] **Step 2: Run the safety test to verify the current state**

```bash
cd apps/mobile
npm test -- src/__tests__/safety.test.ts
```

Expected: PASS unless prohibited copy or APIs were accidentally introduced; if it fails, remove the prohibited implementation rather than weakening the assertion.

- [ ] **Step 3: Implement exact degraded states**

`DataHealthBanner` variants:

Use the `DataHealth` type from `src/domain/models.ts`.

Required copy:

- stale: `数据已过期，行动提醒暂停`;
- conflict: `来源存在冲突，请先查看证据`;
- insufficient proxy: `覆盖不足，无法可靠估算主力/散户参与结构`;
- unavailable forecast: `校准数据不足，预测区间暂不显示`.

```ts
const dataHealthCopy: Record<Exclude<DataHealth, "fresh">, string> = {
  stale: "数据已过期，行动提醒暂停",
  conflict: "来源存在冲突，请先查看证据",
  insufficient: "覆盖不足，无法可靠估算主力/散户参与结构",
};

export function canShowForecast(pointCount: number, calibrated: boolean) {
  return calibrated && pointCount >= 8;
}
```

When `canShowForecast` is false, render
`校准数据不足，预测区间暂不显示` and omit forecast SVG polygons. When
`DataHealth` is not `fresh`, action-severity UI is visually disabled and its
button handler is not attached.

- [ ] **Step 4: Add accessibility semantics**

All presses use at least 44×44-point hit areas. Scores include text labels. Candle colors are accompanied by OHLC and direction text. Buttons have `accessibilityRole="button"` and descriptive labels. Charts expose a summary label containing symbol, interval, direction, high, low, and forecast availability.

Use this shared press target style and chart-label helper:

```ts
export const minimumPressTarget = { minWidth: 44, minHeight: 44 } as const;

export function chartAccessibilityLabel(
  symbol: string,
  interval: string,
  candles: Candle[],
  hasForecast: boolean,
) {
  const high = Math.max(...candles.map((candle) => candle.high));
  const low = Math.min(...candles.map((candle) => candle.low));
  const first = candles[0]!;
  const last = candles[candles.length - 1]!;
  const direction = last.close >= first.open ? "上涨" : "下跌";
  return `${symbol} ${interval} K线，${direction}，最高 ${high.toFixed(2)}，最低 ${low.toFixed(2)}，${hasForecast ? "含预测区间" : "无预测区间"}`;
}
```

- [ ] **Step 5: Write and run the smoke test**

`app-smoke.test.tsx` imports each screen and verifies that it renders with fixtures and a demo badge. Then run:

```bash
cd apps/mobile
npm test
npm run typecheck
npm run lint
npx expo export --platform ios
```

Expected: all tests, typecheck, lint, and export pass.

- [ ] **Step 6: Document the local device workflow**

Create `apps/mobile/README.md` with:

```markdown
# US Stock Helper Mobile Demo

## Start Fast Refresh

`npm run start:dev-client`

The Mac and iPhone must be on the same network. Open the installed
US Stock Helper development app and select the local server.

## Reinstall after free-signing expiry

Free Apple Personal Team profiles expire after 7 days:

1. Connect and trust the iPhone.
2. Open `ios/*.xcworkspace`.
3. Confirm the Personal Team under Signing & Capabilities.
4. Select the iPhone and press Run.

The app is analysis-only and contains demo data. It cannot place orders.
```

- [ ] **Step 7: Perform final iPhone acceptance**

On the physical iPhone:

1. verify Home Screen launch;
2. verify Dashboard short default and horizon switching;
3. open NVDA;
4. confirm RSI, MACD, reported ownership, and estimated participation are all visible;
5. open landscape chart and switch MACD → RSI → participation;
6. verify Magic Nine and probability band;
7. open adviser plan and switch long/short plus all three risk preferences;
8. verify objective score and confidence remain unchanged;
9. save a plan and journal entry;
10. verify evidence links open;
11. edit one label in source and confirm Fast Refresh;
12. confirm no order can be submitted.

- [ ] **Step 8: Commit**

```bash
git add apps/mobile
git commit -m "test: harden iphone demo safety and delivery"
```

---

## Final Result

After Task 11, the user has:

- a standalone US Stock Helper development app on their own iPhone;
- Fast Refresh for rapid UI feedback;
- the approved Dashboard and stock-analysis visual system;
- clear candlestick, forecast, RSI, MACD, Magic Nine, ownership, and participation components;
- adviser-style and long/short risk-plan interactions;
- citations, counter-evidence, stale/conflict states, and safety copy;
- no live data, LLM, moomoo, or trading integration yet;
- a documented 7-day free-signing renewal path.

The next independent project begins only after the user tests this demo and approves the page structure.
