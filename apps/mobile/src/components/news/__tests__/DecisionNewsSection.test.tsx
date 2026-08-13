import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";
import { Linking, StyleSheet } from "react-native";

import { useColorScheme } from "@/hooks/use-color-scheme";
import { colors } from "@/theme/tokens";

import type { Decision, DecisionCitation } from "@/domain/models";

import { DecisionNewsSection } from "../DecisionNewsSection";

jest.mock("@/hooks/use-color-scheme", () => ({
  useColorScheme: jest.fn(() => "light"),
}));

const mockedColorScheme = useColorScheme as jest.MockedFunction<
  typeof useColorScheme
>;

beforeEach(() => {
  mockedColorScheme.mockReturnValue("light");
});

function citation(
  id: string,
  availableAt: string,
  overrides: Partial<DecisionCitation> = {},
): DecisionCitation {
  return {
    id,
    headline: `标题 ${id}`,
    publisher: `发布方 ${id}`,
    url: `https://example.com/${id}`,
    availableAt,
    ...overrides,
  };
}

function decision(overrides: Partial<Decision> = {}): Decision {
  return {
    status: "live",
    symbol: "NVDA",
    horizon: "short",
    decisionCutoff: "2026-08-13T13:30:00.000Z",
    score: null,
    forecast: null,
    riskPlan: null,
    citations: [],
    notes: [],
    ...overrides,
  };
}

async function renderSection(
  props: Partial<Parameters<typeof DecisionNewsSection>[0]> = {},
) {
  return render(
    <DecisionNewsSection
      decision={decision()}
      errorCategory={null}
      symbol="NVDA"
      {...props}
    />,
  );
}

describe("the news evidence carried by a real decision", () => {
  it("lists the cited reports newest first and numbers them in that order", async () => {
    const view = await renderSection({
      decision: decision({
        citations: [
          citation("old", "2026-08-13T12:00:00.000Z"),
          citation("new", "2026-08-13T13:27:00.000Z"),
          citation("mid", "2026-08-13T13:10:00.000Z"),
        ],
      }),
    });

    expect(view.getByTestId("decision-news-marker-new")).toHaveTextContent("①");
    expect(view.getByTestId("decision-news-marker-mid")).toHaveTextContent("②");
    expect(view.getByTestId("decision-news-marker-old")).toHaveTextContent("③");
  });

  it("opens the original report at the publisher's own link", async () => {
    const openURL = jest
      .spyOn(Linking, "openURL")
      .mockImplementation(async () => true);
    const view = await renderSection({
      decision: decision({
        citations: [citation("only", "2026-08-13T13:27:00.000Z")],
      }),
    });

    await fireEvent.press(
      view.getByRole("link", { name: "打开来源：发布方 only" }),
    );

    expect(openURL).toHaveBeenCalledWith("https://example.com/only");
    openURL.mockRestore();
  });

  it("states which news facts the decision service does not supply", async () => {
    // The full news surface shows a claim status and a source reliability.
    // /decision carries neither, so the section has to say so rather than let
    // the reader assume this list was merely thin on sources.
    const view = await renderSection({
      decision: decision({
        citations: [citation("only", "2026-08-13T13:27:00.000Z")],
      }),
    });

    expect(view.getByTestId("decision-news-limits")).toHaveTextContent(
      /未提供来源可靠度与消息证实状态/,
    );
  });

  it("never prints a claim status or a reliability it was not given", async () => {
    const view = await renderSection({
      decision: decision({
        citations: [citation("only", "2026-08-13T13:27:00.000Z")],
      }),
    });

    // The disclaimer names these fields to say they are missing, so the check
    // is for a rendered *value* — a status chip or a reliability percentage.
    expect(view.queryByText(/^(已证实|有报道|传闻)$/)).toBeNull();
    expect(view.queryByText(/可靠度\s*\d/)).toBeNull();
  });

  it("separates a live decision with no reports from a decision that failed", async () => {
    const empty = await renderSection({ decision: decision({ citations: [] }) });
    expect(empty.getByTestId("decision-news-empty")).toBeTruthy();
    expect(empty.queryByTestId("decision-news-unavailable")).toBeNull();

    const failed = await renderSection({
      decision: decision({
        status: "unavailable",
        citations: [],
        notes: ["证据源无法读取"],
      }),
    });
    expect(failed.getByTestId("decision-news-not-connected")).toHaveTextContent(
      /证据源无法读取/,
    );
    expect(failed.queryByTestId("decision-news-empty")).toBeNull();
  });

  it("reports the transport failure rather than an empty market", async () => {
    const view = await renderSection({ decision: null, errorCategory: "offline" });

    expect(view.getByTestId("decision-news-unavailable")).toHaveTextContent(
      /offline/,
    );
    expect(view.queryByTestId("decision-news-empty")).toBeNull();
  });

  it("says it is still reading while the request is in flight", async () => {
    const view = await renderSection({ decision: null, errorCategory: null });

    expect(view.getByTestId("decision-news-loading")).toBeTruthy();
    expect(view.queryByTestId("decision-news-unavailable")).toBeNull();
  });

  it("keeps the model interpretation absent with a reason, never invented", async () => {
    const view = await renderSection({
      decision: decision({
        citations: [citation("only", "2026-08-13T13:27:00.000Z")],
      }),
    });

    expect(view.getByTestId("news-interpretation-unavailable")).toBeTruthy();
    expect(view.getByTestId("news-interpretation-unavailable")).toHaveTextContent(
      /解读接口/,
    );
  });
});

describe("the section's surfaces follow the device theme", () => {
  it("uses the light card on a light device", async () => {
    const view = await renderSection({
      decision: decision({
        citations: [citation("only", "2026-08-13T13:27:00.000Z")],
      }),
    });

    expect(
      StyleSheet.flatten(view.getByTestId("decision-news-feed").props.style)
        .backgroundColor,
    ).toBe(colors.card);
  });

  it("uses the navy card on a dark device", async () => {
    mockedColorScheme.mockReturnValue("dark");

    const view = await renderSection({
      decision: decision({
        citations: [citation("only", "2026-08-13T13:27:00.000Z")],
      }),
    });

    expect(
      StyleSheet.flatten(view.getByTestId("decision-news-feed").props.style)
        .backgroundColor,
    ).toBe(colors.navyRaised);
    expect(
      StyleSheet.flatten(
        view.getByTestId("decision-news-row-only").props.style,
      ).backgroundColor,
    ).toBe(colors.navy);
  });
});
