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

const NOT_REQUESTED_REASON =
  "This request did not ask for the adviser layer; add adviser=1 to call the model.";

function notRequested(): Decision["newsInterpretation"] {
  return { status: "not-requested", reason: NOT_REQUESTED_REASON, value: null };
}

function interpretation(): NonNullable<Decision["newsInterpretation"]> {
  return {
    status: "available",
    reason: null,
    value: {
      headlineSummary: "两家通讯社都报道了指引上调。",
      crossSourceReading: "两条报道指向同一件事，来源相互独立。",
      investmentImpact: [
        {
          statement: "指引上调支持偏多的解读。",
          confidence: "medium",
          citations: [
            {
              evidenceId: "only",
              quote: "raises full-year revenue guidance",
              url: "https://example.com/only",
              publisher: "发布方 only",
              availableAt: "2026-08-13T13:27:00.000Z",
              isCounterEvidence: false,
            },
          ],
          counterEvidence: [],
        },
      ],
      unknowns: ["证据没有说明毛利率如何变化。"],
    },
  };
}

function decision(overrides: Partial<Decision> = {}): Decision {
  return {
    status: "live",
    symbol: "NVDA",
    horizon: "short",
    interval: "day",
    decisionCutoff: "2026-08-13T13:30:00.000Z",
    score: null,
    baselineScore: null,
    adviserAdjustment: null,
    forecast: null,
    riskPlan: null,
    citations: [],
    newsInterpretation: notRequested(),
    adviserCouncil: notRequested() as Decision["adviserCouncil"],
    adviserUsage: null,
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

    const notice = view.getByTestId("decision-news-unavailable");
    expect(notice).toHaveTextContent(/新闻证据不可用 · 连不上/);
    // Naming the failure is half of it; the reader also has to be told this is
    // not a quiet news day, and what would make it work.
    expect(notice).toHaveTextContent(/不是「今天没有消息」/);
    expect(notice).toHaveTextContent(/OpenD/);
    expect(notice).not.toHaveTextContent(/offline/);
    expect(view.queryByTestId("decision-news-empty")).toBeNull();
  });

  it("says it is still reading while the request is in flight", async () => {
    const view = await renderSection({ decision: null, errorCategory: null });

    expect(view.getByTestId("decision-news-loading")).toBeTruthy();
    expect(view.queryByTestId("decision-news-unavailable")).toBeNull();
  });

});

/**
 * "解读暂不可用" was one message covering three different situations. Nobody
 * asked for the interpretation, the model was asked and failed, and the server
 * has no such feature are three different things to do next — pay for it, wait
 * and retry, upgrade the deployment — and one sentence told the reader none of
 * them.
 */
describe("why the interpretation is not on the screen", () => {
  const cited = [citation("only", "2026-08-13T13:27:00.000Z")];

  it("says nobody asked for it, rather than that it failed", async () => {
    const view = await renderSection({
      decision: decision({ citations: cited }),
    });

    const notice = view.getByTestId("decision-interpretation-not-requested");
    expect(notice).toHaveTextContent(/未请求/);
    expect(view.queryByTestId("decision-interpretation-unavailable")).toBeNull();
  });

  it("says the model failed, rather than that it had no view", async () => {
    const view = await renderSection({
      decision: decision({
        citations: cited,
        newsInterpretation: {
          status: "unavailable",
          reason: "模型请求超时（已尝试 3 次）。",
          value: null,
        },
      }),
    });

    const notice = view.getByTestId("decision-interpretation-unavailable");
    expect(notice).toHaveTextContent(/解读不可用/);
    expect(notice).toHaveTextContent(/模型请求超时/);
    // The distinction the whole file exists for: a model that broke is not a
    // model that looked and found nothing worth saying.
    expect(notice).toHaveTextContent(/不是「没有观点」/);
    expect(view.queryByTestId("decision-interpretation-not-requested")).toBeNull();
  });

  it("translates the interpretation's own reason instead of showing it raw", async () => {
    // Defense in depth (2026-08-15 served-copy sweep): `block.reason` used to
    // render straight through with no translation pass -- how English
    // adviser-degradation reasons reached this card before those server
    // strings were translated at the source.
    const view = await renderSection({
      decision: decision({
        citations: cited,
        newsInterpretation: {
          status: "unavailable",
          reason: "Realized volatility could not be measured, so no scenario range is offered.",
          value: null,
        },
      }),
    });

    const notice = view.getByTestId("decision-interpretation-unavailable");
    expect(notice).toHaveTextContent(/无法测得已实现波动率/);
    expect(notice).not.toHaveTextContent(/Realized volatility/);
  });

  it("says the deployment has no such feature when the field is absent", async () => {
    const view = await renderSection({
      decision: decision({ citations: cited, newsInterpretation: null }),
    });

    expect(
      view.getByTestId("decision-interpretation-not-deployed"),
    ).toHaveTextContent(/解读接口/);
  });

  it("never invents an interpretation while the analysis is still in flight", async () => {
    const view = await renderSection({ decision: null, errorCategory: null });

    expect(view.getByTestId("decision-interpretation-pending")).toBeTruthy();
    expect(view.queryByTestId("decision-interpretation-not-requested")).toBeNull();
  });
});

describe("an interpretation the model actually produced", () => {
  const cited = [citation("only", "2026-08-13T13:27:00.000Z")];

  it("shows the cross-source reading and every sourced conclusion", async () => {
    const view = await renderSection({
      decision: decision({
        citations: cited,
        newsInterpretation: interpretation(),
      }),
    });

    expect(view.getByTestId("decision-interpretation-reading")).toHaveTextContent(
      /相互独立/,
    );
    expect(view.getByTestId("decision-interpretation-claim-0")).toHaveTextContent(
      /指引上调支持偏多的解读/,
    );
  });

  it("carries the citation and its quote with the conclusion", async () => {
    const view = await renderSection({
      decision: decision({
        citations: cited,
        newsInterpretation: interpretation(),
      }),
    });

    const source = view.getByTestId("decision-interpretation-citation-0-only");
    expect(source).toHaveTextContent(/发布方 only/);
    expect(source).toHaveTextContent(/raises full-year revenue guidance/);
  });

  it("prints what the evidence could not answer instead of dropping it", async () => {
    const view = await renderSection({
      decision: decision({
        citations: cited,
        newsInterpretation: interpretation(),
      }),
    });

    expect(view.getByTestId("decision-interpretation-unknowns")).toHaveTextContent(
      /毛利率/,
    );
  });

  it("states what the model call cost, since it is the reader's money", async () => {
    const view = await renderSection({
      decision: decision({
        citations: cited,
        newsInterpretation: interpretation(),
        adviserUsage: {
          model: "claude-opus-4-8",
          inputTokens: 13000,
          outputTokens: 3900,
          cacheCreationInputTokens: 0,
          cacheReadInputTokens: 2000,
          costUsd: 0.0993,
        },
      }),
    });

    expect(view.getByTestId("decision-interpretation-cost")).toHaveTextContent(
      /0\.0993/,
    );
  });

  it("does not print a cost when nothing measured one", async () => {
    const view = await renderSection({
      decision: decision({
        citations: cited,
        newsInterpretation: interpretation(),
        adviserUsage: null,
      }),
    });

    // A zero here would claim the call was measured and was free.
    expect(view.queryByTestId("decision-interpretation-cost")).toBeNull();
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
