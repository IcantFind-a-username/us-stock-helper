import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import type { ParticipationBar } from "@/domain/models";

import { ParticipationCard } from "../ParticipationCard";

function unavailableBar(reason: string | null): ParticipationBar {
  return {
    closedAt: "2026-08-13T16:05:00.000Z",
    asOf: "2026-08-13T16:05:00.000Z",
    availableAt: "2026-08-13T16:05:00.000Z",
    mainActivity: null,
    retailActivity: null,
    mainShare: null,
    retailShare: null,
    netFlow: null,
    coverage: 0,
    source: "moomoo",
    methodVersion: "order-size-activity-share-v1",
    qualityStatus: "unavailable",
    missingReason: reason,
  };
}

it("groups the missing bars by reason instead of printing one line each", async () => {
  // Every bar in a snapshot without capital flow carries the same sentence.
  // Printing it once per bar filled the screen with 199 copies and buried the
  // institutional disclosure below it.
  const bars = Array.from({ length: 199 }, () =>
    unavailableBar("capital flow unavailable"),
  );

  const view = await render(<ParticipationCard bars={bars} holdings={[]} />);

  const caption = view.getByTestId("participation-missing-summary");
  expect(caption).toHaveTextContent(/199 根缺失/);
  expect(caption).toHaveTextContent(/资金流/);
  // The reason belongs on screen once. Twice already means it is being
  // repeated per bar rather than counted.
  expect(String(caption.props.children).match(/资金流/g)?.length ?? 0).toBe(1);
});

it("keeps distinct reasons distinct and counts each", async () => {
  const bars = [
    unavailableBar("capital flow unavailable"),
    unavailableBar("capital flow unavailable"),
    unavailableBar("incomplete minute coverage"),
    unavailableBar(null),
  ];

  const view = await render(<ParticipationCard bars={bars} holdings={[]} />);

  const caption = view.getByTestId("participation-missing-summary");
  expect(caption).toHaveTextContent(/4 根缺失/);
  expect(caption).toHaveTextContent(/2 根/);
  expect(caption).toHaveTextContent(/未给出原因/);
});
