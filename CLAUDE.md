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
- 遇到"同一份代码、不同环境算出不同浮点值"先别急着诊断为"跨平台差异"：`sum()` 对 float 列表是从左到右累加，舍入误差只取决于求和顺序，同一顺序在任何平台上结果都相同——真正该查的是求和/累加顺序有没有变过（如从滚动增量换成整窗重算），需要顺序无关的正确舍入就用 `math.fsum()`
- 从主线重启已合并旧 PR 的同名分支时，`git push --force-with-lease -u origin <branch>` 若本地从未 fetch 过该远端分支会报 "stale info"（无 lease 基准）；先 `git fetch origin +refs/heads/<branch>:refs/remotes/origin/<branch>` 建立 tracking ref，若仍报错就显式传 `--force-with-lease=<branch>:<远端实际 sha>`（用 `git ls-remote` 确认）
- `adviser_llm` 的 `anthropic>=0.116` 是开放版本区间，而 `anthropic` SDK 在 1.0.0 版把传输依赖从 `httpx` 改名为 `httpx2`；测试里凡是需要构造真实 `anthropic.*Error` 异常（用于测试 `isinstance` 判断，比无脑换成内置异常更贴近真实场景）时，导入传输库要写成 `try: import httpx / except ModuleNotFoundError: import httpx2 as httpx`，不要硬编码某一个——否则测试红不红取决于 pip 这次解析到哪个 anthropic 版本，看起来像"偶发 flaky"实则是版本漂移
- 全新容器里 `scripts/test_changed.sh` 只对"改动涉及"的服务目录做 `pip install -e`；若该服务通过绝对包名 import 同仓其他内部服务（如 `analysis_api` 依赖 `device_auth`/`information_layer`/`decision_engine`/`adviser_layer`），首轮会报 `ModuleNotFoundError`，这是新容器没装全内部依赖，不是代码坏了——先把用到的内部包都 `pip install -e` 一遍再跑门禁
