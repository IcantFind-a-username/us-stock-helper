# 迭代待办队列

自动迭代的唯一任务来源：每轮从最上面的未勾选项取**一项**做完，不跳项、不并行。完成后勾掉并在"完成记录"补一行；过程中发现的新问题按优先级插入队列，而不是顺手去修。

条目格式：优先级、改动范围（目录级）、完成标准（可被测试验证）。

## 队列

- [ ] **P0** `services/market_gateway`：K 线 `available_at` 应记录真实接收时刻，而非理论收盘时刻（roadmap 第一节指出的时序缺陷）。完成标准：新增测试证明 `available_at` 来自接收时钟；理论收盘时刻早于接收时刻的用例不再通过旧逻辑。
  - 2026-08-15 诊断：修复代码已实现（`opend_adapter.py` `_candle_item`：`available_at`/`received_at` 均改为 `iso_z(now)`，即调用方传入的接收时钟读数，不再用 `bar_close`），新增/改写的 `test_opend_adapter.py` 三个测试单独跑全绿（含新测试 `test_candle_available_at_reflects_receive_clock_not_bar_close`，修复前会失败：期望值 `15:56:00Z` 实际拿到 `15:55:00Z`，即旧逻辑用的是理论收盘时刻）。但 `bash scripts/test_changed.sh` 对本服务不绿：`test_snapshot_contract_v3.py` 的 2 个 contract fixture 测试失败（`101.9` vs `101.89999999999999`），已用 `git stash` 验证该失败在本改动之前、`feature/iphone-demo` 合并后即存在，与 `available_at` 改动无关。故未勾掉本项，留给下一轮：先做下面新插入的 fixture-staleness 条目，再回来复核本项验收标准后勾掉。代码改动已提交在 `claude/token-quota-check-4lvpkl` 分支上，未回退。
- [ ] **P0** `services/market_gateway`：`test_snapshot_contract_v3.py` 的 `test_v2_snapshot_matches_the_checked_in_contract_fixture` / `test_v3_snapshot_matches_the_checked_in_contract_fixture` 对不上 `tests/fixtures/contract_snapshot_v2.json` / `v3.json`（如 `high: 101.9` vs 实际渲染出 `101.89999999999999`），错误信息本身提示"fixture is stale or missing"。需人工核实：这是 `feature/iphone-demo` 分支引入 serializer/计算逻辑变更后忘记同步 regenerate 固件（可用 `REGEN_CONTRACT_FIXTURE=1 python3 -m unittest services.market_gateway.tests.test_snapshot_contract_v3` 重新生成），还是计算精度出现了真实回归（不应盲目 regenerate 掩盖）。完成标准：查明浮点差异来源；确认非计算回归后 regenerate 固件并提交，或如是回归则修复计算逻辑，两测试恢复全绿。
- [ ] **P0** `services/market_gateway`：越界/违规时序数据不得静默降级，必须显式报错或告警。完成标准：对每处静默降级点补测试，断言其抛错或产生可观测告警。
- [ ] **P1** `apps/mobile` + `services/analysis_api`：主力/散户占比界面展示算法版本串（roadmap：四层防线唯一缺口）。完成标准：API 响应含版本字段的测试 + UI 渲染该字段的测试。
- [ ] **P2** 评估 roadmap 第二节零实现能力（期权异动、社媒情绪、全市场扫描）的最小竖切片，拆成可单轮完成的条目后插入本队列。完成标准：本文件新增拆分后的具体条目。

## 完成记录

（格式：日期 · 条目 · PR/commit · 一句话结果）
