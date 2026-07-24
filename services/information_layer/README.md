# Information Layer

这是 US Stock Helper 的“消息进入算法之前”证据层。当前目录只实现可测试的标准库核心，不联网、不放演示新闻、不声称拥有实时数据。

## 安全边界

- 每条 `EvidenceEvent` 同时保存事件、发布、首次发现、可用、抓取和修订时间。
- `EvidencePacketBuilder` 以 `as_of` 为硬截止；截止后才首次发现、可用、抓取或修订的记录不会进入证据包。
- 原文、转载和同集团来源用 provenance 归并；转载不能虚增独立来源数。
- 修订不覆盖历史，证据包指向截止时可见的最新修订，并保留修订链。
- 冲突来源全部保留，市场情绪同时列出证据、反证和不确定性。
- 传闻可以进入观察视图，但不参与 `action_score`，因此不能单独或混入已报道事件后触发行动信号。
- watchlist 只允许改变读取优先级，不能增加相关性、置信度或涨跌分。
- `EvidencePacket` 及其嵌套对象不可变，`version_id` 可复算；引用包含 URL、时间和内容哈希。
- `compact_render` 优先保留结论和引用，在给定的保守 token 估算预算内输出。

## 结构

- `adapter.py`：生产数据源需要实现的 `SourceAdapter` Protocol；核心不拥有网络副作用。
- `models.py`：不可变事件、来源、聚类、引用、情绪、调查请求和证据包模型。
- `clustering.py`：精确内容去重、主张聚类、修订、独立来源以及可信度/新鲜度。
- `sentiment.py`：事实与传闻隔离后的市场情绪、反证、不确定性和补充调查。
- `pipeline.py`：点时过滤、引用、版本化以及上述模块的无副作用编排。
- `compact.py`：面向大模型的紧凑证据包渲染，减少重复上下文。
- `feeds/http.py`：HTTPS-only、精确 host allowlist、无凭证重定向校验、超时和响应字节上限。
- `feeds/generic.py`：可配置 RSS/Atom、条件请求、短摘要、关键词相关性和退避元数据。
- `feeds/sec.py`：SEC EDGAR Current Filings Atom 配置，按表单拆分并保留 accession。
- `feeds/coordinator.py`：ETag/Last-Modified 状态、内容哈希去重和修订发布。

## 生产适配器优先级

优先级不是“越快越可信”，而是决定确认权重和补充调查顺序：

1. **SEC / EDGAR**：公司申报、8-K、10-Q、10-K、Form 4。保存 accession、原始文件 URL、接受时间和修订关系。
2. **公司 IR**：新闻稿、财报材料、电话会文字稿。必须标为公司自述，不能当成独立第三方验证。
3. **交易所与监管机构**：停牌、合规、执法、宏观和公共安全原始公告。
4. **政府与国际组织**：财政、货币、劳工、贸易、制裁和地缘事件的原始发布。
5. **持牌新闻数据源**：用于速度、上下文和跨区域覆盖；转载须携带原始通讯社标识。
6. **社交媒体/论坛**：只进入 `rumor` 观察队列，必须申请原始材料或权威来源复核，不能直接触发交易建议。

公司、政府和新闻源之间仍可能存在利益、口径和时间差异，因此来源层级不会自动消除反证。

## 合规与采集边界

- 优先使用官方 API、RSS、公开数据下载或已购买许可的数据产品；遵守授权地域、展示、存储和再分发条款。
- 不绕过登录、付费墙、验证码、反爬或技术访问控制。
- 抓取前读取并遵守站点服务条款与 `robots.txt`；`robots.txt` 不是版权许可，允许抓取也不等于允许再发布。
- 每个域名使用独立限速、指数退避、`Retry-After`、并发上限和熔断；缓存 ETag / Last-Modified，避免重复请求。
- 应保存事实字段、短摘录、内容哈希和原文链接；不要长期存储或向用户重发未经许可的全文。
- 删除、更正和撤稿必须形成新修订事件，不能静默改写历史。
- API 密钥、会话 cookie 和供应商凭证只能保存在服务端密钥管理中，不能进入 iOS 包、日志或证据引用。

## 配置公开 RSS / Atom

以下代码会真实发起网络请求；测试不会运行它。`robots_allowed=True` 不是自动探测，而是调用方确认该公开 feed 的站点条款与 robots 策略允许访问后的显式证明。若没有完成确认，保留默认 `False`，构造器会拒绝运行。

```python
import os
from datetime import datetime, timedelta, timezone

from information_layer.feeds import (
    FeedConfig,
    GenericFeedAdapter,
    KeywordMapping,
    PollingCoordinator,
    UrllibHttpsTransport,
)

adapter = GenericFeedAdapter(
    FeedConfig(
        adapter_id="licensed-news-feed",
        feed_url=os.environ["NEWS_FEED_URL"],
        allowed_hosts=(os.environ["NEWS_FEED_ALLOWED_HOST"],),
        publisher_id="licensed-news",
        publisher_name="Licensed News",
        source_type="news",
        reliability=0.8,
        user_agent=os.environ["PUBLIC_FEED_USER_AGENT"],
        robots_allowed=True,
        minimum_poll_interval_seconds=60,
        symbol_mappings=(
            KeywordMapping("NVDA", ("NVIDIA", "NVDA"), 0.95),
        ),
        entity_mappings=(
            KeywordMapping("NVIDIA", ("NVIDIA",), 0.9),
        ),
    ),
    UrllibHttpsTransport(),
)
coordinator = PollingCoordinator()
now = datetime.now(timezone.utc)
result = coordinator.poll(
    adapter,
    since=now - timedelta(minutes=10),
    until=now,
)
print(result.events)
print(result.metadata.recommended_delay_seconds)
```

适配器只保留标题、受 `summary_max_chars` 限制的纯文本短摘要、原文 HTTPS URL、内容哈希和时间/来源字段，不保存 feed 中的全文。HTTP 301/302 等重定向后的目标仍须位于同一个精确 allowlist；Cookie、Authorization 与代理凭证会被拒绝。

调用方必须等待至少 `recommended_delay_seconds` 后再轮询。该值始终不小于源配置的最小轮询间隔；429/5xx 时还会合并 `Retry-After` 和有上限的指数退避。协调器不会自行 `sleep`，方便服务端任务调度器持久化并统一执行限速。

## 配置 SEC Current Filings

SEC 要求自动化工具声明应用和联系方式。工厂为每个表单建立独立 Atom feed，默认支持 8-K 与 Form 4：

```python
import os

from information_layer.feeds import (
    UrllibHttpsTransport,
    build_sec_current_filings_adapters,
)

sec_adapters = build_sec_current_filings_adapters(
    transport=UrllibHttpsTransport(),
    user_agent=os.environ["SEC_USER_AGENT"],
    forms=("8-K", "4"),
)
```

SEC adapter 默认最小轮询间隔为 1 秒。SEC 官方当前公平访问上限为全部机器合计不超过每秒 10 个请求；生产调度仍应把所有 SEC adapter 合并限速，并遵守返回的 `Retry-After`。参考 [SEC Developer Resources](https://www.sec.gov/about/developer-resources) 与 [SEC RSS Feeds](https://www.sec.gov/about/rss-feeds)。

`PollingCoordinator` 在进程生命周期内保存条件请求和发布记录：304 不发布、相同 claim/content hash 不重发，内容改变则形成带 `revision_of` 的修订事件。生产部署需要把同样的 validators 与已发布 hash 状态持久化，才能在进程重启后继续去重。

## 运行测试

```bash
cd services/information_layer
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

测试使用构造的最小事件验证算法不变量，不代表实时市场数据。
