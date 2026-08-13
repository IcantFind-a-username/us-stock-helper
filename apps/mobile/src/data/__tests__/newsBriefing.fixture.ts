const asOf = "2026-08-13T13:30:00.000Z";

type FixtureReport = {
  publisherId: string;
  publisher: string;
  url: string | null;
  reliability: number;
  availableAt: string;
  receivedAt: string;
};

type FixtureStory = {
  id: string;
  headline: string;
  claimStatus: string;
  reports: FixtureReport[];
};

type FixtureClaim = {
  id: string;
  text: string;
  evidenceIds: string[];
};

export function newsBriefingFixture() {
  return {
    schemaVersion: "1",
    symbol: "NVDA",
    asOf,
    feed: {
      status: "connected" as "connected" | "not-connected",
      reason: null as string | null,
      stories: [
        {
          id: "story-guidance",
          headline: "英伟达上调全年营收指引",
          claimStatus: "verified",
          reports: [
            {
              publisherId: "reuters",
              publisher: "路透社",
              url: "https://reuters.example/nvda-guidance",
              reliability: 0.92,
              availableAt: "2026-08-13T13:27:00.000Z",
              receivedAt: "2026-08-13T13:27:30.000Z",
            },
            {
              publisherId: "bloomberg",
              publisher: "彭博",
              url: "https://bloomberg.example/nvda-guidance",
              reliability: 0.9,
              availableAt: "2026-08-13T13:28:00.000Z",
              receivedAt: "2026-08-13T13:28:20.000Z",
            },
          ],
        },
        {
          id: "story-supply",
          headline: "供应链厂商确认第三季度产能排期",
          claimStatus: "reported",
          reports: [
            {
              publisherId: "wsj",
              publisher: "华尔街日报",
              url: "https://wsj.example/nvda-supply",
              reliability: 0.86,
              availableAt: "2026-08-13T13:10:00.000Z",
              receivedAt: "2026-08-13T13:10:40.000Z",
            },
          ],
        },
        {
          id: "story-partial",
          headline: "机构调研纪要提到数据中心订单节奏",
          claimStatus: "reported",
          reports: [
            {
              publisherId: "caixin",
              publisher: "财新",
              url: "https://caixin.example/nvda-datacenter",
              reliability: 0.81,
              availableAt: "2026-08-13T13:20:00.000Z",
              receivedAt: "2026-08-13T13:20:10.000Z",
            },
            {
              publisherId: "anonymous-repost",
              publisher: "匿名转载",
              url: null,
              reliability: 0.2,
              availableAt: "2026-08-13T13:19:00.000Z",
              receivedAt: "2026-08-13T13:19:05.000Z",
            },
          ],
        },
        {
          id: "story-unlinked",
          headline: "论坛传闻称新一代产能将翻倍",
          claimStatus: "rumor",
          reports: [
            {
              publisherId: "forum",
              publisher: "匿名论坛",
              url: null,
              reliability: 0.1,
              availableAt: "2026-08-13T13:29:00.000Z",
              receivedAt: "2026-08-13T13:29:10.000Z",
            },
          ],
        },
      ] as FixtureStory[],
    },
    interpretation: {
      status: "available" as "available" | "unavailable",
      reason: null as string | null,
      model: "analysis-llm-v3",
      generatedAt: "2026-08-13T13:29:00.000Z",
      evidenceValidUntil: "2026-08-13T13:45:00.000Z",
      claims: [
        {
          id: "claim-guidance",
          text: "上调指引已有两家独立来源报道，指引口径一致。",
          evidenceIds: ["story-guidance"],
        },
        {
          id: "claim-capacity",
          text: "产能与订单节奏只有单一来源，暂不足以形成结论。",
          evidenceIds: ["story-partial", "story-supply"],
        },
        {
          id: "claim-rumor",
          text: "产能翻倍的说法仅见于无法核实的转述。",
          evidenceIds: ["story-unlinked"],
        },
      ] as FixtureClaim[],
    },
  };
}
