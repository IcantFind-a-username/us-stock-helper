import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";
import type { ReactTestRendererJSON } from "react-test-renderer";

import { InstitutionalHoldingsCard } from "../InstitutionalHoldingsCard";

import { sofiInstitutionalHoldings } from "./institutionalHoldings.fixture";

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
    <InstitutionalHoldingsCard holdings={sofiInstitutionalHoldings} />,
  );

  expect(view.getByTestId("institutional-holdings-percent")).toHaveTextContent(
    "56.59%",
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
    <InstitutionalHoldingsCard holdings={sofiInstitutionalHoldings} />,
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
    <InstitutionalHoldingsCard holdings={sofiInstitutionalHoldings} />,
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
    <InstitutionalHoldingsCard holdings={sofiInstitutionalHoldings} />,
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

  const view = await render(<InstitutionalHoldingsCard holdings={retreat} />);

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

  const view = await render(<InstitutionalHoldingsCard holdings={flat} />);

  expect(
    view.getByTestId("institutional-holdings-percent-change"),
  ).toHaveTextContent(/持平/);
});

it("shows an absent disclosure as absent, with no number to misread as zero", async () => {
  const view = await render(<InstitutionalHoldingsCard holdings={[]} />);

  const empty = view.getByTestId("institutional-holdings-empty");
  expect(empty).toHaveTextContent(/未提供/);
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

  const view = await render(<InstitutionalHoldingsCard holdings={unparsable} />);

  const lag = view.getByTestId("institutional-holdings-lag");
  expect(lag).toHaveTextContent(/滞后未知/);
  // 0 days would read as "filed today", the one thing this card must never say.
  expect(lag).not.toHaveTextContent(/0 天/);
});

it("prints nothing smaller than the phone's readable floor", async () => {
  const view = await render(
    <InstitutionalHoldingsCard holdings={sofiInstitutionalHoldings} />,
  );

  expect(smallestFontSize(view.toJSON() as ReactTestRendererJSON)).toBeGreaterThanOrEqual(12);
});

it("makes the headline number dominate the labels around it", async () => {
  const view = await render(
    <InstitutionalHoldingsCard holdings={sofiInstitutionalHoldings} />,
  );

  const percent = view.getByTestId("institutional-holdings-percent");
  const percentSize = [percent.props.style].flat(Infinity).reduce(
    (found: number, style) =>
      (style as { fontSize?: number } | null)?.fontSize ?? found,
    0,
  );
  expect(percentSize).toBeGreaterThanOrEqual(28);
});
