# SDD ledger — plan: docs/superpowers/plans/2026-08-15-demo-parity-market-brief-and-council.md

Model tiering per the sdd skill's risk rules throughout (haiku for complete-spec transcription, sonnet for integration, fable for high-risk review).

Task 1: complete — 66edf90 (v3 session flow rendered) + HIGH re-review fix 6422e6d (per-candle deltas per §7.3, day/week guard, alignment honesty; old code read session-cumulative splits — opposite lean on late candles)
Task 2: complete — ff2f94d (real-mode search copy de-demoed; haiku)
Task 3: complete — 799d6c4 (GET /market-brief; 25 tests incl. burst→one-sweep throttle proof) + re-review minors 601b131 (unmeasured entry honesty), c1a59f5 (excluded-future disclosure in notes)
Task 4: complete — cf3c66e (decoder + optional client method) + re-review minors ae33ec9 (driver distinctness; unavailable carries no driver values), 94b7f51 (notes decoded and rendered)
Task 5: complete — ef14c17 (MarketBriefCard replaces the placeholder; DataHealthBanner wired; brief-driven header; alert/candidate placeholders name their missing services)
Task 6: complete — db077ed (adviser:'full'→adviser=true, 300s council-path timeout, useAdviserCouncil, AdvisersScreen real mode) + simulator-QA fixes 453576b (council entry button — the screen was unreachable), 4dc62b8 (real mode no longer reads demo fixtures; SOFI crash), re-review minors a4edbd6 (spend-honest loading copy; cache tokens in count)
Task 7: complete — landed in the third-review fix round (b05de28 server + 0495488 mobile)
Task 8: complete — 8693bb3 (council defaults from shared cap) + 96487d9 (cross-language contract test; haiku) + 1d2d924 (anchored regex, unique-match guard)
Task 9: partial — roadmap 四点七 + README command repair landed in 4524d27; the README-command doc-pinning test is still owed (queued into the quant plan's Chinese-sweep wave)

Re-review: fable on route/decoder/council, sonnet on the mechanical four. Verdicts: all approved; 1 HIGH (participation cumulative-vs-delta), 1 important hygiene (untracked normative contracts → versioned in e1925bb's parent), minors as above. Simulator QA additionally caught two assembly gaps unit tests missed (no council entry; fixture read in real mode) — reinforcing the native-acceptance rule.

Final verification: all Python/deploy suites OK; mobile 908 passed / 1 skipped; typecheck clean.
Open product question for Franz: adviser taxonomy — named investors (demo) vs de-branded frameworks (shipped real implementation).
