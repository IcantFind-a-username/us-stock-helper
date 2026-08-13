# adviser_llm — LLM 顾问层

跨源解释与投资影响分析。这一层是**出站调用方，不是服务**：它不监听任何端口，
只用官方 `anthropic` SDK 向 Messages API 发请求。

它也是仓库里唯一带第三方依赖的包（`anthropic` + `pydantic`）。其他服务保持纯标准库；
这里破例，是因为官方 SDK 才是访问该 API 的正确方式，手写 HTTP 需要自行重造
重试、流式与结构化输出解析，且拿不到厂商的兼容保证。

## 模型只做三件事

跨源解释、反证分析、自然语言建议。情绪打分、语义聚类、CIK 归属留在
`information_layer` 的确定性可回测代码里，**不经过模型**；顾问观点到分数的
数值映射也在 `gating.py` 用代码完成，模型只给出 `stance` 与三档 `confidence`。

## 可溯源是 schema 级的约束

`Conclusion.citations` 必填且非空（JSON Schema 里落成 `minItems: 1`），
所以"没有出处的结论"在语法层面就构造不出来。落地后还有两道校验：

1. `evidence_id` 必须命中冻结证据包，否则整份输出拒绝，不做部分展示；
2. `quote` 必须是被引条目原文的逐字片段，且结论正文里不得出现证据之外的
   数字与标的缩写，否则判为编造。

原始链接由系统按 `evidence_id` 从证据包解析——模型写的链接一律丢弃，
因为伪造的 URL 和真实的 URL 长得一模一样。

## 时效性

每条证据同时携带 `available_at`（发布时刻）与 `received_at`（接收时刻），
两者都必须带时区，都不允许用当前时间兜底；证据包按 `available_at` 排序，
晚于 `as_of` 的条目直接剔除。解析后的引用把这两个时刻一起带给上层展示。

## 失败与降级

- API key 只从环境变量读取（默认 `ANTHROPIC_API_KEY`），未配置时抛
  `MissingCredentialError` 并指名变量名；key 不进配置对象、不进日志、不进仓库。
- 重试上限 1..5 次，指数退避；只重试超时/连接/限流/5xx，被拒的请求不重试。
  SDK 自带的重试被关闭，避免两层循环把真实故障拖成长时间挂起。
- 模型不可用时返回 `AdviserOutcome(value=None, unavailable_reason=...)`，
  **绝不返回中性观点**——"够不到模型"和"看过了没意见"是两个不同的结论。

## 顾问席位

13 个分析框架（价值/成长/宏观/地缘/技术/量化/风控/逆向/质量/催化/流动性/
尾部风险/产业链），每个写明方法论与已知盲区；按周期挑选适配的席位出场
（swing 12 席、long 9 席、short 7 席）。顾问观点是建议不是指令：调整幅度受
`us_stock_helper_core.ADVISER_SCORE_CAP` 约束，任一硬门未通过时一律清零且不可执行。

## 验证

```bash
cd services/adviser_llm
PYTHONPATH="src:../information_layer:../analysis_core" python3 -m pytest -q
```

测试全部使用 mock 的 Anthropic client，不发真实请求。
