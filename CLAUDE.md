# us-stock-helper

美股投资决策辅助系统：只读行情 + 可解释分析库 + 原生 iOS App。现状与开发顺序以 `docs/roadmap-to-delivery.md` 为准，待办队列在 `docs/backlog.md`。

本文件是唯一的 agent 记忆（`AGENTS.md` 是指向它的符号链接，Claude Code 与 Codex 读写同一份）。注意：Stop hook 门禁只在 Claude Code 中自动生效，其他工具必须自觉执行迭代规则第 3 条。

## 仓库地图

- `services/` — 8 个独立 Python 包（各有 pyproject + tests）：`analysis_core` 分析原语（零依赖、严禁未来函数）、`analysis_api` HTTP 服务、`market_gateway` 行情网关、`adviser_llm`/`adviser_layer` LLM 顾问、`decision_engine`、`device_auth`、`information_layer`
- `apps/mobile/` — Expo/React Native App（jest + tsc）
- `deploy/`、`scripts/` — 部署与本地运行时（测试面向 macOS/launchd，在 Linux 上会有环境性失败，属正常）
- `docs/handoffs/` — 历次迭代交接记录

## 测试命令（已验证）

- 单个服务：`python3 -m pip install -q -e services/<name> && python3 -m pytest services/<name>/tests -q`
- 只跑与改动相关的测试（优先用这个）：`bash scripts/test_changed.sh`——屏幕只显示摘要/失败末尾，完整日志在 `test_changed.log`，不要把完整日志读进上下文
- 移动端：`cd apps/mobile && npm test`（需先 `npm ci`）；类型检查 `npm run typecheck`
- CI（`.github/workflows/ci.yml`）以 8 个服务全绿为合并门禁；`deploy/`、`scripts/` 的 macOS 专属套件不在 Linux CI 中跑

## 不可妥协原则（违反即打回，详见 roadmap 第一节）

1. 只读行情，绝不触碰任何交易接口
2. 主力/散户占比是代理信号，不得冒充机构持仓
3. 预测恒为三情景概率分布，带反方证据与失效条件，永不自动下单
4. 严禁未来函数；时序越界必须显式报错，不得静默降级

## 迭代规则

1. 每轮只做 `docs/backlog.md` 中的一项，改动保持小而完整。大功能不许在单会话里一口气做完：先拆成可单轮完成的 backlog 条目（Claude Code 用 `/plan-feature`），再逐轮执行（执行类迭代用 Sonnet 档模型即可，测试门禁兜底质量）
2. 修 bug 先写复现它的失败测试，再改代码（回归测试就是记忆）
3. 结束前必须跑 `bash scripts/test_changed.sh` 且全绿
4. 完成后更新 backlog（勾掉完成项、追加新发现的问题）
5. 踩到值得记住的坑，压缩成一行写进下方"经验教训"

## 经验教训

（上限 15 条；新增时若已满或某条已过时/已被测试覆盖固化，删掉它。只留仍然有效的规则。）

- `deploy/tests`、`scripts/tests` 在 Linux 容器里会有环境性失败（launchd/fchmod/systemd 假设），不代表代码坏了，勿花 token 去"修"
- `services/market_gateway` 的 `test_snapshot_contract_v3.py` 两个 contract fixture 测试目前不绿（fixture 与 serializer 输出对不上，如 `101.9` vs `101.89999999999999`），与本条目无关的改动跑 `test_changed.sh` 也会被拖红；已作为独立 backlog 条目排队，未查明前不要当作"我的改动搞坏的"
