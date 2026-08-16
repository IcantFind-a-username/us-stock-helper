# Agent 交接：us-stock-helper（2026-08-17）

这份文件是给**接手开发的 AI agent** 的完整上下文。读完它 + `docs/roadmap-to-delivery.md`
就足以继续工作，不需要回溯此前的会话记录。

---

## 零、开发三原则（不满足其一，这次开发就不算完成）

这三条是 Franz 明确要求的工作方式，优先于任何"看起来更快"的做法。

### 原则一：**开着 iOS 模拟器，看着真实画面开发**

不是写完再截图验收，而是**从开工就把模拟器面板开着**，每落地一个用户可见的改动就去看那一屏。

```bash
# 开工第一件事（不是最后一件）
# 1) 确认 Xcode 已选好（需要 Franz 输密码，agent 不能代跑 sudo）
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
# 2) 起本地栈
python3 scripts/local_runtime.py status && python3 scripts/local_runtime.py health
# 3) 拿到深链接
python3 scripts/metro_deep_link.py
```

然后用 iOS Simulator 工具：`attach` 开实时面板 → `open_url` 打开上一步的深链接 →
`screenshot` / `tap` / `swipe` 逐屏走。移动端有 Fast Refresh，改代码即时可见；
**改了 Python 服务要 `launchctl kickstart -k` 对应标签**，否则屏幕上还是旧行为。

**为什么这条是硬性的**：本项目已经发生过两次单测全绿但界面是死代码的情况——
13 席顾问会诊屏做好了却全 app 没有入口；顾问屏在真实模式无条件读演示 fixture，换个 symbol 就崩。
两者都是在模拟器里点出来的，测试一个都没抓到。**测试证明逻辑对，模拟器证明用户真的能用到。**

### 原则二：**TDD——测试必须先看到它变红**

写实现前先写会失败的测试，**运行它，确认它以预期原因失败**，再实现到绿。
从未变红的测试什么也没证明——历史上有两个变异体大摇大摆走过全绿测试。
关键断言要做**变异验证**：故意把修复反转，确认测试确实变红，再改回来。

### 原则三：**SDD——先有规格，再有代码；进度写进台账**

每一段工作都必须有一份**计划文档**和一份**台账**，两者一起防止开发偏离：

| 文件 | 作用 |
|---|---|
| `docs/superpowers/plans/<日期>-<名字>.md` | 规格：目标、架构、全局约束、逐任务的"先红测试→实现→验证→提交"步骤与勾选框 |
| `.superpowers/sdd/<同名>/progress.md` | 台账：每个任务的 RED 证据、GREEN 结果、评审发现与修复、提交哈希、遗留项 |

**接手时：下一段的规格已经写好了**，见
[`docs/superpowers/plans/2026-08-17-authoritative-source-adapters.md`](../superpowers/plans/2026-08-17-authoritative-source-adapters.md)。
按任务顺序执行，每完成一个任务就勾掉它的复选框并往台账追加一行。
**不要自己发挥新方向**；规格与现实冲突时，先把冲突写进台账并告知 Franz，由他定夺。

后续每开一段新工作，同样先写规格再动手（照抄现有两份已完成计划的结构：
`2026-08-15-demo-parity-market-brief-and-council.md`、`2026-08-15-quant-foundations-plain-language.md`）。

---

## 一、这是什么项目

一个**证据优先的美股研究助手**：iOS App（Expo/React Native）+ 一组 Python 只读服务。
产品定位是"辅助判断"，不是"喊单"，更不是交易终端。所有者 Franz 是产品负责人、量化金融小白、
中文交流、以短线为主。

**十条红线中最容易被工程便利侵蚀、必须每次核对的六条：**

1. **只读行情，绝不触碰交易接口。** 全仓库对 `place_order`/`TradeContext`/`unlock_trade` 零命中，
   任何字段都不得承载订单或凭据。这条没有例外。
2. **真实 / 代理 / 推断 / 演示四类数据显式区分。** 演示模式（`演示模式` 开关，仅开发构建）
   的内容永远不得出现在真实模式；真实数据上永远不得出现"演示"字样。
3. **不可用就显示不可用。** 没有可靠数据时说"不可用"并给出**具名原因**，不得用装饰性默认值填充。
   典型反例（历史上真实发生过）：把"没测到"评成"测得中性 0.0"。
4. **PIT（point-in-time）正确性。** 一切数据按真实 `available_at` 截止；越过决策截止的未来数据
   必须**大声失败**，不得静默修补，也不得被误报为"数据缺失"。
5. **顾问是有上限的软因子**（±3 分，共享常量 `ADVISER_SCORE_CAP`，跨语言测试钉死），
   不能替代证据层与风控层，硬门触发时归零。
6. **白话不喊单。** 面向用户的解读只说"这是什么 / 现在什么状态 / 什么情况下作废"，
   禁用词 买入/卖出/加仓/抄底/梭哈 在 `PlainReading` / `PatternShapeSignal` 构造期即被拒绝。

---

## 二、工作区与分支（第一个坑）

```
/Users/franz/Documents/stock_trader                    ← 主仓库，main 分支（几乎是空的）
/Users/franz/Documents/stock_trader/.worktrees/iphone-demo  ← 真正的开发工作区，分支 feature/iphone-demo
```

**所有开发都在 worktree 里。** 在主仓库路径下跑 `git`/测试命令会找不到文件——这是新 agent 第一天
必踩的坑。开工先 `cd /Users/franz/Documents/stock_trader/.worktrees/iphone-demo`。

远端：`origin/feature/iphone-demo`（GitHub `IcantFind-a-username/us-stock-helper`，Apache-2.0）。

目录：

| 路径 | 内容 |
|---|---|
| `apps/mobile` | Expo SDK 57 / RN 0.86 / TS 严格模式；`src/screens`、`src/components`、`src/data`（解码器）、`src/domain`（纯计算）、`src/i18n`（服务端词汇映射） |
| `services/analysis_core` | 指标/评分/形态/波动率/广度/RS/RVOL/白话词汇（纯 stdlib，无 I/O） |
| `services/information_layer` | 证据采集、情绪打分、跨源聚类、协调器限速（唯一的外网出口，HTTPS + host 白名单） |
| `services/decision_engine` | 三层合成，单一 `as_of` 截止 |
| `services/adviser_layer` / `services/adviser_llm` | 13 席风格顾问（前者纯库封顶逻辑，后者真实 Claude 调用 + 落地检查） |
| `services/market_gateway` | 只读 moomoo OpenD 边界 |
| `services/analysis_api` | 只读 HTTP 边界：`GET /health`、`GET /decision`、`GET /market-brief`、`POST /v1/device-pairings` |
| `services/device_auth` | 设备配对凭据（SQLite，单次码、可吊销） |
| `scripts/`、`runtime/`、`deploy/` | 本地 launchd 常驻栈、live 冒烟、部署套件 |

---

## 三、怎么跑（第二个坑）

### 测试命令必须用**绝对路径** PYTHONPATH

相对路径会在子进程测试（analysis_api 有一个换 cwd 的子进程用例）里解析失败。
每个包的规范命令在其 README 里，且 `services/analysis_api/tests/test_documentation.py`
会**真的执行** README 里写的命令——文档漂移会红灯。

```bash
cd /Users/franz/Documents/stock_trader/.worktrees/iphone-demo && W=$PWD

PYTHONPATH=$W/services/analysis_core python3 -m unittest discover -s services/analysis_core/tests
PYTHONPATH=$W/services/information_layer python3 -m unittest discover -s services/information_layer/tests
PYTHONPATH=$W/services/adviser_layer:$W/services/analysis_core python3 -m unittest discover -s services/adviser_layer/tests
PYTHONPATH=$W/services/analysis_core:$W/services/information_layer:$W/services/adviser_layer:$W/services/decision_engine python3 -m unittest discover -s services/decision_engine/tests
PYTHONPATH=$W/services/market_gateway/src:$W/services/analysis_core python3 -m unittest discover -s services/market_gateway/tests
PYTHONPATH=$W/services/device_auth/src python3 -m unittest discover -s services/device_auth/tests
PYTHONPATH=$W/services/analysis_api/src:$W/services/analysis_api/tests:$W/services/analysis_core:$W/services/information_layer:$W/services/adviser_layer:$W/services/decision_engine:$W/services/market_gateway/src:$W/services/adviser_llm/src:$W/services/device_auth/src python3 -m unittest discover -s services/analysis_api/tests
PYTHONPATH=$W/scripts python3 -m unittest discover -s scripts/tests
# deploy 用与 analysis_api 相同的服务路径再加 $W/deploy

cd services/adviser_llm && PYTHONPATH="src:../information_layer:../analysis_core" python3 -m pytest -q

cd $W/apps/mobile && npm test -- --runInBand && npm run typecheck
```

基线（2026-08-17）：Python 各套件全绿，移动端 **982 passed / 1 skipped**，typecheck 干净。

### 本地常驻栈（launchd，四个标签）

```bash
python3 scripts/local_runtime.py status     # 看四个组件
python3 scripts/local_runtime.py health
python3 scripts/local_runtime.py reinstall  # 常规代码变更后
launchctl kickstart -k "gui/$(id -u)/com.franz.us-stock-helper.analysis-api"   # 单组件重启
```

端口：行情网关 loopback `8765` / LAN `8766`，分析 API `8770`，Metro `8088`（**只有 8088 是规范的**，
8081/8083 是历史遗留，只报告不动它们）。OpenD 是外部依赖，`127.0.0.1:11111`。

⚠️ **改了 Python 服务代码后必须重启对应 launchd 标签**，否则手机/模拟器看到的还是旧行为——
这在联调时反复骗过人。移动端有 Fast Refresh，不用重启。

⚠️ `local_runtime.py` 的 CLI 把所有异常吞成一句 `local runtime command failed`
（这本身是个待修缺陷）。要看真实原因，直接在 Python 里调 `build_default_controller()` 并 traceback。
若清单状态卡在 `rollback_required`，先 `launchctl bootout` 相关标签再 `install`。

### 模拟器联调（验收面）

```bash
# 先确保 xcode-select 指向完整 Xcode（需要 Franz 输密码，agent 不能代跑 sudo）
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
```

用 iOS Simulator MCP 工具：`attach` 开实时面板 → `open_url` 打开
`exp+us-stock-helper://expo-development-client/?url=http%3A%2F%2F<Mac的LAN IP>%3A8088`
（`python3 scripts/metro_deep_link.py` 会直接打印这条 URL）→ `screenshot` / `tap` / `swipe` 验收。
坐标空间 440×956 点（截图是像素，换算 ≈ ÷2.09）。

真机 iPhone 走 `docs/runbooks/iphone-dev-client.md`：免费个人签名 7 天过期，需要 Franz
连线解锁 + Xcode Run，agent 无法代劳。

---

## 四、工作方法（这套 harness 的核心，必须遵守）

### 1. TDD：测试必须**先看到它变红**

写实现前先写会失败的测试，**运行它，确认它以预期原因失败**，再实现到绿。
从未变红的测试什么也没证明——这条是被历史缺陷反复教出来的（两个变异体曾走过全绿测试）。
关键断言要做变异验证：故意把修复反转，确认测试确实变红。

### 2. 客观评审循环

每批实现落地后，派**只读评审代理**做对抗性复核，每条发现再派**验证者**去证伪它。
证据：三轮评审在"我自己刚写的代码"里找出 11/19/24 条真实缺陷。
评审提示词里要明确预告"你的发现将被对抗性验证"——实测能显著提高自我过滤
（第三轮 25 提仅 1 条被证伪，前两轮是 40 提 29 伪、34 提 15 伪）。

### 3. 模型分工（Franz 明确要求，不需要他每次声明）

规则写在 `.agents/skills/subagent-driven-development/SKILL.md` §Model Selection，派发时**必须显式传 model**：

| 档位 | 用于 |
|---|---|
| **haiku** | 计划文本已含完整代码的转写实现、单文件机械修复 |
| **sonnet** | 散文规格实现、多文件集成、修复轮 1–3、机械维度评审（**评审员和散文实现者的下限**） |
| **fable** | 架构/设计、整分支终审、PIT/金融语义/安全/并发维度的评审、修复轮 4–5 升档 |

对抗性验证密度：critical/important 双人，minor 单人或抽查。
复用已产出工件（findings.json、契约文件、差距地图）而不是重扫代码库。
**ultracode 开着也不改变分档**——它指编排的穷尽度，不是把所有代理放最强档。

### 4. 提交纪律

一个逻辑单元一个提交；**用显式 pathspec 暂存**（`git add -- <具体路径>`），因为经常有并行代理
在同一 worktree 里工作。提交信息是仓库风格的小写祈使句（如 `fix: stop scoring an unread market as neutral`），
末尾空一行加 `Co-Authored-By:` trailer。遇到 `index.lock` 冲突就 sleep 3 秒重试。

计划文档放 `docs/superpowers/plans/`，台账放 `.superpowers/sdd/<plan-name>/progress.md`
（该目录默认 gitignore，用 `git add -f` 入库）。

### 5. 联调验收高于单测（见开头原则一）

**每个用户可见的任务，收尾条件是"测试绿 + 模拟器里真实看到这屏"**，两者缺一不可。
台账里要写清楚这次在模拟器里看到了什么（哪一屏、什么数据、什么状态），
"跑过测试了"不能替代"看到了"。

### 6. 任务完成的定义（DoD）

一个任务只有同时满足下面五条才算完成，才可以勾掉计划里的复选框：

1. 先红后绿的测试存在，且 RED 的失败原因与预期一致（台账记录失败输出）；
2. 受影响的**全部**套件绿（Python 各包 + `npm test` + `npm run typecheck`）；
3. 用户可见的改动在**模拟器里亲眼验收过**（台账记录看到了什么）；
4. 只用显式 pathspec 暂存本任务的文件，单独提交，信息含 `Co-Authored-By` trailer；
5. 台账追加一行：RED 证据、GREEN 结果、模拟器验收、提交哈希、遗留项。

---

## 五、当前状态（2026-08-17）

### 已完成并已推送（`origin/feature/iphone-demo`，HEAD `ff70a6d` 之后）

- **阶段 1–3**：红灯契约收敛、双指标引擎收敛（`analysis_core` 为 canonical）、PIT 语义债偿还。
- **阶段 5 主体 + 第三轮客观评审**（roadmap 四点七）：24 条确认缺陷（2 条 critical）全部修复并复审收口。
- **演示面对齐计划**（`docs/superpowers/plans/2026-08-15-demo-parity-market-brief-and-council.md`，9 任务全完成）：
  `GET /market-brief` 只读市场简报路由（诚实披露 9 类驱动因子的覆盖缺口）、移动端解码器、
  Dashboard 真实简报渲染（替换"尚未接入"占位卡）、13 席顾问会诊手机端接线与渲染、
  顾问调整单一口径、v3 参与结构真实渲染、真实模式搜索文案去演示化、±3 封顶跨语言契约测试。
- **量化基础计划**（`docs/superpowers/plans/2026-08-15-quant-foundations-plain-language.md`，12 任务全完成）：
  广度引擎 `breadth-v1`、板块相对强度 `sector-rs-v1`、时段化相对成交量 `rvol-tod-v1`、
  Parkinson/Garman-Klass 波动率 `range-vol-v1`、形态检测引擎 `patterns-shapes-v1`
  （顶/底分型、W底/双头、头肩顶/底、回踩五日线企稳）、白话词汇层 + `PlainReadingCard` 三层解读、
  神奇九转白话解读、MACD/RSI 版本化序列上图、机构资金因子接线（估算代理 0.5 置信 + 披露趋势，PIT 边界）、
  服务端文案中文化 + 完整性闸门、方法论文档。
- **本轮评审的 4 个修复代理**已收口：形态引擎 PIT 重放不变量（已解决的形态不得被全历史重算抹掉）、
  形态因子"仅在有效期内投票"+ 版本号升 v2 并披露、README 谎言修正（+ 路由白名单机械钉死）、
  简报缓存失败重试 TTL / 单飞不持锁 / 有效样本量诚实、跨语言快照契约 fixture。

### 尚未完成（按 roadmap 阶段）

- **阶段 4 剩余**：workspace 级包安装机制（消灭拼 PYTHONPATH 的脆弱态）、
  快照请求连接复用与节流（每次 v3 快照仍建 4 条 OpenD 连接）、2026-07-24 旧交接文档仍停在 Task 5。
- **阶段 5 剩余**：`risk_preference` 参数在 HTTP 层不可达（service 签名接受，`http_app` 不解析，
  所以所有 riskPlan 恒为 balanced）。
- **阶段 6 剩余（投入产出比最高）**：补齐权威源适配器——见下节 roadmap。
- **阶段 7 剩余**：补充调查（`申请补充调查`）受理端点、共识/最大分歧结构、顾问 taxonomy 决策。
- **阶段 8 剩余**：十字光标拖拽、水平价格线、横屏、复权切换、绘图工具、VWAP/MA10/MA20、
  可选子图与筹码分布、孤儿组件接线或删除、暗色模式与双主题体系合并、全市场 symbol 搜索。
- **阶段 9**：新加坡云端部署（deploy kit 与设备配对链已就绪但**未上机**）、TestFlight/Release 门。
- **阶段 10**：校准与自适应学习闭环——解锁提醒系统、候选雷达、Agent 对话三块演示面。

---

## 六、Roadmap：接下来按这个顺序做

> 每一项都以 TDD 推进，落地后跑客观评审，并在模拟器里眼见为实。

### R1 · 阶段 6 权威源适配器（**优先级最高**）

**为什么第一**：App 现在每只股票都显示"不可行动 · 证据不足"，因为真实证据源只有
SEC 8-K/Form 4 当期 feed + 财政部收益率曲线。评分门槛不是太严，是**眼睛太少**。
这一项直接决定用户能否看到有意义的结论。

- SEC 覆盖扩展：10-Q / 10-K / 13D / 13G、公司范围 feeds（现在只有 8-K + Form 4 当期流）
- SEC 申报正文抓取（现在只有标题，所以申报情绪结构性不可测——Atom feed 不含正文）
- 公司 IR 适配器泛化（现在硬编码 Apple + NVIDIA 两家）
- 停牌 / FINRA / FDA / FTC-DOJ / OFAC / 地缘政治源（`geopolitical_mappings` 管道在，没有源配置它）
- 协调器快照持久化**接线**（机制已实现但生产装配没用上：`evidence_provider` 每次新建
  内存 `PollingCoordinator`，重启仍会把 feed 里还在的每条当新闻重播）
- 新闻 wire 留空是**故意的**（等商业授权），不要为了填坑去抓未授权源

### R2 · 每股 RVOL 与范围波动率上屏

词汇层与算法都已就绪（`rvol.py`、`volatility.py`、`plain_language.py`），
缺的是把它们塞进 per-symbol decision 载荷并在个股页用 `PlainReadingCard` 渲染。
这是量化计划 Task 5 明确留下的后续。RVOL 会给"等待量价确认"一个真正的数字定义。

### R3 · 阶段 4 债务清算

workspace 级包安装（`pyproject` workspace 或 uv），把 PYTHONPATH 拼接从 launchd 规格、
smoke_live、部署 env、每个 README 里彻底移除；OpenD 连接复用与节流。
**这条越晚做越贵**——真实使用越多，moomoo 配额风险越高。

### R4 · 阶段 7 收尾

补充调查受理端点（现在两个按钮都只改本地 state，没有受理方）、共识/最大分歧结构化输出、
以及**需要 Franz 拍板的产品决策**：顾问用"13 位具名投资人风格"（演示模式现状）
还是"去品牌化框架"（真实 `adviser_llm` 现状，短线 7 席 / 波段 12 席 / 长线 9 席）。

### R5 · 阶段 8 图表与 UI 收口

按用户价值排序：十字光标拖拽（需要手势仲裁，单指现在归平移）→ 横屏
（`expo-screen-orientation` 已装未接线，几何已支持 1180 宽）→ 复权切换
（现在硬编码前复权 QFQ，需服务端参数 + UI）→ 暗色模式（`userInterfaceStyle: light` 硬关，
`RootLayout` 的 DarkTheme 分支和 `newsPalette` 暗色板都是死代码）→ 孤儿组件清理。

### R6 · 阶段 9 云端部署

deploy kit（Caddyfile、systemd、bootstrap/preflight、4 个部署测试文件）和设备配对链
（哈希单次码、SQLite、即时吊销、iOS Keychain）都已就绪且有测试，但**没有任何主机真的部署过**。
runbook 自己承认的缺口：设备令牌不过期、读路径无边缘限速、loopback 网关无认证、
无自动升级、无告警、加密备份与推送未处理。

### R7 · 阶段 10 校准闭环（解锁最后三块演示面）

- **保形预测（conformal prediction）做预测带校准**——`CalibrationStatus` 现在永远是
  `UNCALIBRATED`，设计规定校准通过前不显示概率带。保形方法无分布假设、用历史残差分位数
  直接给出诚实覆盖率，比 Brier 更容易先落地，且与"预测区间不是保证"的产品哲学天然一致。
- **walk-forward 回测引擎**——给九转/神龙/形态挂上真实命中率，替换现在所有形态解读末尾的
  "历史胜率待回测"。
- **事件研究引擎**——对每类事件统计 T+1/T+5 超额收益分布 + 样本量（等 R1 数据源变宽后统计力才够）。
- 随后：常驻扫描服务 → **提醒 tab**；全市场 screener → **发现 tab 候选雷达**；
  会话服务（六段式：客观结论/证据/最强反证/缺失信息/风险场景/引用）→ **Agent tab**。
  这三块是演示模式里唯一还没有真实对应物的界面。

---

## 七、反复咬人的坑（历史教训，全部有代价）

1. **截止时间必须在全部取数完成后采样。** 曾经 `as_of` 在拉 K 线后、拉证据前定格，
   于是"用户看到新闻才来查"的那次请求必然看不到该新闻，还照常发出满权重的中性结论。
2. **类型上不可为 None 的字段就不可能诚实降级。** 给因子加"不可用"通道时，
   要证明生产路径**真的能**产出 None，否则通道只是装饰。
3. **每条修复要验证到装配层。** 函数被测试调用 ≠ 被产品调用。历史上三次：
   CIK 登记表没传给生产装配、吊销回路无人调用、13 席会诊屏无入口。
4. **一条发现的每个半场都要修完。** 锁只锁一半、重锚定只覆盖换标的场景，都会在复审里被重新打开。
5. **fixture 不得使用线上不可能出现的形状。** MACD 解码器曾期待一个网关从未发送过的嵌套结构，
   而 fixture 与解码器"自洽地共同错误"，全绿了三天。现在有跨语言契约 fixture
   （`services/market_gateway/tests/fixtures/contract_snapshot_v3.json`，Python 生成 + 字节钉死，
   移动端读同一份 JSON 解码）堵住这个洞——**新增 wire 字段时要重新生成它**。
6. **默认值不得填充恰好让校验通过的那个值**；异常分类不要用字符串匹配。
7. **文档说谎是红线。** README 声称"分析服务不读 /v3/stock-snapshot"在机构资金接线后变成假话，
   已被机械钉死的测试捕获。改行为就改文档，同一个提交。

---

## 八、需要 Franz 决定的事（agent 不要替他决定）

1. **顾问 taxonomy**：具名投资人 vs 去品牌化框架（见 R4）。
2. **广度/RS 的股票池**：现在默认回退到他的 46 只自选（标签诚实写作 `自选广度（46 只）`），
   板块 RS 需要配置 `ANALYSIS_API_SECTOR_RS_SYMBOLS` / `_BENCHMARK` 才会出值。
   要不要买/配一个更宽的池子是产品决策。
3. **云端部署的时机与主机**（阶段 9），以及是否走 TestFlight。
4. **新闻 wire 商业授权**是否采购（影响 R1 的情绪因子上限）。

不可逆动作（推送到别人的分支、删除、对外发送、花钱的模型调用扩量）在他不在场时不要自作主张。
13 席会诊每次约 $0.10，只在用户显式点击时调用，**永不批量**。
