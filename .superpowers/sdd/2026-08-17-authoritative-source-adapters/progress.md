# SDD ledger — plan: docs/superpowers/plans/2026-08-17-authoritative-source-adapters.md

Status: **not started.** Baseline at handoff = commit `cc34784` on `feature/iphone-demo`.
Baseline suites: all Python packages OK; mobile 982 passed / 1 skipped; typecheck clean.

## How to use this file

Append one block per task as you finish it. A task is not done until every line below has a real answer —
"跑过测试了" is not an acceptable substitute for the simulator line.

```
Task N: <name> — complete | in progress | blocked
- RED: <test name(s)> failed with <actual failure output, quoted>
- GREEN: <suite counts after the fix>
- Mutation check: <what you inverted, which test caught it>   (for correctness-critical changes)
- Suites: <package: count> for every affected package + mobile + typecheck
- Simulator: <which screen, what you actually saw — data, state, copy>
- Commit: <hash> <message>
- Notes / deferred: <anything the next agent must know>
```

## Task blocks

Task 1: Extend SEC current-filings coverage — not started
- Pre-work owed: confirm real EDGAR form codes for 10-Q / 10-K / SC 13D / SC 13G against live samples
  (the plan assumes `SC 13D`/`SC 13G`; the captured fixture is the authority, not the assumption).

Task 2: Generalize company IR sources — not started
- Owed per feed registered: a line recording that robots.txt and terms were actually read.

Task 3: Regulatory and agency sources — not started
- Owed per source investigated and REJECTED: the reason (no public feed / robots forbids / unstable schema).
  A documented rejection is a result; an undocumented gap is a trap.

Task 4: Coordinator snapshot persistence — not started
- The mechanism (`snapshot`/`from_snapshot`) already exists and is unit-tested; only production wiring is missing.
- Restart proof owed: kickstart the analysis-api label twice, show the second start publishes nothing new.

Task 5: Re-examine the evidence gate — not started
- Do NOT touch the 0.35 literal before Tasks 1–4 land. Measurement first, then a named constant,
  and a `method_version` bump if the value changes.

Task 6: Filing document text (optional) — undecided
- Needs Franz's decision before any code: it is a new capability with real EDGAR request-volume risk.

Task 7: Methodology / README / roadmap close-out — not started

## Open questions for Franz (do not decide these alone)

1. 顾问 taxonomy：具名投资人 vs 去品牌化框架（阶段 7 遗留）。
2. 广度/RS 股票池是否扩大到自选之外；板块 RS 需要配置 `ANALYSIS_API_SECTOR_RS_SYMBOLS` / `_BENCHMARK`。
3. Task 6（申报正文抓取）是否值得做。
4. 新闻 wire 商业授权是否采购。
