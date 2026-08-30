# EasySQL 评审汇总

## 复核结论

我重新阅读了昨天生成的 review 文档，并重新对照仓库代码做了一轮校验。总体判断是：原来的 review 方向整体合理，问题识别基本抓到了主线，没有出现明显“脱离代码空谈架构”的情况；真正需要修正的是表达方式。

原文档主要有两个问题：

- 全部是英文，不符合当前使用场景
- 代码证据不够展开，很多结论只有文件引用，没有把“这段代码为什么会导致这个问题”讲透

因此这轮修订没有推翻昨天的结论，而是做了三件事：

- 把 `docs/review/` 全部改成中文
- 在各篇 review 中补了更具体的代码片段和解释
- 重新检查优先级排序，确认 deep-dive 选择是否仍然成立

## 本轮 review 文档

已完成的五个主 review：

- [2026-04-13-backend-architecture-review.md](./2026-04-13-backend-architecture-review.md)
- [2026-04-13-langgraph-workflow-review.md](./2026-04-13-langgraph-workflow-review.md)
- [2026-04-13-rag-and-storage-review.md](./2026-04-13-rag-and-storage-review.md)
- [2026-04-13-config-and-runtime-review.md](./2026-04-13-config-and-runtime-review.md)
- [2026-04-13-infra-observability-review.md](./2026-04-13-infra-observability-review.md)

已完成的三个深度分析：

- [2026-04-13-config-and-runtime-deep-dive.md](./2026-04-13-config-and-runtime-deep-dive.md)
- [2026-04-13-backend-architecture-deep-dive.md](./2026-04-13-backend-architecture-deep-dive.md)
- [2026-04-13-langgraph-workflow-deep-dive.md](./2026-04-13-langgraph-workflow-deep-dive.md)

## 为什么原排序仍然成立

重新核对代码后，我保留了昨天的排序。原因很简单：几个高优先级主题并不是“看起来更架构”，而是它们真的控制着运行时真相。

- 配置与运行时排第一，是因为 `Settings`、嵌套 `BaseSettings`、DB override、运行时缓存失效一起组成了半显式控制面。只要 precedence 不清楚，很多问题都不会以报错形式出现，而是以“改了但没完全生效”的方式出现。
- 后端架构和 LangGraph 工作流并列第二，是因为它们分别控制“谁拥有运行时资源”和“谁拥有工作流状态权威”。这两件事一旦不清楚，branch、resume、graph rebuild、服务拆分都会持续受影响。
- RAG 与存储虽然风险很高，但 blast radius 略窄于配置和工作流权威问题。它更多影响检索正确性、可解释性与后续调优效率。
- 基础设施与可观测性的问题也真实存在，但更多是把当前真实运行契约暴露清楚，工程量主要在补齐和收口，不像前三项那样直接控制系统内核行为。

## 排名矩阵

| 方向 | 正确性风险 | 架构杠杆 | 交付拖拽 | 横向影响面 | 总分 | 复核后的判断 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| [2026-04-13-config-and-runtime-review.md](./2026-04-13-config-and-runtime-review.md) | 5 | 5 | 5 | 5 | 20 | 配置权威来源竞争、override 与 cache invalidation 关系不清，会直接造成运行时行为与 operator 认知脱节。 |
| [2026-04-13-backend-architecture-review.md](./2026-04-13-backend-architecture-review.md) | 4 | 5 | 5 | 5 | 19 | 运行时资源 ownership 分散在模块级全局变量与大 service 中，导致后端演进和测试替换都偏重。 |
| [2026-04-13-langgraph-workflow-review.md](./2026-04-13-langgraph-workflow-review.md) | 5 | 5 | 4 | 5 | 19 | checkpoint state、shadow state、legacy/agent 双模式并存，直接作用于核心 Text2SQL 主链路。 |
| [2026-04-13-rag-and-storage-review.md](./2026-04-13-rag-and-storage-review.md) | 5 | 4 | 4 | 4 | 17 | 检索正确性受 `db_name` 隔离不足、filter provenance 污染和大方法编排影响，但影响面略窄于前三项。 |
| [2026-04-13-infra-observability-review.md](./2026-04-13-infra-observability-review.md) | 4 | 4 | 3 | 4 | 15 | 主要矛盾是外部运维契约不够诚实，修复价值高，但多数是补齐与澄清，不是底层运行模型重构。 |

## 贯穿五篇文章的共同主题

### 1. 运行时真相过于隐式

这是这次 review 最稳定的结论。多个方向都指向同一件事：仓库里的概念分层已经有了，但真正的运行时真相仍然散落在：

- 模块级全局变量
- `lru_cache`
- service 层 fallback state
- 文档未写明的 precedence 规则

这也是为什么很多问题不是“代码坏了”，而是“代码能跑，但别人很难准确预测它怎么跑”。

### 2. 项目处在多条迁移线同时并存的阶段

当前代码不是混乱，而是明显处于迁移期：

- legacy SQL loop 与 `sql_agent` 并存
- `.env` 配置与 DB persisted override 并存
- LangGraph checkpoint state 与 session shadow state 并存
- Langfuse tracing 已接入，但 service-level observability 还没补齐

因此很多问题都表现为“已经有了 70% 的正确方向，但剩下 30% 正好卡在最关键的边界上”。

### 3. 最有价值的优化是边界收口，不是功能重写

这次 review 没有哪一篇建议“推倒重来”。真正高收益的动作是：

- 明确 ownership
- 明确 precedence
- 明确 persisted state authority
- 明确 retrieval contract

这些工作做完之后，后面的性能优化、检索调优、agent 演进才会更稳。

## 建议的执行顺序

### 第一阶段：先修运行时真相

1. 优先收敛配置权威与 runtime invalidation 语义。
2. 同时把后端资源 ownership 从模块级全局迁到 app-scoped 生命周期。
3. 补上 config precedence、graph resume、cross-database retrieval 这三类关键回归测试。

原因是这一步会直接减少“系统看起来改了，实际没完全改”的风险。

### 第二阶段：收口核心工作流

1. 收敛 LangGraph checkpoint state 与 `session.state` 的权威边界。
2. 明确 legacy / agent 两条路径的 retry 语义。
3. 给 legacy loop 加 progress guard。

这一阶段会直接提升 Text2SQL 主链路的可解释性与可回放性。

### 第三阶段：提升检索 contract 纯度

1. 让 `db_name` 成为主 schema retrieval 的一等输入。
2. 用 typed candidate / provenance 替换 `list[str] + mutable context`。
3. 把 code context 并入统一 prompt section abstraction。

这样做之后，RAG 调优才会真正进入“可以分层定位”的状态，而不是继续在一个大方法里叠逻辑。

### 第四阶段：伴随式补齐基础设施与可观测性

建议把 infra/observability 放到前三阶段里伴随推进，而不是单独开一个大重构。因为健康检查、日志启动、启动文档、依赖说明，本质上都应该跟随运行时边界一起收口。

## 选中的 deep-dive 主题

复核后仍然保留以下三篇为最值得先做的深挖方向：

1. [2026-04-13-config-and-runtime-deep-dive.md](./2026-04-13-config-and-runtime-deep-dive.md)
2. [2026-04-13-backend-architecture-deep-dive.md](./2026-04-13-backend-architecture-deep-dive.md)
3. [2026-04-13-langgraph-workflow-deep-dive.md](./2026-04-13-langgraph-workflow-deep-dive.md)

选择依据没有变化：

- `config` 解决的是“系统到底以谁为准”
- `backend` 解决的是“运行时资源到底归谁管”
- `langgraph` 解决的是“核心工作流状态到底谁说了算”

这三件事正好构成 EasySQL 当前最核心的运行时三角。

## 复核后的最终判断

如果只用一句话概括这次 review 的结果，就是：

EasySQL 当前最需要的不是再加新能力，而是把已经存在的运行时能力收敛成一套更清楚、更可验证、更可解释的模型。

昨天的 review 在方向上是对的；这次修订主要是把它从“方向判断”提升成“有代码证据支撑的中文工程结论”。
