# Sonnet 交接（2026-08-17）

**你是接手开发的 agent。本文件是你的操作手册，按顺序照做。**

先读这两份（不要跳过，它们定义了什么算"做对了"）：
1. `docs/handoffs/2026-08-17-agent-handoff.md` — 主交接：红线、目录、测试命令、历史坑
2. `docs/superpowers/plans/2026-08-17-authoritative-source-adapters.md` — 你要执行的规格

如果你在 Cursor 里工作，再读 `2026-08-17-cursor-handoff.md`（模拟器用 `xcrun simctl` 的写法）。

---

## 最重要的一条：不确定就停下来问，不要猜

这个项目里**猜错的代价远大于问一句的代价**。历史上最恶劣的三个缺陷都不是"写得不够多"，
而是"在不确定的地方自作主张"：

- 把一份内幕交易申报以 **1.0 相关度、VERIFIED、0.99 可靠度** 挂到了错误的股票上；
- 把"没读到数据"评成"读了，是中性 0.0"，于是系统越瞎、分数看起来越自信；
- 修好的机器没人接线（函数被测试调用 ≠ 被产品调用），全绿了三天。

**遇到下面任何一种情况，立刻停下来写进台账并告诉 Franz，不要继续写代码：**

- 规格里写的和你在代码/真实数据里看到的不一致（**真实数据永远是权威，规格不是**）；
- 你需要修改规格"文件清单"之外的文件，且理由不是显而易见的；
- 你需要改一个会影响评分、排序、PIT 时间戳或归属的行为；
- 一个测试你想不出怎么让它先红；
- 你想加默认值 / fallback / `except: pass` 来让某个东西"能跑通"。

停下来是合格的产出。硬着头皮猜不是。

---

## 一、开工前的固定动作（每次会话都做）

```bash
cd /Users/franz/Documents/stock_trader/.worktrees/iphone-demo   # 注意：worktree，不是主仓库
git pull
```

跑基线，**不绿就先查环境，绝对不要在红的基线上开始开发**：

```bash
W=$PWD
PYTHONPATH=$W/services/analysis_core python3 -m unittest discover -s services/analysis_core/tests
PYTHONPATH=$W/services/information_layer python3 -m unittest discover -s services/information_layer/tests
PYTHONPATH=$W/services/adviser_layer:$W/services/analysis_core python3 -m unittest discover -s services/adviser_layer/tests
PYTHONPATH=$W/services/analysis_core:$W/services/information_layer:$W/services/adviser_layer:$W/services/decision_engine python3 -m unittest discover -s services/decision_engine/tests
PYTHONPATH=$W/services/market_gateway/src:$W/services/analysis_core python3 -m unittest discover -s services/market_gateway/tests
PYTHONPATH=$W/services/device_auth/src python3 -m unittest discover -s services/device_auth/tests
PYTHONPATH=$W/services/analysis_api/src:$W/services/analysis_api/tests:$W/services/analysis_core:$W/services/information_layer:$W/services/adviser_layer:$W/services/decision_engine:$W/services/market_gateway/src:$W/services/adviser_llm/src:$W/services/device_auth/src python3 -m unittest discover -s services/analysis_api/tests
PYTHONPATH=$W/scripts python3 -m unittest discover -s scripts/tests
cd apps/mobile && npm test -- --runInBand && npm run typecheck && cd $W
```

**PYTHONPATH 必须是绝对路径**（`$W/...`），相对路径会在子进程测试里失败。这条坑过很多次。

起服务栈与模拟器（做任何用户可见的改动都需要）：

```bash
python3 scripts/local_runtime.py health          # 四个组件都要 reachable
open -a Simulator
xcrun simctl openurl booted "$(python3 scripts/metro_deep_link.py)"
xcrun simctl io booted screenshot /tmp/app.png   # 然后看这张图
```

⚠️ **改了 Python 服务代码，必须重启对应组件，否则屏幕上还是旧行为：**

```bash
launchctl kickstart -k "gui/$(id -u)/com.franz.us-stock-helper.analysis-api"
```

移动端（.ts/.tsx）有 Fast Refresh，不用重启。

---

## 二、每个任务的固定流程（不要跳步）

1. **读规格里这个任务的全文**，包括它的"Files"清单——只改清单里的文件。
2. **写测试，运行它，确认它红了**，并且**红的原因和你预期的一致**。把失败输出复制到台账。
   - 如果它一上来就绿，说明你的测试没测到东西，重写。
   - 如果它红的原因和预期不同，先搞清楚为什么，不要直接改实现。
3. **写最小实现让它绿**。不要顺手改别的。
4. **变异验证**（只对关键断言）：把你的修复故意改坏（反转条件、改常量），
   确认测试变红，再改回来。写进台账。
5. **跑受影响的全部套件**（上面的命令，至少跑你改动涉及的包 + analysis_api）。
6. **用户可见的改动要截图验收**：重启服务 → 模拟器截图 → 看清楚那一屏显示了什么。
   把"看到了什么"写进台账（不是"验收通过"，而是"AAPL 页显示 $305.93，日K/MACD 正常渲染"）。
7. **提交**：只暂存这个任务的文件，用显式路径：
   ```bash
   git add -- <具体文件1> <具体文件2>
   git commit -m "fix: 一句话小写祈使句

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
   ```
   遇到 `index.lock` 等 3 秒重试。**永远不要 `git add -A` 或 `git add .`**。
8. **勾掉规格里这个任务的复选框**，并往台账追加一个任务块。
9. **推送**：`git push origin feature/iphone-demo`（每完成 1–2 个任务推一次，别攒着）。

---

## 三、台账格式（照抄，每个任务一块）

文件：`.superpowers/sdd/2026-08-17-authoritative-source-adapters/progress.md`
（该目录被 gitignore，提交时用 `git add -f`）

```
Task N: <名字> — 完成
- RED: <测试名> 失败，输出：<粘贴真实失败信息>
- GREEN: <套件名 计数>
- 变异验证: 把 <X> 改成 <Y> → <测试名> 变红；已恢复
- 套件: information_layer 247 OK / analysis_api 273 OK / ...
- 模拟器: <哪一屏，看到了什么具体内容>
- 提交: <hash> <message>
- 遗留: <下一个人必须知道的事；没有就写"无">
```

---

## 四、现在的状态与你要做的事

### 已完成（不要重做）

| 提交 | 内容 |
|---|---|
| `8cfab6c` | SEC current filings 扩到 6 种表格（10-Q/10-K/SCHEDULE 13D/13G）。**真实样本证明 `SC 13D`/`SC 13G` 已被 EDGAR 弃用**，规格里的假设是错的，以 fixture 为准 |
| `abefa25` | 公司 IR 源泛化（+MSFT/INTC/BA/AMZN/GOOGL，每家都核查过 robots） |
| `801fb29` | 监管源：Nasdaq 停牌适配器、FDA/FTC/DOJ 公告（OFAC 无 RSS，地缘政治源如实保持缺位） |
| `4ef2226` | 协调器快照持久化接线（重启不再重播回看窗口） |
| `ead0bd7` | **多方申报重复发布修复**（PIT 红线）：EDGAR 对一份申报的每一方发一条目，两条共享 claim key 却互相当作"修订版"无限重发，导致这类申报永远显示"刚刚到达"、`stale` 永不触发。按 `docs/superpowers/plans/2026-08-17-dual-entry-filing-reannouncement.md` 的方案 A 修复（每方独立 claim key + 按 accession 聚簇 + 代表排序新增"带归属"档位）。**部署注记**：升级后第一次轮询会对回看窗口内的每份申报一次性重新宣布（有界、仅一次，旧格式快照能正常加载） |
| `44d396c` | 上条的台账记录 |

**⚠️ 一件必须在生产栈起来后补做的验证**：`ead0bd7` 的实现代理没跑成真实的
双重启检查（当时服务栈没起）。你第一次把栈跑起来时，请做：
`launchctl kickstart -k "gui/$(id -u)/com.franz.us-stock-helper.analysis-api"` 连做两次，
确认第二次启动没有重新宣布回看窗口内的申报，并把结果写进台账。

### 评审发现（2026-08-17，对抗性评审 Cursor 的四个提交）

评审结论：**归属正确性（本项目最恶劣的历史缺陷类）这一轮是扎实的**——
`_TITLE_FORM` 正则对全部 145 条 fixture 条目与 EDGAR 自己的 `<category term>` 零不符；
`(Filed by)` 持有人在任何路径下都不会认领股票代码；快照持久化的原子写/0600/整体拒绝/
真的被调用（不是"函数没人接线"）全部核实通过。发现两条真缺陷：

| 严重度 | 缺陷 | 状态 |
|---|---|---|
| **critical** | **Nasdaq 停牌源在盘中完全瞎**：feed 的 `pubDate` 是日粒度（美东午夜），生产回看窗口是 6 小时，所以美东 06:00 之后的每一次轮询都返回 0 条——**整个交易时段拿不到任何停牌**。现有测试用 60 天窗口，把这个 bug 完全遮住了。 | 已派修，见下 |
| minor（潜伏） | `sec.py::_symbol_relevance` 对不归属角色仍会走关键词兜底。当前注册表没给 SEC 源配 `symbol_mappings`，所以够不着；但将来谁配了，`(Filed by) BERKSHIRE HATHAWAY` 就会以 0.7 关联度重演 DaVita 型误归属。 | 未修，加个守卫或注释即可 |

另外一条 **minor**：`blog.google` 是消费级营销博客（`google-newsroom`），高噪音促销文案会以
0.9 关联度进入情绪证据流。与 Apple Newsroom 的既有取舍一致且已在方法论文档披露，
但如果情绪分数出现莫名偏多，先查这里。

### 你的下一件事：Task 5 · 证据闸门重审

规格在 `2026-08-17-authoritative-source-adapters.md` 的 Task 5。**它有一个前置条件：必须在美股交易日的数据窗口里测量**（EDGAR 的 getcurrent 回看窗口在周末是空的，测出来没有意义）。

具体做法：

1. **先确认现在是交易日窗口**：`TZ=America/New_York date`，美东工作日盘中或收盘后几小时内最好。
   如果是周末或美东深夜，**停下来告诉 Franz 等交易日**，不要用空窗口的数据下结论。
2. 跑 Cursor 已经写好的测量脚本（在 `services/analysis_api/scripts/measure_evidence_gate.py`，
   提交 `540b0a8`）。先读它的用法说明再跑。
3. **把测量结果写进台账**：46 只自选里有多少只的 `evidence_confidence` 越过了 0.35，分布如何。
4. 然后才是代码改动：把 `services/analysis_core/us_stock_helper_core/scoring.py:450-451` 的
   裸字面量 `0.35` 提成有名字的常量，docstring 写清楚依据和测量日期，
   并钉死边界行为（刚好低于→触发，刚好高于→不触发，零证据→触发）。
5. **只有测量数据支持时才改这个数值**。如果改了，必须
   bump 评分的 `method_version` 并在服务端解释文案里说明——
   静默改阈值 = 静默改分数，这是红线（参考 `explainable-horizon-score-v2` 的先例）。
6. 模拟器验收：打开 Dashboard 和三只个股页，记录"综合结论"现在各说什么、
   还有几只是"不可行动"、给出的具名原因是什么。

### 之后

- **Task 6（申报正文抓取）**：先问 Franz 要不要做，**不要自己开工**。
  这是新能力不是扩展（会大幅增加 EDGAR 请求量，有被封风险）。
- **Task 7（方法论/README/roadmap 收口）**：把新增的每个源写进
  `docs/indicator-methodology.md`，并更新 roadmap 阶段 6。
- 再往后的方向见主交接文档第六节的 R2–R7。

---

## 五、绝对不要做的事

- ❌ 不要在主仓库路径 `/Users/franz/Documents/stock_trader` 下开发（要在 `.worktrees/iphone-demo`）
- ❌ 不要 `git add -A` / `git add .`
- ❌ 不要跳过"先看测试变红"这一步
- ❌ 不要为了让测试快而降低轮询间隔（注入时钟，不要改常量）
- ❌ 不要新增任何需要 `Authorization`/`Cookie`/登录/付费的数据源（传输层会直接拒绝）
- ❌ 不要碰交易接口相关的任何东西（本项目只读行情，这是最高红线）
- ❌ 不要用默认值填充缺失数据（"不可用"就显示"不可用"并给具名原因）
- ❌ 不要跑 `sudo`（需要密码，让 Franz 自己跑）
- ❌ 不要改 `~/.us-stock-helper/lan.env`（凭据文件）
- ❌ 不要在没有真实抓取样本的情况下注册新数据源（fixture 是权威，猜的 URL 不是）

---

## 六、需要 Franz 拍板的事（不要替他决定）

1. Task 6（申报正文抓取）是否值得做；
2. 顾问 taxonomy：具名投资人 vs 去品牌化框架；
3. 广度/RS 股票池是否扩到自选之外；板块 RS 需要配置
   `ANALYSIS_API_SECTOR_RS_SYMBOLS` / `_BENCHMARK` 才会出值；
4. 新闻 wire 商业授权是否采购（不采购就永远不要接 Reuters/Bloomberg 类源）；
5. 换网后 `apps/mobile/.env` 与服务端来源白名单要手动同步，是否要做个自愈脚本。
