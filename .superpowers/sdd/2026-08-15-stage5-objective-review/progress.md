# SDD ledger — 2026-08-15 third objective review (stage 5+ surface)

Scope: `1cadc7e..310e581` (38 commits) + stage-5 core 5439941/0961e05, all verified at HEAD.
Review run: 8 risk-dimension reviewers → dedup → adversarial verification (2 per critical/important, 1 per minor). 25 proposed, 24 confirmed (critical 2 / important 11 / minor 11), 1 refuted (mechanism correct, scenario unreachable — reachability is part of a finding).
Artifacts: confirmed-findings.json, fix-units.json, review-summary.md, adviser-adjustment-contract.md (local, gitignored).

## Fix round 1 (11 units, parallel, model-tiered)
- b0829fd pairing-code candidate window (device_auth 99 OK)
- 8693bb3 adviser cap single authority; 8390099 adviser_llm grounding all served text fields + honest cache note
- b51c5ac preflight robustness; d7787b1 smoke_live verdict honesty
- c30be17 + afef2e3 mobile pairing recovery
- d2ebda0 chart touch/viewBox alignment; cb4325b window identity reset
- 258f37b evidence cutoff after fetch + exclusion disclosure (CRITICAL)
- ea91278 unmeasured sentiment/pattern typed unavailable (CRITICAL)
- e4ad724 request-scoped EvidenceRead gaps

## Wave 2 (same round, overlapping files serialized)
- 20c7260 freshness budget from data interval; 29e1fbe CIK registry required + production wiring
- 7f091d7 fundamentals staleness bound + quarter-span comparability
- b05de28 adviser adjustment null-or-folded single authority (server)
- 2e35e92 riskplan strict decode; 3f32af7 blocked-score visibility + mapped error copy; 0495488 adviser adjustment mobile decode + display rule

## Re-review (risk-tiered: fable on PIT/financial/concurrency cluster, sonnet on mechanical cluster)
Findings: 3 important (collector/coordinator locking half unfixed; recovery pill overlapping tab bar → accidental forgetDevice; reanchor only covered identity change, not rolling refresh) + 3 minor (sentiment marker not on wire for empty windows; weekly budget latent stale-gate; English boilerplate note).

## Fix round 2 (7 commits)
- 8b5ebe2 collector/coordinator locks + atomic reserve/commit poll; 02f0dff 情绪未测量 marker on empty windows; 1906530 weekly 9-day budget; 1728910 Chinese adviser-off note
- f6946ef + 4551e90 pill above tab bar via shared layout.tabBarHeight + SafeAreaProvider added at root (latent production crash found and fixed); eb64f23 timestamp-based window reanchoring
- Round-2 re-review: single fable reviewer over all seven commits (verdict recorded below when complete)

## Final verification (2026-08-15 evening)
analysis_core / information_layer / adviser_layer / decision_engine / market_gateway / device_auth / analysis_api / scripts / deploy all OK; adviser_llm 122; mobile 829 passed / 1 skipped; typecheck clean.

Roadmap record: section 四点七; bookkeeping corrections to 二.3, 二.6, 阶段 4/5/7/8.
