# EasySQL Langfuse Evaluation Resources

## Knowledge

- [Prometheus: Overview](https://prometheus.io/docs/introduction/overview/)
  官方架构总览：数值时间序列、labels、pull scrape、PromQL、recording/alerting rules、Alertmanager 与可视化集成。用于划分 Prometheus 的工程职责边界。
- [Prometheus: Metric Types](https://prometheus.io/docs/concepts/metric_types/)
  Counter、Gauge、Histogram 与 Summary 的官方定义。用于选择审核量、队列深度和延迟等指标类型。
- [Prometheus: Instrumentation](https://prometheus.io/docs/practices/instrumentation/)
  在线服务的请求数、错误和延迟等推荐指标，以及何时计数的实践。用于设计文档审核服务最小指标集。
- [Prometheus: Metric and Label Naming](https://prometheus.io/docs/practices/naming/)
  每个 label 组合都会形成新时间序列以及 label 设计建议。用于防止 trace_id、document_id、user_id 等高基数数据进入指标。
- [Prometheus: Exemplars Storage](https://prometheus.io/docs/prometheus/latest/feature_flags/#exemplars-storage)
  在指标样本中关联代表性 Trace ID 的机制。用于从 Grafana 延迟尖峰下钻到 Langfuse Trace，而不把 trace_id 设为普通 label。
- [Langfuse: Metrics API](https://langfuse.com/docs/metrics/features/metrics-api)
  对 Langfuse Observations 与 Scores 聚合成本、用量、延迟、调用量和质量分数。用于解释其与通用 Prometheus 指标监控重叠但不等价的部分。
- [Langfuse: Observations API](https://langfuse.com/docs/api-and-data-platform/features/observations-api)
  逐行获取 Span、Generation、Event 的输入输出、模型、用量、延迟和 Trace 上下文。用于对比 Prometheus 聚合时间序列与 Langfuse 逐请求明细。
- [Langfuse: Scores](https://langfuse.com/docs/evaluation/scores/overview)
  将正确性、相关性和业务质量评价附着到 Trace、Observation、Session 或 Experiment Run。用于界定 Langfuse 的 LLM 质量层能力。
- [Langfuse: Access Control (RBAC)](https://langfuse.com/docs/administration/rbac)
  Projects 作为 Langfuse 数据与细粒度访问控制分组，Project API keys 访问对应 Project 数据。用于校准多部门 Project 隔离与服务端 client 选择。
- [Langfuse: Public API](https://langfuse.com/docs/api-and-data-platform/features/public-api)
  Project-level API 范围及 Public Key / Secret Key Basic Auth。用于确认 Prompt、Trace 等访问由 Project credentials 选定。
- [OpenTelemetry: What is OpenTelemetry?](https://opentelemetry.io/docs/what-is-opentelemetry/)
  官方总览：OTel 负责生成、采集和导出 traces、metrics、logs，但本身不是存储或可视化后端。用于校准所有 OTel 基础定义。
- [OpenTelemetry: Traces](https://opentelemetry.io/docs/concepts/signals/traces/)
  Trace、Span、Trace ID、Span ID、父子关系、attributes、events、links 和 status。用于理解 Langfuse Observation 的底层追踪模型。
- [OpenTelemetry: Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
  W3C `traceparent`、跨服务上下文注入与提取、日志关联。用于设计 API、OCR worker 和异步审核流水线的分布式 Trace。
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
  Receiver、Processor、Exporter、Collector 重试/批处理/过滤和多后端分发。用于设计 Langfuse 与 Tempo、Jaeger、Datadog 等平台共存。
- [OpenTelemetry Protocol Specification](https://opentelemetry.io/docs/specs/otlp/)
  OTLP/HTTP 与 OTLP/gRPC 的传输、编码、默认路径和多目标交付语义。用于核实 Langfuse OTLP endpoint 的协议边界。
- [Langfuse: OpenTelemetry for LLM Observability](https://langfuse.com/integrations/native/opentelemetry)
  Langfuse OTLP/HTTP Trace 入口、认证、v4 实时 ingestion header、属性映射、Collector 示例和过滤风险。
- [Langfuse: Existing OpenTelemetry Setup](https://langfuse.com/faq/all/existing-otel-setup)
  LangfuseSpanProcessor、全局/隔离 TracerProvider、与 Sentry、Datadog、Honeycomb、Jaeger、Tempo 共存以及 Span 过滤和计费风险。
- [Langfuse Datasets](https://langfuse.com/docs/evaluation/experiments/datasets)
  Dataset、Dataset Item、生产 Trace 来源关联和可复用测试集。用于设计 bad case 收集与 golden set。
- [Langfuse Experiments via SDK](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk)
  当前 Python Experiment runner、task、item evaluator、run evaluator、并发和结果比较。用于实现离线回归 runner。
- [Langfuse Prompt Management Data Model](https://langfuse.com/docs/prompt-management/data-model)
  Prompt、不可变版本、production/latest/custom labels 和发布工作流。用于设计候选、晋级与回滚。
- [Langfuse Prompt Version Control](https://langfuse.com/docs/prompt-management/features/prompt-version-control)
  按版本或 label 获取 Prompt，并保持运行可复现。用于固定实验使用的 Prompt version。
- [Langfuse Annotation Queues](https://langfuse.com/docs/evaluation/evaluation-methods/annotation-queues)
  人工审核队列和 Score Config。用于把原始 thumbs-down 变成有类别、有纠正答案的高质量样本。
- [Langfuse Python SDK v3 to v4 Migration](https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4)
  Python SDK v4 在 2026 年重写后的迁移说明。用于约束 EasySQL 的依赖版本和兼容性。
- [Langfuse Experiment Action](https://github.com/langfuse/experiment-action)
  在 GitHub CI 中运行 Experiment、评论结果并通过 RegressionError 阻止回归。用于后续建立 Prompt 发布门禁。
- [EasySQL SQL Generation Quality Evaluation Research](docs/research/2026-04-16-sql-generation-quality-evaluation-research.md)
  本仓库已有的 Text2SQL 专用指标、结果集比较、golden set 和 EvalRunner 研究。用于补足 Langfuse 不负责的判分实现。

## Wisdom (Communities)

- [Langfuse Discord](https://discord.gg/7NXusRtqYU)
  官方社区，适合核实 self-hosted、SDK 升级、Experiment 和 Prompt Management 的实际使用问题。

## Gaps

- EasySQL 还没有可运行的内部 golden dataset 和结果集等价比较器
- EasySQL 还没有用户反馈接口、人工审核状态和 Langfuse trace_id 持久化
- 尚未用真实目标数据库验证 Langfuse Experiment runner 与当前 LangGraph callback 的父子 Trace 结构
