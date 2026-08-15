# SDD ledger — plan: docs/superpowers/plans/2026-08-15-quant-foundations-plain-language.md

All 12 tasks complete (2026-08-16). Model tiering per the sdd skill throughout.

Task 1: ded4db5 breadth-v1 (hand-computed fixtures, PIT)
Task 2: 7ddc5a4 sector-rs-v1 (EMA-anchored RS, correlation regime)
Task 3: ef834f9 rvol-tod-v1 (session-bucket injection, never padded 1.0×)
Task 4: 0566440 range-vol-v1 (Parkinson/GK, closed forms verified to 9 decimals)
Task 5: 1d77951/4afe9ee/07d3bae/9f60377 (watchlist-fallback universe, 自选广度 labels, trading-date cache)
Task 6+7: b57092c/a8990c0/844031e/0a1e05a/8d2257a (construction-time banned-verb guard, PlainReadingCard, brief drivers + Magic Nine reading)
Task 8: e17c686..f2f1dd9 (patterns-shapes-v1 full stack) + UX fold 69f683c
Task 9: e953086 (independent-reference series pins) + 2c54997 (real bug: decoder expected a shape the gateway never sent; fixtures self-consistently wrong)
Task 10: 7245680/9e45bbd (proxy 0.5-confidence + PIT disclosure blend)
Task 11: cdf221f/5b70151/a782f21/d1fd50f (Chinese sweep + completeness gate + doc-command pin)
Task 12: 283fb25 (methodology, literature citations)

Re-review (fable high-risk / sonnet standard): 2 CRITICAL + 1 critical-doc + 3 important + minors, all demonstrated by runnable probes:
- F1 patterns PIT/replay guarantee false (global cursor erased resolved episodes) → d7be758: per-candidate resolution, episodic MA5, ReplayInvariantPropertyTests (∀k: resolved signals of any prefix are immutable in the full recompute)
- F2 形态 factor silent semantics change (historical confirmed signals voted forever; probe −0.30→+0.90) → 8ed7811: in-force-only votes, latest-wins ties, method explainable-horizon-score-v2 + disclosed copy
- F4 analysis_api README lied post-institutional-wiring → 835cd1d + AllowlistDriftTests (README route claim mechanically pinned to _READ_PATHS)
- F6/F7/F8 brief cache → d921058 (failure retry-TTL 180s), c7121f8 (single-flight without holding the lock; followers get 计算中), 375ab52 (有效 X/Y 只 sample honesty)
- F9 MACD fixture-vs-wire trap → facf699 cross-language contract fixtures (Python byte-pinned generation, mobile decodes the same JSON; teeth proven by reverting the original bug)
- F3/F5 + banned-verb-guard gap → 2d4a0d8, 6e9be0e, 3a32c92; RVOL doc self-contradiction → 32188a0

Final verification: all 9 Python/deploy suites OK (analysis_core 273, market_gateway 186, analysis_api 273); mobile 982 passed / 1 skipped; typecheck clean. Services restarted on the fixed code.

Simulator acceptance evidenced during the wave: MACD/RSI curves drawn; factor details in Chinese; 自选广度（46 只）live on the dashboard; pattern markers and folded hint cards on real symbols; Magic Nine reading beside the badge.

Deferred/open: RVOL & range-vol per-symbol serving (vocabulary ready, wiring is a follow-up); sector RS awaits operator env config (ANALYSIS_API_SECTOR_RS_SYMBOLS/_BENCHMARK); phase 2 (conformal calibration, walk-forward backtest, event study) is a separate plan.
