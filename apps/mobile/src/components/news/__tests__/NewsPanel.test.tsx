import { afterEach, beforeEach, describe, expect, it, jest } from "@jest/globals";
import { act, fireEvent, render } from "@testing-library/react-native";
import { Linking, StyleSheet } from "react-native";

import { decodeNewsBriefingEnvelope } from "@/data/newsGateway";
import { useColorScheme } from "@/hooks/use-color-scheme";
import { colors } from "@/theme/tokens";

import { newsBriefingFixture } from "../../../data/__tests__/newsBriefing.fixture";
import { NewsPanel } from "../NewsPanel";

jest.mock("@/hooks/use-color-scheme", () => ({
  useColorScheme: jest.fn(() => "light"),
}));

const mockedColorScheme = useColorScheme as jest.MockedFunction<
  typeof useColorScheme
>;
const readerClock = new Date("2026-08-13T13:30:05.000Z");

async function renderPanel(
  mutate: (value: ReturnType<typeof newsBriefingFixture>) => void = () => {},
) {
  const payload = newsBriefingFixture();
  mutate(payload);
  const briefing = decodeNewsBriefingEnvelope(payload, { now: new Date() });
  return render(<NewsPanel briefing={briefing} />);
}

const openURL = jest
  .spyOn(Linking, "openURL")
  .mockImplementation(async () => undefined);

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(readerClock);
  mockedColorScheme.mockReturnValue("light");
  openURL.mockClear();
});

afterEach(() => {
  jest.useRealTimers();
});

describe("news feed timeliness", () => {
  it("puts the most recent verifiable story first", async () => {
    const view = await renderPanel();

    expect(
      view.getAllByTestId(/^news-story-row-/).map((row) => row.props.testID),
    ).toEqual([
      "news-story-row-story-guidance",
      "news-story-row-story-partial",
      "news-story-row-story-supply",
    ]);
  });

  it("shows both how long ago and exactly when each story arrived", async () => {
    const view = await renderPanel();

    expect(
      view.getByTestId("news-story-relative-story-guidance"),
    ).toHaveTextContent("3 分钟前");
    expect(
      view.getByTestId("news-story-absolute-story-guidance"),
    ).toHaveTextContent(/发布 2026-08-13 13:27:00 UTC/);
    expect(
      view.getByTestId("news-story-absolute-story-guidance"),
    ).toHaveTextContent(/接收 2026-08-13 13:27:30 UTC/);
  });

  it("keeps the relative time true as the clock moves", async () => {
    const view = await renderPanel();
    expect(
      view.getByTestId("news-story-relative-story-guidance"),
    ).toHaveTextContent("3 分钟前");

    await act(async () => {
      jest.advanceTimersByTime(60_000);
    });

    // A relative time frozen at render time quietly turns into a lie the
    // longer the screen stays open.
    expect(
      view.getByTestId("news-story-relative-story-guidance"),
    ).toHaveTextContent("4 分钟前");
    expect(
      view.getByTestId("news-story-relative-story-supply"),
    ).toHaveTextContent("21 分钟前");
  });

  it("states the snapshot cutoff it is reading from", async () => {
    const view = await renderPanel();

    expect(view.getByTestId("news-panel-asof")).toHaveTextContent(
      "快照截止 2026-08-13 13:30:00 UTC",
    );
  });
});

describe("news sourcing", () => {
  it("counts the independent publishers behind one story", async () => {
    const view = await renderPanel();

    expect(
      view.getByTestId("news-story-source-count-story-guidance"),
    ).toHaveTextContent("2 家来源");
    expect(view.getByText("路透社 · 可靠度 92%")).toBeTruthy();
    expect(view.getByText("彭博 · 可靠度 90%")).toBeTruthy();
  });

  it("names the single publisher instead of counting to one", async () => {
    const view = await renderPanel();

    expect(view.getByText("华尔街日报 · 可靠度 86%")).toBeTruthy();
    expect(
      view.queryByTestId("news-story-source-count-story-supply"),
    ).toBeNull();
    expect(view.queryByText("1 家来源")).toBeNull();
  });

  it("opens the original report rather than a copy of it", async () => {
    const view = await renderPanel();

    fireEvent.press(view.getByRole("link", { name: "打开来源：路透社" }));

    expect(openURL).toHaveBeenCalledWith(
      "https://reuters.example/nvda-guidance",
    );
  });

  it("never shows a story the reader cannot open, and says how many it hid", async () => {
    const view = await renderPanel();

    expect(view.queryByText("论坛传闻称新一代产能将翻倍")).toBeNull();
    expect(view.queryByTestId("news-story-row-story-unlinked")).toBeNull();
    expect(view.getByTestId("news-feed-hidden")).toHaveTextContent(
      /^1 条无原始链接的报道未展示 · /,
    );
  });

  it("says when a story's own sources were partly unverifiable", async () => {
    const view = await renderPanel();

    expect(
      view.getByTestId("news-story-omitted-story-partial"),
    ).toHaveTextContent("1 条无原始链接的来源未展示");
    expect(view.queryByText("匿名转载 · 可靠度 20%")).toBeNull();
  });
});

describe("interpretation and its evidence", () => {
  it("labels each conclusion with the evidence row it stands on", async () => {
    const view = await renderPanel();

    expect(view.getByTestId("news-claim-claim-guidance")).toHaveTextContent(
      /① 路透社/,
    );
    expect(
      view.getByTestId("news-story-marker-story-guidance"),
    ).toHaveTextContent("①");
    expect(view.getByTestId("news-story-cited-story-guidance")).toBeTruthy();
  });

  it("marks only the stories a conclusion actually used", async () => {
    const view = await renderPanel((value) => {
      value.interpretation.claims = [value.interpretation.claims[0]!];
    });

    expect(view.getByTestId("news-story-cited-story-guidance")).toBeTruthy();
    expect(view.queryByTestId("news-story-cited-story-supply")).toBeNull();
  });

  it("withholds a conclusion whose evidence cannot be opened", async () => {
    const view = await renderPanel();

    expect(
      view.queryByText("产能翻倍的说法仅见于无法核实的转述。"),
    ).toBeNull();
    expect(view.getByTestId("news-interpretation-withheld")).toHaveTextContent(
      "1 条结论因证据无法溯源未展示",
    );
  });

  it("names the model and the window its evidence is good for", async () => {
    const view = await renderPanel();

    expect(view.getByTestId("news-interpretation-meta")).toHaveTextContent(
      /模型 analysis-llm-v3/,
    );
    expect(view.getByTestId("news-interpretation-meta")).toHaveTextContent(
      /证据有效期至 2026-08-13 13:45:00 UTC/,
    );
  });
});

describe("the three ways this surface can be empty", () => {
  it("says the news feed is not connected without blanking the section", async () => {
    const view = await renderPanel((value) => {
      value.feed.status = "not-connected";
      value.feed.reason = "尚未配置新闻源凭据";
      value.feed.stories = [];
      value.interpretation.claims = [];
    });

    expect(view.getByTestId("news-feed-not-connected")).toHaveTextContent(
      /^新闻源尚未接入/,
    );
    expect(view.getByTestId("news-feed-not-connected")).toHaveTextContent(
      /尚未配置新闻源凭据/,
    );
    expect(view.queryAllByTestId(/^news-story-row-/)).toHaveLength(0);
    expect(view.queryByTestId("news-interpretation-unavailable")).toBeNull();
    expect(view.queryByTestId("news-interpretation-expired")).toBeNull();
  });

  it("says the interpretation service failed without touching the feed", async () => {
    const view = await renderPanel((value) => {
      value.interpretation.status = "unavailable";
      value.interpretation.reason = "解读模型未响应";
      value.interpretation.claims = [];
    });

    expect(
      view.getByTestId("news-interpretation-unavailable"),
    ).toHaveTextContent(/^解读暂不可用/);
    expect(
      view.getByTestId("news-interpretation-unavailable"),
    ).toHaveTextContent(/解读模型未响应/);
    expect(view.queryAllByTestId(/^news-story-row-/)).toHaveLength(3);
    expect(view.queryByTestId("news-feed-not-connected")).toBeNull();
    expect(view.queryByTestId("news-interpretation-expired")).toBeNull();
  });

  it("retires a conclusion once its evidence window closes", async () => {
    const view = await renderPanel();
    expect(view.getByTestId("news-claim-claim-guidance")).toBeTruthy();

    await act(async () => {
      jest.advanceTimersByTime(15 * 60_000);
    });

    expect(view.getByTestId("news-interpretation-expired")).toHaveTextContent(
      /^证据已过期/,
    );
    expect(view.queryByTestId("news-claim-claim-guidance")).toBeNull();
    expect(view.queryByTestId("news-interpretation-unavailable")).toBeNull();
    expect(view.queryByTestId("news-feed-not-connected")).toBeNull();
    // Nothing that describes the retired conclusions may outlive them: a model
    // line or a withheld count would read as an interpretation still standing.
    expect(view.queryByTestId("news-interpretation-meta")).toBeNull();
    expect(view.queryByTestId("news-interpretation-withheld")).toBeNull();
    // The reports themselves are still facts with timestamps; only the
    // conclusion drawn from them expired.
    expect(view.queryAllByTestId(/^news-story-row-/)).toHaveLength(3);
    expect(view.queryAllByTestId(/^news-story-cited-/)).toHaveLength(0);
  });

  it("separates a connected but quiet feed from a disconnected one", async () => {
    const view = await renderPanel((value) => {
      value.feed.stories = [];
      value.interpretation.claims = [];
    });

    expect(view.getByTestId("news-feed-empty")).toHaveTextContent(
      /^新闻源已接入 · 该时段没有可核实的报道/,
    );
    expect(view.getByTestId("news-interpretation-empty")).toHaveTextContent(
      /^暂无可溯源的结论/,
    );
    expect(view.queryByTestId("news-feed-not-connected")).toBeNull();
    expect(view.queryByTestId("news-interpretation-unavailable")).toBeNull();
  });
});

describe("theme", () => {
  it("uses the light surfaces on a light device", async () => {
    const view = await renderPanel();

    expect(
      StyleSheet.flatten(view.getByTestId("news-feed").props.style)
        .backgroundColor,
    ).toBe(colors.card);
    expect(
      StyleSheet.flatten(
        view.getByTestId("news-story-headline-story-guidance").props.style,
      ).color,
    ).toBe(colors.ink);
  });

  it("uses the dark surfaces on a dark device", async () => {
    mockedColorScheme.mockReturnValue("dark");

    const view = await renderPanel();

    expect(
      StyleSheet.flatten(view.getByTestId("news-feed").props.style)
        .backgroundColor,
    ).toBe(colors.navyRaised);
    expect(
      StyleSheet.flatten(
        view.getByTestId("news-story-headline-story-guidance").props.style,
      ).color,
    ).not.toBe(colors.ink);
    expect(
      StyleSheet.flatten(
        view.getByTestId("news-story-relative-story-guidance").props.style,
      ).color,
    ).toBe(colors.navyMuted);
  });
});
