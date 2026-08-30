# LangGraph 工作流深度分析

## 问题定义

EasySQL 已经把 LangGraph 放到了 Text2SQL 主链路中心，但目前仍处于“迁移到一半”的状态：外层已经使用 graph、checkpoint、thread_id、interrupt，内层却仍然保留 service shadow state、legacy SQL loop 和黑盒式 `SqlAgentNode`。这会直接影响三件核心事情：

- 分支是否可解释
- 恢复是否可依赖
- 重试计数是否可比较

所以这篇能进前三，不是因为 LangGraph 用得不好，而是因为它已经足够重要，任何边界不清都会直接打到核心产品路径。

## 关键代码证据

### 1. 一个 graph 承载了两套执行语义

`build_graph()` 根据配置在同一个外层流程里切换 agent 模式与 legacy 模式：

```python
if use_agent_mode:
    builder.add_node("sql_agent", sql_agent_node)
else:
    builder.add_node("generate_sql", generate_sql_node)
    builder.add_node("validate_sql", validate_sql_node)
    builder.add_node("repair_sql", repair_sql_node)
...
if use_agent_mode:
    builder.add_edge("retrieve_code", "sql_agent")
    builder.add_edge("sql_agent", "update_history")
else:
    builder.add_edge("retrieve_code", "generate_sql")
    builder.add_edge("generate_sql", "validate_sql")
    builder.add_edge("repair_sql", "validate_sql")
```

对应代码：

- [easysql/llm/agent.py](../easysql/llm/agent.py)

问题不在于“有两个模式”，而在于它们共用一套外围 state contract 与 service contract。这样一来：

- 图长得一样，执行语义却不一样
- 字段名字一样，运维解释却不一样
- 上层服务必须理解两种内部模型

### 2. service 层维护了一套裁剪过的 shadow state

`QueryService` 会把 graph state 压缩成一份更小的 `session.state`：

```python
safe_keys = {
    "generated_sql",
    "validation_passed",
    "validation_result",
    "clarification_questions",
    "clarified_query",
    "error",
    "fork_conversation_history",
    "fork_cached_context",
    "fork_retrieval_result",
}
```

follow-up 时又会把它拿出来兜底：

```python
prev_state = snapshot.values if snapshot else session_state
...
cached_context = prev_state.get("cached_context")
if cached_context is None:
    cached_context = session_state.get("fork_cached_context")
retrieval_result = prev_state.get("retrieval_result")
if retrieval_result is None:
    retrieval_result = session_state.get("fork_retrieval_result")
```

对应代码：

- [easysql_api/services/query_service.py](../easysql_api/services/query_service.py)

这意味着系统现在并不是“所有恢复逻辑都从 checkpoint replay”，而是：

- 优先读 checkpoint
- 不够时读 session shadow state
- branch 时再借助 `fork_*` 字段兜底

这就是当前 replay fidelity 不够强的根本原因。

### 3. state schema 已经出现重复字段

`BuildContextNode` 同时写 `context_output` 和 `cached_context`：

```python
return {
    "context_output": context_dict,
    "cached_context": context_dict,
}
```

对应代码：

- [easysql/llm/nodes/build_context.py](../easysql/llm/nodes/build_context.py)

这段代码很有代表性，它说明当前 state schema 正在承担越来越多职责，但还没有明确决定：

- 哪些字段是当前节点输出
- 哪些字段是跨轮缓存
- 哪些字段是持久化恢复依赖

一旦边界不清，graph state 体积会越来越大，而 service 层又会继续发明新的 summary / fallback 字段。

### 4. legacy 路径里的 retry 语义与 progress 语义都偏模糊

`generate_sql` 每次产出 SQL 都直接加一：

```python
return {
    "generated_sql": sql,
    "validation_passed": False,
    "validation_result": None,
    "retry_count": state.get("retry_count", 0) + 1,
}
```

但 `repair_sql` 有可能什么也不做：

```python
if not error or not original_sql:
    return {}
```

对应代码：

- [easysql/llm/nodes/generate_sql.py](../easysql/llm/nodes/generate_sql.py)
- [easysql/llm/nodes/repair_sql.py](../easysql/llm/nodes/repair_sql.py)

这说明 legacy loop 里至少存在两个歧义：

- `retry_count` 更像 attempt 计数，不是失败轮次
- 节点可能推进了，但状态并没有真正前进

当这套字段再和 `sql_agent` 模式共存时，可观测性就会继续下降。

## 根因分析

根因非常明确：项目在逐步从 legacy SQL 生成链迁移到 agent 路径，但迁移过程中保留了过多“双轨”设计：

- graph state 一套
- service shadow state 一套
- legacy mode 一套
- agent mode 一套

这在迁移初期是合理的，因为它降低了切换风险；但一旦系统进入长期维护阶段，这种“双轨制”会从安全网变成主要复杂度来源。

## 为什么这件事优先级高

LangGraph 不是边缘模块，而是 Text2SQL 的核心编排器。只要这层的状态权威不清楚，后面所有这些场景都会变难：

- 追查一条 follow-up 为什么没有继承正确上下文
- 判断 branch 是基于哪一段历史分叉出去的
- 确认某次 SQL 失败到底发生在 validation、repair 还是 agent tool call

相比之下，换 prompt、调 retrieval、改模型都不是第一顺位，因为那些改动最终都还是要落到这条工作流上执行。

## 目标方向

建议目标是把当前“双轨工作流”收敛成一套更清楚的运行模型：

- checkpoint state 是恢复与分支的默认权威来源
- `session.state` 只做 UI / 摘要 / 运营展示
- retry 语义拆清楚，避免一个字段承载两种含义
- `SqlAgentNode` 要么继续黑盒但补齐结构化 artifact，要么逐步 graph-visible 化
- legacy mode 要么加硬约束继续支持，要么明确降级成兼容模式

## 分阶段优化建议

### 第一阶段：先把 correctness 问题钉住

- 补 interrupt / resume / branch 的服务边界测试
- 为 legacy loop 增加 progress guard
- 重命名或拆分 retry 相关字段

这是最小投入但收益很高的一步，因为它先解决“能不能稳定解释当前行为”。

### 第二阶段：收缩 state schema

- 清理 `context_output` / `cached_context` 这类重叠字段
- 让 retrieval artifact、conversation artifact、execution artifact 分开
- 限制 `session.state` 只保存明确允许投影出去的内容

### 第三阶段：收敛权威状态

- follow-up / branch 逻辑默认只依赖 checkpoint state
- `fork_*` 兜底逻辑逐步下沉为只读兼容层
- 重建流程围绕 persisted thread history，而不是围绕 service 自定义摘要

### 第四阶段：视业务价值决定是否拆 `SqlAgentNode`

如果你们要做更强的 replay、逐轮诊断、工具级统计，那就需要 subgraph 或 graph-visible steps。如果这些需求暂时不强，可以先保留黑盒节点，但至少要让内部迭代结果进入结构化持久化产物。

## 迁移风险与约束

最大的约束是兼容现有前端和 API 行为。因为现在流式输出、branch 创建、clarify 恢复已经是对外行为，不能为了“架构更纯”直接推翻。

另一个现实约束是 checkpointer 形态。如果某些环境仍然使用 `MemorySaver()`，那 checkpoint authority 只在单进程生命周期内成立。这个约束不会否定收敛方向，但会决定你们在“跨重启恢复”上能走多远。
