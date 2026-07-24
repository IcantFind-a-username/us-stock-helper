import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { EvidenceSheet } from "../EvidenceSheet";

it("labels facts and rumors separately", async () => {
  const view = await render(
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
