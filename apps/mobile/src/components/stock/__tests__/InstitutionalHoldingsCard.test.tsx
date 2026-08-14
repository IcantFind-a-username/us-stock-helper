import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";
import type { ReactTestRendererJSON } from "react-test-renderer";

import type {
  DelayedInstitutionalHolding,
  SnapshotSection,
} from "@/domain/models";

import { InstitutionalHoldingsCard } from "../InstitutionalHoldingsCard";

import {
  sofiInstitutionalHoldings,
  sofiInstitutionalHoldingsSection,
} from "./institutionalHoldings.fixture";

const aggregateWarning =
  "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释";

function sectionWith(
  data: DelayedInstitutionalHolding[],
): SnapshotSection<DelayedInstitutionalHolding[]> {
  return { ...sofiInstitutionalHoldingsSection, data };
}

function unavailableSection(
  overrides: Partial<SnapshotSection<DelayedInstitutionalHolding[]>> = {},
): SnapshotSection<DelayedInstitutionalHolding[]> {
  return {
    availabilityStatus: "unavailable",
    qualityStatus: "invalid",
    source: null,
    asOf: null,
    availableAt: null,
    receivedAt: null,
    data: null,
    errorCode: "HOLDINGS_UNAVAILABLE",
    reason: "机构持仓数据不可用",
    warnings: [],
    anomalies: [],
    methodVersion: "unavailable-v1",
    ...overrides,
  };
}

/**
 * The smallest fontSize anywhere in a rendered subtree.
 *
 * The reader's complaint was that the numbers were unreadable, and the way
 * this card got unreadable was one caption at a time. A floor is the only
 * assertion that survives the next person adding "just one more" 8-point line.
 */
function smallestFontSize(node: ReactTestRendererJSON | string | null): number {
  if (node === null || typeof node === "string") return Infinity;
  const flat = [node.props?.style].flat(Infinity) as ({ fontSize?: number } | null)[];
  const own = flat.reduce(
    (smallest, style) => Math.min(smallest, style?.fontSize ?? Infinity),
    Infinity,
  );
  return (node.children ?? []).reduce<number>(
    (smallest, child) =>
      Math.min(smallest, smallestFontSize(child as ReactTestRendererJSON)),
    own,
  );
}

it("leads with the latest quarter and its quarter-over-quarter move", async () => {
  const view = await render(
    <InstitutionalHoldingsCard section={sofiInstitutionalHoldingsSection} />,
  );

  expect(view.getByTestId("institutional-holdings-percent")).toHaveTextContent(
    "56.588%",
  );
  // The move is the information; the level alone says nothing about whether
  // institutions came or went this quarter.
  expect(
    view.getByTestId("institutional-holdings-percent-change"),
  ).toHaveTextContent(/较上季.*\+0\.24 个百分点/);
  expect(view.getByTestId("institutional-holdings-count")).toHaveTextContent(
    /1,062/,
  );
  expect(
    view.getByTestId("institutional-holdings-count-change"),
  ).toHaveTextContent(/\+6/);
  // 730,882,098 shares is unreadable as a raw integer on a phone.
  expect(view.getByTestId("institutional-holdings-shares")).toHaveTextContent(
    "7.31 亿",
  );
  expect(
    view.getByTestId("institutional-holdings-shares-change"),
  ).toHaveTextContent(/\+880\.8 万/);
});

it("states how stale the disclosure is, in days, before anything else", async () => {
  const view = await render(
    <InstitutionalHoldingsCard section={sofiInstitutionalHoldingsSection} />,
  );

  // Period end 2026-06-30T20:00:00Z, snapshot 2026-08-13T17:54:28Z.
  expect(view.getByTestId("institutional-holdings-lag")).toHaveTextContent(
    /季度披露.*滞后 44 天/,
  );
  // The period-end basis means the real filing is later still, and the reader
  // has to be told that rather than left to assume this is a live position.
  expect(view.getByTestId("institutional-holdings-basis")).toHaveTextContent(
    /报告期末/,
  );
  expect(view.getByTestId("institutional-holdings-basis")).toHaveTextContent(
    /不是当前持仓/,
  );
});

it("renders the wire's own timestamp spelling as a date, not as raw ISO", async () => {
  const view = await render(
    <InstitutionalHoldingsCard section={sofiInstitutionalHoldingsSection} />,
  );

  const period = view.getByTestId("institutional-holdings-period");
  expect(period).toHaveTextContent(/2026\/Q2/);
  expect(period).toHaveTextContent(/2026-06-30/);
  // The gateway sends `2026-06-30T20:00:00Z` with no milliseconds. A formatter
  // written against a `.000Z` fixture leaves the T and the Z on screen.
  expect(period).not.toHaveTextContent(/T\d\d:\d\d/);
  expect(period).not.toHaveTextContent(/\dZ/);
});

it("says how many quarters it is holding back instead of dropping them", async () => {
  const view = await render(
    <InstitutionalHoldingsCard section={sofiInstitutionalHoldingsSection} />,
  );

  const rows = view.getAllByTestId("institutional-holdings-history-row");
  expect(rows.length).toBeLessThan(sofiInstitutionalHoldings.length);
  expect(view.getByTestId("institutional-holdings-coverage")).toHaveTextContent(
    `共 ${sofiInstitutionalHoldings.length} 期 · 已显示最近 ${rows.length} 期`,
  );
});

it("marks a quarter where institutions sold as a decrease", async () => {
  // 2022/Q4 is the real series' sharpest retreat: -5.389 percentage points.
  const retreat = sofiInstitutionalHoldings.slice(
    sofiInstitutionalHoldings.findIndex((item) => item.period === "2022/Q4"),
  );

  const view = await render(<InstitutionalHoldingsCard section={sectionWith(retreat)} />);

  expect(
    view.getByTestId("institutional-holdings-percent-change"),
  ).toHaveTextContent(/减|▼/);
  expect(
    view.getByTestId("institutional-holdings-percent-change"),
  ).toHaveTextContent(/-5\.39 个百分点/);
});

it("calls an unchanged quarter unchanged rather than dressing it as a gain", async () => {
  const flat = [
    {
      ...sofiInstitutionalHoldings[0]!,
      holdingPercentChange: 0,
      institutionCountChange: 0,
      sharesHeldChange: 0,
    },
  ];

  const view = await render(<InstitutionalHoldingsCard section={sectionWith(flat)} />);

  expect(
    view.getByTestId("institutional-holdings-percent-change"),
  ).toHaveTextContent(/持平/);
});

it("shows an absent disclosure as absent, with no number to misread as zero", async () => {
  const view = await render(<InstitutionalHoldingsCard section={unavailableSection()} />);

  const empty = view.getByTestId("institutional-holdings-empty");
  expect(view.getByText("机构持仓数据不可用")).toBeTruthy();
  // "No filing in this snapshot" and "institutions hold none of it" are
  // opposite claims. A digit anywhere in the empty state invites the second
  // reading, so there is none.
  expect(view.queryByTestId("institutional-holdings-percent")).toBeNull();
  expect(view.toJSON()).not.toHaveTextContent(/\d/);
});

it("refuses to invent a lag when the timestamps cannot be read", async () => {
  const unparsable = [
    { ...sofiInstitutionalHoldings[0]!, reportedAt: "unknown" },
  ];

  const view = await render(
    <InstitutionalHoldingsCard section={sectionWith(unparsable)} />,
  );

  const lag = view.getByTestId("institutional-holdings-lag");
  expect(lag).toHaveTextContent(/滞后未知/);
  // 0 days would read as "filed today", the one thing this card must never say.
  expect(lag).not.toHaveTextContent(/0 天/);
});

it("prints nothing smaller than the 13pt floor in either section branch", async () => {
  const available = await render(
    <InstitutionalHoldingsCard section={sofiInstitutionalHoldingsSection} />,
  );
  const unavailable = await render(
    <InstitutionalHoldingsCard section={unavailableSection()} />,
  );

  expect(
    smallestFontSize(available.toJSON() as ReactTestRendererJSON),
  ).toBeGreaterThanOrEqual(13);
  expect(
    smallestFontSize(unavailable.toJSON() as ReactTestRendererJSON),
  ).toBeGreaterThanOrEqual(13);
});

it("makes the headline number dominate the labels around it", async () => {
  const view = await render(
    <InstitutionalHoldingsCard section={sofiInstitutionalHoldingsSection} />,
  );

  const percent = view.getByTestId("institutional-holdings-percent");
  const percentSize = [percent.props.style].flat(Infinity).reduce(
    (found: number, style) =>
      (style as { fontSize?: number } | null)?.fontSize ?? found,
    0,
  );
  expect(percentSize).toBeGreaterThanOrEqual(28);
});

it("keeps an anomalous provider aggregate exact and explains its delayed basis", async () => {
  const anomalous = sectionWith([
    {
      ...sofiInstitutionalHoldings[0]!,
      period: "2026/Q1",
      reportedAt: "2026-03-31T00:00:00.000Z",
      availableAt: "2026-05-15T00:00:00.000Z",
      asOf: "2026-03-31T00:00:00.000Z",
      holdingPercent: 345.937,
      methodVersion: "reported-holdings-v2-anomaly-aware",
    },
  ]);
  Object.assign(anomalous, {
    qualityStatus: "anomalous",
    asOf: "2026-03-31T00:00:00.000Z",
    availableAt: "2026-05-15T00:00:00.000Z",
    warnings: [aggregateWarning],
    anomalies: [
      {
        code: "AGGREGATE_PERCENT_ABOVE_100",
        reason: aggregateWarning,
        rowIndex: 0,
      },
    ],
  });

  const view = await render(<InstitutionalHoldingsCard section={anomalous} />);

  expect(view.getByTestId("institutional-holdings-percent")).toHaveTextContent(
    "345.937%",
  );
  expect(view.queryByText("345.94%")).toBeNull();
  expect(view.getByText("持仓质量异常")).toBeTruthy();
  expect(view.getByText(aggregateWarning)).toBeTruthy();
  expect(view.getByTestId("institutional-holdings-source")).toHaveTextContent(
    "来源 moomoo · 延迟机构披露",
  );
  expect(view.getByTestId("institutional-holdings-period")).toHaveTextContent(
    /2026\/Q1.*2026-03-31/,
  );
  expect(view.getByTestId("institutional-holdings-lag")).toHaveTextContent(
    /滞后 45 天/,
  );
  expect(view.toJSON()).not.toHaveTextContent(
    /贝莱德|BlackRock|今日买入|今日卖出|大单代理|实名机构/,
  );
});

it("maps known section codes locally and never renders server prose", async () => {
  const poisoned = unavailableSection({
    errorCode: "FUTURE_HOLDINGS_ROW",
    reason: "Python RuntimeError provider=secret token=secret",
    warnings: ["upstream exception token=secret"],
    anomalies: [
      {
        code: "FUTURE_HOLDINGS_ROW",
        reason: "provider traceback token=secret",
      },
    ],
  });
  const view = await render(<InstitutionalHoldingsCard section={poisoned} />);

  expect(view.getByText("机构持仓记录晚于决策截止时间")).toBeTruthy();
  expect(view.toJSON()).not.toHaveTextContent(
    /FUTURE_HOLDINGS_ROW|RuntimeError|provider|traceback|token=secret|exception/,
  );
});

it("uses a fixed fallback for unknown reason, warning, anomaly, and code", async () => {
  const unknown = unavailableSection({
    errorCode: "PYTHON_TRACE",
    reason: "ValueError provider payload token=secret",
    warnings: ["provider warning token=secret"],
    anomalies: [
      {
        code: "UNKNOWN_PROVIDER_ANOMALY",
        reason: "异常 token=secret",
      },
    ],
  });
  const view = await render(<InstitutionalHoldingsCard section={unknown} />);

  expect(view.getByText("机构持仓数据不可用")).toBeTruthy();
  expect(view.queryByTestId("institutional-holdings-percent")).toBeNull();
  expect(view.toJSON()).not.toHaveTextContent(
    /PYTHON_TRACE|UNKNOWN_PROVIDER_ANOMALY|ValueError|provider|异常|token=secret/,
  );
  expect(view.toJSON()).not.toHaveTextContent(/0%/);
});
