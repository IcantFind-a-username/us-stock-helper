# Cursor 交接补充（2026-08-17）

本文件是给 **Cursor** 的环境适配说明。**主交接文档是
[`2026-08-17-agent-handoff.md`](2026-08-17-agent-handoff.md)，先读它**——红线、目录结构、
测试命令、历史坑都在那里，这里只写 Cursor 与原环境的差异。

原环境（Claude Code）有三样 Cursor 没有的东西：iOS 模拟器 MCP 工具、并行子代理派发、
工作流编排。下面给出等价做法。三条开发原则（模拟器驱动 / TDD / SDD）**一条都不放松**。

---

## 一、模拟器：改用 `xcrun simctl` CLI（已验证可用）

原文档里的 `attach` / `screenshot` / `tap` 是 MCP 工具。Cursor 用命令行等价物：

```bash
# 0) 一次性：确认 Xcode 已选好（需要 Franz 输密码）
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer

# 1) 启动模拟器并开可视窗口（Franz 能看到，你也能截图）
xcrun simctl boot "iPhone 17 Pro Max" 2>/dev/null; open -a Simulator

# 2) 起本地服务栈（在 worktree 根目录）
python3 scripts/local_runtime.py status
python3 scripts/local_runtime.py health

# 3) 让 app 连上 Metro（脚本直接打印深链接）
xcrun simctl openurl booted "$(python3 scripts/metro_deep_link.py)"

# 4) 看画面：截图后用 Cursor 的图片查看能力读它
xcrun simctl io booted screenshot /tmp/app.png
```

**交互操作**（`simctl` 没有 tap/swipe 子命令）三选一：

- **首选：读结构而不是点像素。** 大多数验收问题（"这屏渲染了什么/是不是死代码"）
  用截图 + 读 `apps/mobile/src/screens/*.tsx` 的渲染分支就能判断。
- **需要真的点：** 让 Franz 手动点几下，你截图看结果——他就在旁边，这比装一套自动化更快。
- **需要可重复的交互回归：** 写 Jest 组件测试（本仓库已有 982 个），
  用 `fireEvent` 覆盖交互路径。**交互逻辑归测试，视觉与装配归截图**，两者不互相替代。

⚠️ 改了 **Python 服务**代码必须重启对应 launchd 标签，否则截图上还是旧行为：

```bash
launchctl kickstart -k "gui/$(id -u)/com.franz.us-stock-helper.analysis-api"
```

移动端有 Fast Refresh，改 TS/TSX 即时生效，不用重启。

**验收纪律不变**：每个用户可见的任务，收尾条件是"测试全绿 **+ 截图里真实看到这屏**"，
并把看到了什么写进台账。本项目已发生两次单测全绿但界面是死代码的事故
（会诊屏无入口、真实模式读演示 fixture 直接崩），两次都只有截图能抓到。

---

## 二、客观评审：没有子代理，就用"隔离的第二遍"

原环境靠派发只读评审代理 + 对抗性验证者。Cursor 里的等价做法，按有效性排序：

1. **新开一个 Cursor 会话做评审。** 不带实现时的上下文，只给它：
   `git diff <base>..HEAD`、相关红线（主交接文档 §一）、以及一句
   "你的任务是找出这段改动里的真实缺陷；每条发现都要给出具体的失败场景（什么输入 → 什么错误输出），
   并先自己尝试证伪它，证伪不掉才报告。"
   **换会话比换提示词重要**——同一个会话里"再检查一遍"基本只会自我确认。
2. **变异验证代替第二意见。** 把你的修复反转（或把关键常量改坏），确认测试确实变红，再改回来。
   这条在本仓库救过场：曾有两个变异体大摇大摆走过全绿测试。
3. **对着历史缺陷清单自查。** 主交接文档 §七 的七条坑是真实事故复盘，
   每次提交前对照一遍，尤其是"装配缺口"（函数被测试调用 ≠ 被产品调用）。

评审强度按风险分配：动到 PIT / 评分语义 / 安全 / 并发的改动必须走第 1 条；
纯文案、脚本、配置改动做第 3 条即可。

---

## 三、把规则钉进 Cursor 的上下文

Cursor 不会自动读交接文档。建议在仓库根加一个 `.cursorrules`（或 `.cursor/rules/`），
内容指向权威文件而不是复制它们（复制必然漂移）：

```
本项目的开发纪律见 docs/handoffs/2026-08-17-agent-handoff.md，动手前必读。
不可妥协的红线（违反即回滚）：
1. 只读行情，绝不触碰交易接口；任何字段不得承载订单或凭据。
2. 真实/代理/推断/演示四类数据显式区分；演示内容永不出现在真实模式，真实数据上永不出现"演示"字样。
3. 不可用就显示不可用并给具名原因；禁止用默认值把"没测到"伪装成"测得中性"。
4. PIT：一切数据按真实 available_at 截止；违规必须大声失败，不得静默修补。
5. 顾问是 ±3 封顶软因子（ADVISER_SCORE_CAP，跨语言测试钉死），硬门触发归零。
6. 白话解读禁用喊单动词（买入/卖出/加仓/抄底/梭哈），构造期即被拒绝。

工作方式：
- 所有开发在 worktree .worktrees/iphone-demo（分支 feature/iphone-demo），不是主仓库路径。
- TDD：先写会失败的测试，运行它、确认以预期原因失败，再实现；关键断言做变异验证。
- SDD：按 docs/superpowers/plans/ 下的规格执行，进度写进 .superpowers/sdd/<同名>/progress.md。
- 每个用户可见的改动，收尾要有模拟器截图验收，并写进台账。
- 测试命令用绝对路径 PYTHONPATH（见各包 README，analysis_api 的 README 命令被测试真的执行）。
- 提交用显式 pathspec 暂存，一个逻辑单元一个提交。
```

---

## 四、Cursor 特有的注意事项

- **别让自动应用改动跳过 RED 步骤。** Cursor 的补全很容易一步到位写出实现，
  TDD 的价值恰恰在那个"先看它红"的瞬间。要求自己：测试文件先提交/先运行，再写实现。
- **长任务分批。** 本仓库的套件跑一遍要几分钟（移动端 982 个测试），
  别攒一大堆改动再跑；每个任务收尾跑一次受影响的套件，全量跑放在提交前。
- **并行编辑冲突。** 如果 Franz 同时在别处跑 agent，`git add` 一定用显式路径，
  遇到 `index.lock` 等 3 秒重试，别用 `git add -A`。
- **不要碰的东西**：`~/.us-stock-helper/lan.env`（凭据）、
  `.worktrees/` 之外的主仓库、任何 `sudo` 命令（要 Franz 亲自跑）。

---

## 五、开工顺序（照做即可）

1. 读 `docs/handoffs/2026-08-17-agent-handoff.md` 全文，再读本文件。
2. `cd /Users/franz/Documents/stock_trader/.worktrees/iphone-demo && git pull`
3. 跑一遍基线：各 Python 套件 + `cd apps/mobile && npm test -- --runInBand && npm run typecheck`
   （基线：Python 全绿，移动端 982 passed / 1 skipped）。基线不绿就先查环境，别继续。
4. 起服务栈 + 模拟器，截一张图确认 app 能跑真实数据。
5. 打开规格 `docs/superpowers/plans/2026-08-17-authoritative-source-adapters.md`，
   从 Task 1 Step 1 开始，逐步执行、逐步勾选、逐步写台账。
