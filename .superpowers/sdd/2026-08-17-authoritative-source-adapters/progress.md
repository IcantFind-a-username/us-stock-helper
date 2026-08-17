# 台账：权威源适配器（2026-08-17）

规格：`docs/superpowers/plans/2026-08-17-authoritative-source-adapters.md`

## 开工基线（2026-08-17 00:36 +0800）

- Python 全部套件绿（analysis_core / information_layer / adviser_layer / decision_engine /
  market_gateway / device_auth / analysis_api / scripts 均 OK；adviser_llm 122 passed）。
- 移动端 982 passed / 1 skipped，`npm run typecheck` 干净。与交接文档基线一致。
- 服务栈四组件 running（market-loopback 8765 / market-lan 8766 / analysis-api 8770 / metro 8088）。
- 模拟器验收：iPhone 17 Pro Max（Booted），深链接打开后看到 VCX 个股页真实模式
  （"实时只读"，日 K + MACD + 神奇九转 + 参与结构，截止 2026-08-15）。
  截图 `/tmp/app_baseline.png`。

## Task 1 · Step 1：EDGAR 表格代码调研（完成）

**抓取方式**：curl，User-Agent = `us-stock-helper/0.1 (orchestragent@gmail.com)`
（联系邮箱取自 `~/.us-stock-helper/lan.env` 的 `US_STOCK_HELPER_CONTACT_EMAIL`），
URL 与 `SecCurrentFilingsAdapter` 生产构造完全一致
（`browse-edgar?action=getcurrent&type=<form>&…&output=atom`），仅 `count=40`（生产为 100，
只影响条数不影响形状）。每次请求间隔 ≥1s。抓取时间 2026-08-16 12:41 EDT（周日）。

**礼貌性核查**：www.sec.gov 是既有已注册主机（8-K、Form 4 已在池内），非新增主机。
EDGAR 公平访问政策（`sec.gov/os/accessing-edgar-data`）要求声明式 User-Agent（App/版本 + 联系邮箱）、
≤10 请求/秒；本项目 UA 合规、单源轮询间隔 300s，远低于上限。robots.txt 未禁止 `cgi-bin/browse-edgar`。

**各 `type=` 实际返回**（样本已存 `services/information_layer/tests/fixtures/`）：

| 请求的 type= | 返回 | 实际表格分布（样本 40 条） | fixture |
|---|---|---|---|
| `10-Q` | 40 条 | 10-Q ×38、10-Q/A ×2；角色全部 (Filer) | `sec_current_10q.atom` |
| `10-K` | 25 条 | 10-K ×21、10-K/A ×4；角色全部 (Filer) | `sec_current_10k.atom` |
| `SC 13D` | **0 条**（"No recent filings"） | — | `sec_current_sc_13d_empty.atom` |
| `SC 13G` | **0 条**（"No recent filings"） | — | `sec_current_sc_13g_empty.atom` |
| `SCHEDULE 13D` | 40 条 | SCHEDULE 13D ×10、SCHEDULE 13D/A ×30 | `sec_current_schedule_13d.atom` |
| `SCHEDULE 13G` | 40 条 | SCHEDULE 13G ×36、SCHEDULE 13G/A ×4 | `sec_current_schedule_13g.atom` |

**结论：规格假设不成立，以 fixture 为准。** 受益所有权申报的现行代码是
`SCHEDULE 13D` / `SCHEDULE 13G`（EDGAR 2024 年改版后启用），`SC 13D`/`SC 13G` 是死代码。
注册的 SourceSpec 用 `SCHEDULE 13D` / `SCHEDULE 13G`。

**13D/13G 归属结构**（真实样本证据）：每份申报产生**成对条目**，共享同一 accession 与同一
Atom `<id>`：`(Filed by)`（持有人，标题与 URL 均为持有人 CIK）+ `(Subject)`（标的发行人，
标题与 URL 均为发行人 CIK）。样本 40 条 = 20 份申报 × 2。归属应给 **Subject（发行人）**；
Filed by 条目不得认领股票代码（持有人自身是上市公司时会重演 DaVita→Berkshire 误归属）。

**调研发现的现有代码缺口**（对着真实 fixture 跑 `SecCurrentFilingsAdapter` 实测确认）：

1. `_TITLE_FORM` 正则不认多词表格：`SCHEDULE 13D/A - …` 解析失败，`form_type` 属性
   回退为请求前缀 `SCHEDULE 13D`——修正案被错标为原件（违反"记录条目自称的表格"）。
2. `cik_registry._ROLE` 不认 `(Filed by)`：角色返回 None → `role_attributes_symbol(None)=True`
   → 持有人 CIK 若在注册表中会被误归属（1.0 相关度、VERIFIED、0.99 可靠度）。
3. `adapter_id` 由表格代码 casefold 生成：`SCHEDULE 13D` → `"sec-current-schedule 13d"`
   （含空格），且与 SourceSpec.source_id 的既有一致性约定
   （`test_every_declared_source_becomes_an_adapter_carrying_its_terms` 按 source_id 查 adapter_id）冲突。

以上三条均属"form-code check demands it"允许的 sec.py / cik_registry.py 修改范围
（cik_registry.py 不在规格 Task 1 文件清单里，但 13D/13G 归属断言强制触及角色逻辑，特此记录）。

**发现的既有缺陷（超出 Task 1 范围，不擅自修，上报 Franz）——协调器对双条目申报每轮重发**：
同一 claim key（`sec|<accession>`）在一个批次出现两次（Filed by + Subject），内容哈希不同，
协调器把第二条当第一条的"修订版"发布；下一轮又因存储哈希与首条不符而把两条**再次全部重发**
（rev 2、3、4… 无限互刷）。实测：同一 fixture 轮询两次，第二次仍发布全部 40 条。
影响：① 该类申报在回看窗口内每轮被重新宣布；② 重发事件带新的 `available_at`，
collector 按 event_id 覆盖后这些申报永远"看起来刚发生"、永不过期（PIT 诚实性受损）。
**Form 4（Reporting + Issuer 双条目）今天在生产中就有同样问题**，非本次新增所致。
claim key 共享是聚类的承重结构（同一申报聚成一簇 + 修订链让 Subject 条目胜出），
不能在 Task 1 局部改动；建议与 Task 4（快照持久化）一并定夺。

## 环境修复插曲（2026-08-17 01:11–01:18，非代码提交，纯本地配置）

Mac 换网导致 LAN IP 从 192.168.0.59 变为 10.100.252.18，模拟器 app 卡在
"Failed to load app from http://192.168.0.59:8088"。三层根因逐一修复：

1. **Metro 缓存旧 IP**：`launchctl kickstart -k …metro` 重启后 `metro_deep_link.py`
   输出新 IP（10.100.252.18 在脚本允许的 10/8 私网段内，校验通过）。
2. **`apps/mobile/.env`（未跟踪的本地配置）钉着旧 IP**：`EXPO_PUBLIC_MARKET_API_URL`
   / `EXPO_PUBLIC_ANALYSIS_API_URL` 由 192.168.0.59 改为 10.100.252.18，再次重启 Metro。
3. **服务端来源白名单挡新网段**（app 显示"网络受限·来源白名单"，具名原因正确工作）：
   `~/.us-stock-helper/lan.env` 的 `MOOMOO_GATEWAY_ALLOWED_CLIENTS` /
   `ANALYSIS_API_ALLOWED_CLIENTS` **追加** 10.100.252.0/24（保留旧网段 192.168.0.0/24，
   回原网络仍可用），`local_runtime.py reinstall` 重生成 plist。文件保持 0600。

修复后 Dashboard 显示真实市场简报（中性 · 真实数据 · 自选广度 46 只 59% 收于 50 日线上方）。
**遗留给 Franz**：换网后 `.env` 与白名单需要手动同步是个易踩的环境坑，
是否要一个"换网自愈"脚本（或把 app 端 URL 从 Metro hostUri 动态推导）值得拍板。

## Task 1 · Steps 2–5：RED → GREEN → 变异验证 → 验收 → 提交（完成）

**RED（先看到红）**：新增 `BeneficialOwnershipFormCodeTests` /
`QuarterlyAndAnnualReportFeedTests`（fixture 驱动，test_adapters.py）与
`WidenedSecCoverageTests`（test_source_registry.py）。首跑失败 6 处，原因全部与预期一致：

- `test_a_filed_by_entry_claims_no_symbol_even_when_the_holder_is_listed`：
  `(('URVN', 1.0),) != ()` —— Filed by 角色不被识别，持有人被误归属（13D）。
- `test_a_13g_subject_entry_is_attributed_to_the_issuer` 中的持有人断言：
  `(('PLRA', 1.0),) != ()` —— 同上（13G）。
- `test_a_multiword_form_builds_a_hyphenated_adapter_id`：
  `'sec-current-schedule 13d' != 'sec-current-schedule-13d'`。
- `test_an_amendment_carries_its_actual_form_not_the_requested_prefix`：
  form 集缺 `SCHEDULE 13D/A`（多词表格正则解析失败，回退为请求前缀）。
- `test_the_registry_polls_all_six_current_filing_forms`：注册表缺 4 种表格。
- `test_every_sec_source_shares_the_8k_terms`：`2 != 6`。

**GREEN 改动**：

- `sec.py`：`_TITLE_FORM` 支持多词表格（逐词、非贪婪、停在首个 " - "）；
  新增 `CURRENT_FILING_FORMS`（6 种表格的单一权威清单）与 `sec_current_source_id()`
  （空格→连字符）；adapter_id 改用该函数；工厂 `build_sec_current_filings_adapters`
  默认值改为 `CURRENT_FILING_FORMS`（Step 4 决定：保留工厂但与注册表共用一份清单，
  消灭两份清单；工厂仍被 README 示例与自身测试使用，不删）。
- `cik_registry.py`：`_ROLE` 增加 `filed by`；`role_attributes_symbol` 把
  `filed by` 加入不归属集合（与 `reporting` 同理，防持有人上市时的 DaVita 型误归属）。
  ——该文件不在规格 Task 1 文件清单内，但 13D/13G 归属断言必然触及角色逻辑，属规格
  "sec.py only if the form-code check demands it" 的同类必要修改，特此记录。
- `registry.py`：SEC 源改为按 `CURRENT_FILING_FORMS` 生成 6 条 `SourceSpec`
  （条款与 8-K 完全一致：0.99 / 300s / 联系式 UA / VERIFIED / 仅 www.sec.gov）。
- `feeds/__init__.py` 导出新名字；`services/information_layer/README.md` 源表格
  与工厂说明同步（同一提交，文档不说谎）。

**变异验证**（两处关键断言）：
① 把 `role_attributes_symbol` 反转回 `role != "reporting"` → 2 处测试红
（URVN/PLRA 误归属复现）；② 把 `_TITLE_FORM` 反转回单词版 → 修正案表格测试红。
两处均恢复后全绿。

**GREEN 结果**：information_layer 247 OK · analysis_api 273 OK · scripts 211 OK
（analysis_api 含 README 命令执行测试与路由白名单钉死测试）。
移动端无涉及文件（纯 Python 改动），基线 982/1 在开工时已确认。

**模拟器/服务端验收**（环境修复后）：
- Dashboard：真实市场简报渲染（中性 · 真实数据；自选广度 46 只，59% 收于 50 日线上方，
  +0.17；其余驱动因子按具名原因显示不可用）。截图 `/tmp/app_task1_dashboard3.png`。
- AAPL 个股页（深链接 `usstockhelper://stocks/AAPL`）：实时只读 $305.93，日 K/MACD/
  九转真实渲染。截图 `/tmp/app_task1_stock_aapl.png`。
- 服务端证据核查（`GET /decision?symbol=AAPL&horizon=short`，重启后的 analysis-api）：
  `citations = []`，notes 仅点名 geopolitics / institutional_flow 两个缺口，
  **无任何 sec-current-* 源失败** —— 六个 SEC feed（含四个新源）全部被成功轮询。
  **证据数没有移动的诚实解释**：验收发生在周日深夜（美东周日中午后），getcurrent
  6 小时回看窗口内 EDGAR 没有新申报；新源注册正确、轮询成功、窗口为空，
  属"不可用/为空就说为空"的预期行为。工作日窗口下 10-Q/10-K/13D/13G 事件将进入证据流。

**提交**：`8cfab6c` — feat: widen sec current-filings coverage to 10-Q, 10-K and schedule 13D/13G。

**遗留项**：协调器双条目重发缺陷（见上方"发现的既有缺陷"）待 Franz 定夺；
建议放进 Task 4 一并处理。

## Task 2 · 公司 IR 源泛化（完成）

**调研（先于代码，全部真实抓取验证，UA 同 Task 1，逐个间隔 ≥1s）**：
自选 46 只中的大市值候选逐一试探官方 newsroom/IR feed：

| 结果 | 明细 |
|---|---|
| ✅ 采纳 5 家 | MSFT `news.microsoft.com/feed/`（robots 全开）；INTC `newsroom.intel.com/feed`（robots 全开）；BA `boeing.mediaroom.com/news-releases-statements?pagetemplate=rss`（**无 robots.txt**，HTTP 404，按惯例不设限；该 URL 是 MediaRoom 平台自身的 RSS 分发模板）；AMZN `www.aboutamazon.com/news/rss`（robots 允许，Crawl-delay 10s ≪ 900s 轮询）；GOOGL `blog.google/rss/`（robots 仅禁 /search 路径） |
| ❌ 拒绝并记录 | MRK：`merck.com/feed/` 与 `/media/news/feed/` 均返回 200 但 **0 条目**（空壳 feed）；AMZN 旧地址 `press.aboutamazon.com/rss/news-releases.xml` 404；AMD `ir.amd.com/rss/press-releases.xml` 404、`www.amd.com/en/newsroom.rss` 连接失败；CSCO 两个候选 404；QCOM 两个候选 404；PYPL MediaRoom 模板返回 HTML 非 RSS；SONY 403 Access Denied；KO 404 |
| ⏸ 未键入 | GRAB / SOUN / COIN / RIOT / NIO / MO 等：代码与常见英文词同形（或无已验证 feed），在拿到"grab holdings"式多词键前不进表——测试 `IrKeywordHonestyTests` 把这条规则钉死 |

样本存 `tests/fixtures/ir_{microsoft_news,intel_newsroom,boeing_mediaroom,aboutamazon_news,google_blog}.rss`。
GOOGL 特殊性已记录：blog.google 是 Google（运营公司）的官方频道，上市主体是 Alphabet Inc.；
entity 键用 "Alphabet Inc."，关键词用 "google"/"googl"（"alphabet" 是常见词，不用）。

**RED**：`company_ir_source` 不存在 → test_source_registry 整文件 ImportError
（预期失败原因：构建器未实现）。新测试：`CompanyIrSourceBuilderTests`（行展开、
空 symbol/公司名/关键词拒绝、http 拒绝、host 不匹配拒绝、同 publisher 双行注册表拒绝）、
`IrKeywordHonestyTests`（真实演示 "grab" 动词误归属 + 钉死出货表无歧义常见词关键词）、
`ShippedIrCoverageTests`（7 家 newsroom 齐全、条款一致）、
`CompanyIrFeedFixtureTests`（真实 fixture：Boeing 标题含公司词 → ("BA",0.9)+VERIFIED；
Google 博客标题不点名公司 → 零归属——归属从文本挣得，不因频道假定）。

**GREEN**：`registry.py` 新增 `company_ir_source()` 构建器（0.95 / 900s / VERIFIED /
OFFICIAL_ANNOUNCEMENT；首关键词=公司词，挣得 entity 归属；构造期拒绝空行）；
Apple/NVIDIA 迁入同一张 `_COMPANY_IR_SOURCES` 表（source_id 与 mapping 逐字段保持不变，
`ShippedRegistryTests` 与既有 apple/nvidia 断言未动仍绿）；新增 5 行已验证 feed。
`feeds/__init__.py` 导出；README 源表格 +5 行并写明构建器规则。

**变异验证**：往 GOOGL 行塞入常见词关键词 "grab" →
`test_no_shipped_ir_keyword_is_an_ambiguous_common_word` 变红
（`'grab' unexpectedly found in frozenset`）。恢复后全绿。
（插曲：恢复变异时误用 `git checkout` 把未提交的 registry.py Task 2 改动一并回滚，
已重新应用并复跑全套件确认 258 绿——教训记录：变异恢复用编辑器反向替换，不用 checkout。）

**GREEN 结果**：information_layer 258 OK · analysis_api 273 OK · scripts 211 OK。

**模拟器/服务端验收**：MSFT 个股页真实渲染（$495.40 实时只读，日 K/MACD/九转），
截图 `/tmp/app_task2_stock_msft.png`。重启 analysis-api 后
`GET /decision?symbol=MSFT&horizon=short`：无任何源失败（16 个源全部轮询成功，
含 7 家 newsroom），citations 仍为空——周日 6 小时回看窗口内无新公告，诚实为空；
工作日窗口配合 MSFT/INTC/BA/AMZN/GOOGL 的公告将进入证据流。

**提交**：`abefa25` — feat: register verified company ir feeds。

## Task 3 · EDGAR 之外的监管/机构源（完成）

**调研（全部真实抓取 + robots 核查，2026-08-16/17）**：

| 结果 | 明细 |
|---|---|
| ✅ 采纳 4 个 | **Nasdaq 停牌** `www.nasdaqtrader.com/rss.aspx?feed=tradehalts`（无 robots.txt——请求 302 到"Page Not Available"；该 RSS 是 Nasdaq Trader 官方分发产品，feed 自声明 ttl=1 分钟，明示欢迎分钟级轮询）；**FDA 新闻稿** `www.fda.gov/...press-releases/rss.xml`（robots Crawl-Delay 30s ≪ 900s）；**FTC 新闻稿** `www.ftc.gov/feeds/press-release.xml`（robots Crawl-delay 5s）；**DOJ 新闻** `www.justice.gov/feeds/justice-news.xml`（robots Disallow 不含 /feeds） |
| ❌ 拒绝并记录 | **OFAC/财政部制裁源**：`ofac.treasury.gov/recent-actions/rss.xml`、`/system/files/rss/recent-actions.xml` 均 404，`home.treasury.gov` 新闻稿 RSS 404/302——OFAC 网站改版后不再提供 RSS/Atom 端点。**地缘政治驱动因子保持具名"尚未接入"**（规格 Step 3 要求"只在数据真实流动时接线"——没有源就不接）。NYSE 停牌只有 CSV 下载无 feed，未注册 |

样本存 `tests/fixtures/{nasdaq_trade_halts,fda_press_releases,ftc_press_releases,doj_justice_news}.rss`。

**真实样本暴露的三个事实（全部写进测试）**：
1. **Nasdaq 停牌条目没有 `<link>`/`<guid>`** → 通用解析器会全部丢弃 → 需要专用适配器
   （`feeds/nasdaq.py::NasdaqHaltsAdapter`）：按 `ndaq:IssueSymbol` 权威归属（1.0，
   等价于 CIK 精确匹配而非关键词猜测）、身份=代码+停牌日期+时间（复牌字段填充后
   同一 claim 以修订版发布）、停牌通告是元数据不打情绪分。`SourceSpec` 新增 `dialect`
   字段路由（未知 dialect 构造期拒绝）。
2. **FDA feed 的条目链接是 http://** → 通用解析器按"仅 https"把全部条目丢弃。
   修复：解析时把条目链接升级为同 URL 的 https 形式（引用不得给读者明文链接，
   而整条公告因链接 scheme 被丢弃是更大的损失），新增钉死测试。
3. **DOJ feed 真实携带未来日期条目**（"FY26 Q4 Data Due"，dated 2026-10-30，
   抓取时刻是 08-16）→ 用真实载荷钉死 PIT 未来条目拒收护栏
   （`future_entries_rejected ≥ 1`）。

**归属设计**：FDA/FTC/DOJ 是监管者对第三方公司的表述，不是发行人自有频道——
公司点名关键词用 **0.85** 相关度（发行人频道 0.9、CIK/交易所权威 1.0），
映射只含区分度足够的公司词（apple/amazon/google/…/taiwan semiconductor + tsmc；
FDA 另配 crispr therapeutics→CRSP、structure therapeutics→GPCR、merck→MRK）。
当前抓取的样本窗口内没有任何映射词命中（测试断言零虚构归属）。

**RED**：ImportError（`NasdaqHaltsAdapter` 不存在）×6 + KeyError
（`nasdaq-trade-halts` 等不在注册表）×3，原因全部符合预期。
其中 FDA fixture 解析测试在适配器/注册表就位后仍红（0 事件），暴露了上面第 2 条
http 链接问题——先红的测试真实抓到了一个规格没预见的缺陷。

**变异验证**：删除 `NasdaqHaltsAdapter._symbol_relevance` 的权威归属分支 →
`test_a_halt_names_its_ticker_reason_and_pit_stamps` 变红。恢复后全绿。

**GREEN 结果**：information_layer 268 OK · analysis_api 273 OK · scripts 211 OK ·
decision_engine 19 OK。

**验收**：重启 analysis-api 后 `GET /market-brief`：`sourceGaps: []`——
**20 个源（6 SEC + 3 宏观 + 7 newsroom + 4 机构）全部实时轮询成功零失败**；
`GET /decision?symbol=AAPL` notes 无任何源失败。Dashboard 真实简报渲染正常
（截图 `/tmp/app_task3_dashboard.png`）。citations 仍为空——周日窗口诚实为空；
停牌源上线后，自选股盘中停牌将以 1.0 相关度、VERIFIED 直达该股证据流。

**提交**：`801fb29` — feat: add verified regulatory and agency sources。

## Task 4 · 协调器快照持久化接线（完成）

**RED**（`test_evidence_provider.CoordinatorPersistenceTests`，4 个用例首跑 2 失败 + 1 错误，
原因全符预期）：
- `test_a_restart_does_not_reannounce_what_was_already_published`：两次
  `evidence_provider_from_environment()` 共享同一快照路径 + 每个 feed 都返回同一条目的
  假传输 → 第二次仍重发 3 个事件（`(EvidenceEvent(...)×3) != ()`）——缺陷本体。
- `test_the_snapshot_file_is_private_and_written_atomically`：无快照文件产生。
- `test_a_malformed_snapshot_is_rejected_whole_with_a_named_reason`：
  `coordinator_state` 模块不存在（ImportError）。
- scripts：`ANALYSIS_API_COORDINATOR_STATE` 未注入 analysis-api 环境 → 环境字典测试红。

**GREEN 改动**：
- `information_layer/feeds/collector.py`：`EvidenceCollector.coordinator` 只读访问器
  （information_layer 保持零文件 I/O，文件读写归 analysis_api——规格 Step 2 的取向）。
- 新文件 `analysis_api/.../coordinator_state.py`：`CoordinatorStateStore`——
  `load_coordinator()` 缺文件=正常首启；损坏文件**整体拒绝**并返回具名原因 + 全新协调器
  （沿用 `from_snapshot` 的不部分加载规则）；`save()` 原子写（同目录临时文件 + rename）、
  0600、目录 0700，失败返回具名原因但**不使当次请求失败**（崩溃降级为旧行为，不腐蚀状态）。
- `evidence_provider.py`：读 `ANALYSIS_API_COORDINATOR_STATE`，启动时恢复协调器
  （损坏原因 print 进 launchd 日志），每次证据扫描后保存；未配置路径时行为逐字节不变
  （测试钉死）。`__main__.py` 停机 finally 再保存一次。
- `scripts/local_runtime_support.py`：analysis-api 分支注入
  `~/.us-stock-helper/state/coordinator.json`（与 DEVICE_AUTH_DATABASE 同款）。
- `services/analysis_api/README.md` 环境变量表新增该行。

**变异验证**：把装配改回 `coordinator=None`（无视恢复的协调器）→ 重启重播测试变红。
恢复后 analysis_api 17/17 绿。

**GREEN 结果**：information_layer 268 OK · analysis_api 277 OK · scripts 211 OK。

**真实重启验证**：`local_runtime.py reinstall` 注入新环境变量 → `GET /decision` 200 后
`~/.us-stock-helper/state/coordinator.json` 出现（`-rw-------` 0600，3667 字节，
与 devices.sqlite3 同目录）→ `launchctl kickstart -k` 重启 → 第二次 `GET /decision` 200，
快照续写，日志无"malformed"具名原因（即恢复成功）。本任务无用户可见界面改动
（服务端状态持久化）；Dashboard 此前截图确认服务健康。

**行为语义说明（诚实披露）**：持久化后，重启进程不再把回看窗口内旧条目重新宣布为新证据
——同时意味着重启后的进程证据存量从零开始积累（旧条目不再重播即不再入库），
直到各 feed 出现新内容。这是规格明确要求的取向（重播被定义为缺陷：available_at
被刷新成"刚发生"，永不过期）。Franz 若希望"重启后立即恢复证据存量"，
需要另行持久化证据事件本身（超出本规格，见拍板事项）。

**提交**：`4ef2226` — fix: remember what each feed already published across restarts。

## Task 5 · 证据闸门重审（**未开工，顺延，原因如下**）

规格 Step 1 要求"先测量"：新源上线后统计 46 只自选的真实 `evidence_confidence` 分布。
本次会话在周日深夜（美东周日中午后），EDGAR getcurrent、各 newsroom、机构 feed 的
6 小时回看窗口全部为空——此时测量得到的是全零分布，正是规格自己警告的
"tuning a gate against a starved input"。**测量必须在美股交易日窗口内做**，
届时新源（尤其 10-Q/10-K/13D/13G 与停牌）有真实事件流。
顺延项：Step 1 测量 → Step 2 常量命名+边界钉死 → Step 3 视测量决定是否调值。

## Task 6 ·（可选）申报正文抓取：待 Franz 拍板后才动（见拍板事项）

## Task 7 · 方法论 / README / roadmap / 台账收口（完成）

- `docs/indicator-methodology.md` 新增 "Evidence sources" 一节：四类源的发布内容、
  节奏、归属规则与已知局限（13D/13G 双条目归属、IR 源自营宣传属性、停牌元数据、
  机构公告 0.85 第三方点名、DOJ 未来条目被 PIT 拒收、显式缺席的源与原因）。
- `services/information_layer/README.md` 与 `services/analysis_api/README.md`
  已在各任务提交内同步（源表格 +9 行、dialect 说明、`ANALYSIS_API_COORDINATOR_STATE`
  环境变量行）；`services/README.md` 无涉源清单表述，无需改动。
- `docs/roadmap-to-delivery.md` 阶段 6 "补齐权威源适配器" 勾选，附提交清单与未做项。

## 会话收口（2026-08-17 02:00 +0800）

**最终全量测试**：Python 八个包 unittest 全 OK + adviser_llm 122 passed；
移动端 982 passed / 1 skipped；`tsc --noEmit` 干净。与开工基线一致（本轮只增测试：
information_layer 247→268，analysis_api 273→277）。

**本轮提交**：`8cfab6c`（SEC 六表格）→ `abefa25`（IR 源表）→ `801fb29`（监管/机构源）
→ `4ef2226`（协调器快照持久化）→ 本提交（文档收口）。未 push，未建 PR。

**留给 Franz 拍板的事项**（主交接文档第八节 + 本轮新发现）：
1. （§八.1）顾问 taxonomy：具名投资人 vs 去品牌化框架。
2. （§八.2）广度/RS 股票池是否购买/配置更宽的池子。
3. （§八.3）云端部署时机与主机、是否走 TestFlight。
4. （§八.4）新闻 wire 商业授权是否采购。
5. （新）**协调器双条目重发缺陷**：Form 4 / 13D/13G 的成对条目共享 claim key，
   每轮轮询互刷为"修订版"重发且 available_at 被刷新（影响新鲜度诚实与 stale 标记）。
   claim key 共享是聚类的承重结构，修法需要设计取舍（如 claim key 加 CIK 维度 +
   聚类改用 accession 维度合并），建议专门排一个小计划。
6. （新）**重启后证据存量从零开始**：快照持久化按规格阻止重播，副作用是重启后
   决策的证据数暂时下降，直到 feed 出现新内容。若要"重启即恢复存量"，需另行
   持久化证据事件本身（新能力，需规格）。
7. （新）**申报正文抓取（Task 6）**：让申报情绪可测需对 EDGAR 的请求量显著上升
   （每份申报多一次正文抓取），是礼貌与封禁风险问题，规格明确要求先拍板。
8. （新）**换网环境自愈**：本轮换网导致 Metro 缓存旧 IP + `apps/mobile/.env` 钉旧 IP +
   服务端白名单挡新网段三层连环故障（已手工修复，均为本地未跟踪配置）。
   是否要一个"换网自愈"脚本或把 app 端 URL 从 Metro hostUri 动态推导，值得决定。
9. （新）**证据闸门测量（Task 5）**：需在美股交易日窗口内做，周末测量是饥饿输入。

**下一步建议**：工作日盘中做 Task 5 的 evidence_confidence 分布测量（46 只自选），
再决定 0.35 阈值去留；顺手在真实事件流下复核停牌/13D 源的端到端表现。

## 续轮（2026-08-17 02:06–02:20 +0800）：Franz 指示"继续开发"，拍板事项全部保持挂起

执行顺序按 Franz 建议（1 计划文档 → 2 测量准备 → 3 边角补齐），未发现更优顺序。

### ① 双条目重发缺陷专项计划（仅计划，不实现）

文档：`docs/superpowers/plans/2026-08-17-dual-entry-filing-reannouncement.md`。
内容：复现证据（同一 fixture 两轮均发布 40 条、修订号 2/3 互刷）、两类伤害
（available_at 被刷新导致永不过期 + 无界假修订链）、claim key 共享的承重分析
（聚类按 claim key 合簇 + 修订链取代恰好让带归属的 Subject 条目当代表）、
三个候选修法（A 按方 claim key + 聚类按 accession 合簇【推荐】；B 协调器多哈希
记录【无法区分"同时的双方"与"随时间的修订"，否决】；C 适配器丢弃非归属方条目
【丢可追溯性且改已钉死行为，否决】）、最小改动路径（4 个任务，先红后绿）、测试策略。
**起草中核实的新事实**：`_representative_sort_key` 并不偏好带归属的事件
（按状态/修订号/可靠度/置信度/时间/event_id 排序）——今天 Subject 胜出纯靠
修订链取代这个副作用；键拆分后该函数必须显式增加"带归属"优先级（计划已写明，
这是全案唯一触碰评分相邻语义的点）。

### ② Task 5 一键测量脚本（测量准备，不改阈值）

脚本：`.superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py`。
原理：进程内搭建与 `analysis_api.__main__` 完全相同的 provider 栈，
对 `decision_engine.engine.extract_horizon_features` 打记录补丁，逐股跑真实
`service.decision()`，捕获评分器真正看到的 `evidence_confidence`（HTTP 载荷不含此值）
——零重实现，数值不可能与生产漂移。**状态诚实**：故意不设
`ANALYSIS_API_COORDINATOR_STATE`（全新内存协调器=完整回看窗口视角，
且绝不触碰生产快照文件）。

**与规格的偏差（记录）**：规格 Task 5 Step 1 说测量脚本是"/tmp 下的一次性脚本，
不入库"。Franz 本轮明确要求"可一键执行 + 使用说明"，故持久化在台账目录
（非 scripts/ 工具目录，git add -f 入库），偏差原因即此指令。

**RED→GREEN**：`summarize()` 先以 NotImplementedError 落地，`--self-test` 首跑红
（NotImplementedError）→ 实现后绿。**变异验证**：把闸门边界 `>=` 改成 `>` →
自检红（`clears_gate 1 != 2`，钉死"0.35 本身算通过、闸门严格小于才触发"）→ 恢复绿。
**真实烟测**（`--limit 3`）：时段外警告正确弹出；SOFI/CRCL 测得 0.000（周日窗口
诚实为空）；VCX 因首轮扫描一个瞬时网络失败（sec-current-10-q 无法连接）被记为
"未测量"而非记 0——仪器不把"没测到"伪装成"测得零"。报告样例 `/tmp/gate_smoke.md`。

**周一使用方法**（美股盘中 21:30–04:00 北京时间，服务栈开着即可）：
```
cd /Users/franz/Documents/stock_trader/.worktrees/iphone-demo
python3 .superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py \
  --horizon short --out /tmp/gate_measurement.md
```
可选 `--limit N` 烟测、`--self-test` 免网络自检；瞬时"未测量"的股票重跑一次即可。
产出 markdown 表（逐股 confidence/引用数/是否触闸）+ 分布摘要（含 ≥0.35 通过数），
直接贴进台账即可完成 Task 5 Step 1。

### ③ 规格边角补齐（Task 1/3 的验收缺口）

- **FTC 正向归属用例**：抓取窗口内没有任何条目点名映射公司，正向归属此前未被
  fixture 证明。按 Berkshire 测试的既有风格，把真实标题里的 Grubhub 换成 Qualcomm
  → 断言 `("QCOM", 0.85)` 归属（第三方点名 0.85 的锚点也被钉死）。
  **变异验证**：从注册表移除 QCOM 映射 → 测试红（named 事件零归属）→ 恢复绿，
  registry.py 与提交版本零差异。
- **13G 修正案表格钉死**：13D fixture 已覆盖多词表格 /A 解析，13G 走同一路径但
  未被自己的载荷钉住；补 `test_a_13g_amendment_carries_its_actual_form_too`
  （forms == {SCHEDULE 13G, SCHEDULE 13G/A}）。两个测试为钉死性质（落地即绿），
  RED 纪律由各自的变异验证承担。

**GREEN 结果**：information_layer 270 OK（268→270）。

**本轮提交**：`9c023e6`（专项计划文档）→ `58bf763`（补齐测试）→
`540b0a8`（测量脚本）。无用户可见改动（纯文档/测试/测量工具），无需模拟器截图；
模拟器与服务栈保持上一轮末尾的健康状态。

**新发现的拍板事项**：无新增；专项计划文档本身就是拍板材料（推荐路径 A）。


## 续轮（2026-08-17）：双条目重发缺陷修复（专项计划路径 A，Franz 已批准继续开发）

按 `docs/superpowers/plans/2026-08-17-dual-entry-filing-reannouncement.md` 的
Option A 四任务实施，全程 fixture 驱动（`sec_current_schedule_13d.atom`，真实抓取样本）。

**RED（先看到红，与计划预测逐字吻合）**：

- `test_an_unchanged_feed_publishes_nothing_on_the_second_poll`：
  第二轮轮询同一 body 发布了全部 40 条，修订号列表
  `[2, 3, 2, 3, …] != []` —— 计划预测的互刷链原样复现。
- `test_an_unchanged_filing_keeps_its_available_at_and_goes_stale`：
  第二轮后存量事件 `available_at` 从 17:00 被刷新为 23:00 UTC，
  `stale` 永不触发（PIT 诚实性受损的直接钉死）。
- Task 3 RED（claim key 拆分后、聚类补偿前）：`40 != 20`（一份申报裂成两簇）；
  代表评选两处 `'z-unattributed' != 'a-attributed'`（成对条目在状态/修订/可靠度/
  置信度/时间全部并列，旧 event-id 字典序把无归属方选为代表）。

**GREEN 改动**：

- `feeds/sec.py` `_claim_key`：`sec|{accession}|{党方CIK}`（标题优先取条目自身 CIK；
  无 CIK 回退角色字符串；两者皆无回退旧键；无 accession 走通用键）。每方条目
  只与自己比对哈希，互刷终止；同方真实修订仍按同键正常走修订链。
- `clustering.py` `_cluster_events`：第三张 owners 映射（`accession_owner`），
  共享 `accession` 属性的事件合入一簇（仅 SEC 适配器发该属性，accession 全局唯一）。
- `clustering.py` `_representative_sort_key`：新增"带股票归属"档位，
  位于所有编辑性档位（状态/修订号/可靠度/置信度）之下、时间/event-id 决胜之上
  ——全案唯一触碰评分相邻语义的点，位置本身被测试显式钉死
  （`test_attribution_outranks_recency` + 三个"不越权"钉：不压状态/可靠度/修订号）。

**变异验证（三处，全部见红后恢复）**：

1. 把 `_claim_key` revert 回 `sec|{accession}` → 3 红（互刷 40 条复现、
   available_at 被刷新、快照兼容测试 `4 != 0`）。
2. 删除 accession 合簇 → `40 != 20` 红。
3. 删除"带归属"档位 → 3 红（fixture 代表测试 `fdfa… != 1261…`：无归属的
   Filed-by 条目重新当代表；两个合成代表测试同红）。

**快照兼容（部署路径钉死）**：手工构造旧格式快照（`sec|{accession}` 键、
真实内容哈希、修订号停在互刷中段的 3）→ `from_snapshot` 正常加载（键是不透明
字符串）；恢复后首轮把窗口内每个条目**作为全新 claim（revision 0，无 revision_of）
重发一次**，第二轮归零。测试：
`test_an_old_format_snapshot_causes_one_bounded_reannouncement`。

**GREEN 结果**：information_layer 280 OK（270→280，+10 测试）·
decision_engine 19 OK · analysis_api 277 OK · scripts 211 OK。

**提交**：`ead0bd7` — fix: stop republishing multi-party filings as fake revisions
（仅 4 个文件：sec.py / clustering.py / test_adapters.py / test_semantic_clustering.py）。

**部署须知（一次性有界重播，计划已预告）**：生产协调器快照持有旧格式 claim key
（以及由旧键派生的 event_id）。部署本修复后的**第一轮轮询**会把回看窗口内的每个
在场条目按新键重新宣布一次（revision 0 的全新 claim，不接旧修订链），此后恢复安静。
这是有界的一次性重播，与此前每轮无限互刷相对；已用快照兼容测试钉死上界。
计划 Task 4 中的"对运行栈的双重启实测"属部署时验证，本轮未运行生产栈，留待
下次启动服务栈时顺手确认（观察首轮日志一次重播、次轮归零即可）。

**未触碰**：证据闸门阈值（Task 5 需交易日测量）、移动端、roadmap 文档。
