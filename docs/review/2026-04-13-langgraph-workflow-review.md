# LangGraph 工作流评审

## 范围与核心判断

本文聚焦 EasySQL 的 LangGraph 主链路，重点看以下几个问题：

- graph 是怎么组装的
- state 是怎么定义和持久化的
- follow-up / branch / clarify 这些多轮能力是怎么接进来的
- 旧版 `generate_sql -> validate_sql -> repair_sql` 与新版 `sql_agent` 是如何并存的

先说结论：这条链路不是“不能用”，相反，它已经正确用上了不少 LangGraph 的核心能力，例如 `StateGraph`、conditional edges、`thread_id`、`interrupt`、checkpointer。问题出在另一层：项目并没有完全把 LangGraph checkpoint state 当成唯一权威状态，而是在 API service 层额外维护了一套裁剪过的 `session.state`。这会让工作流在分支、恢复、重试语义上出现“双轨制”，而这恰好是 LangGraph 本来最适合帮你简化的部分。

## 当前实现（结合代码）

### 1. 一套 graph 外壳下并存两种执行模式

`build_graph()` 会根据 `settings.llm.use_agent_mode` 动态拼出两条完全不同的执行链：

```python
def build_graph() -> "CompiledStateGraph":
    settings = get_settings()
    use_agent_mode = settings.llm.use_agent_mode

    builder = StateGraph(EasySQLState)
    ...
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
        builder.add_conditional_edges(
            "validate_sql",
            route_validate,
            {"update_history": "update_history", "repair_sql": "repair_sql"},
        )
        builder.add_edge("repair_sql", "validate_sql")
```

对应代码：

- [easysql/llm/agent.py](../easysql/llm/agent.py)

这段代码说明了两个事实：

- graph 的外层编排只有一套
- 但核心 SQL 生成阶段实际上有两套完全不同的执行语义

这会带来一个长期问题：`QueryService`、state schema、持久化逻辑、调试手段都必须同时兼容“agent 内部循环模式”和“legacy 显式 validate/repair 模式”。短期看这是迁移期常见做法；长期看，这会让很多字段的语义开始漂移，比如 `retry_count`、`validation_passed`、`generated_sql` 到底对应哪一轮、哪一次修复、哪一种执行路径。

### 2. checkpoint state 已经存在，但 service 层并没有完全信任它

`QueryService` 会把 graph state 再裁成一份 `session.state` 存起来：

```python
def _sanitize_state(self, state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not state or not isinstance(state, dict):
        return None

    sanitized: dict[str, Any] = {}
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
    ...
```

而 follow-up 时，如果 checkpoint state 不完整，又会回退到 `session.state` 里的 `fork_*` 字段：

```python
snapshot = await graph.aget_state(
    self._make_config(session.session_id, effective_thread_id)
)
session_state = session.state if isinstance(session.state, dict) else {}
prev_state = snapshot.values if snapshot else session_state

cached_context = prev_state.get("cached_context")
if cached_context is None:
    cached_context = session_state.get("fork_cached_context")

retrieval_result = prev_state.get("retrieval_result")
if retrieval_result is None:
    retrieval_result = session_state.get("fork_retrieval_result")
```

对应代码：

- [easysql_api/services/query_service.py](../easysql_api/services/query_service.py)

这意味着当前系统的真实状态模型并不是“graph state 就是权威”，而是：

- 第一层：LangGraph checkpoint state
- 第二层：service 层裁剪过的 `session.state`
- 第三层：branch/fork 场景下额外兜底的 `fork_*` 字段

为什么这会有问题？

- `session.state` 不是完整 state，只保留了安全字段和 summary 字段
- 一旦 branch / follow-up 的正确性依赖这些裁剪逻辑，真正的业务语义就不再只掌握在 graph 里，而被分散到了 service 层
- 以后你要排查“某次 follow-up 为什么上下文不对”，就必须同时看 checkpoint、session.state、fork fallback，而不是只看一条 thread 的持久化轨迹

### 3. `BuildContextNode` 里已经出现重复 source of truth

`BuildContextNode` 会同时写入 `context_output` 和 `cached_context`，而且两者内容完全一样：

```python
context_dict = {
    "system_prompt": output.system_prompt,
    "user_prompt": output.user_prompt,
    "total_tokens": output.total_tokens,
}

return {
    "context_output": context_dict,
    "cached_context": context_dict,
}
```

对应代码：

- [easysql/llm/nodes/build_context.py](../easysql/llm/nodes/build_context.py)

这类代码的危险之处不在于“多存一份数据占内存”，而在于它会模糊字段职责：

- `context_output` 看起来像当前节点产物
- `cached_context` 看起来像跨轮复用缓存

但现在两者在写入时没有任何语义区别，后续节点却可能把它们当成不同含义来使用。随着 follow-up、fork、context summary 增加，这种“先复制一份再说”的做法很容易把 state schema 越堆越大。

### 4. legacy 模式下的重试语义并不稳定

旧链路里，`generate_sql` 一生成就直接增加 `retry_count`：

```python
return {
    "generated_sql": sql,
    "validation_passed": False,
    "validation_result": None,
    "retry_count": state.get("retry_count", 0) + 1,
}
```

但 `repair_sql` 在没有 `error` 或没有 `generated_sql` 时会直接空返回：

```python
if not error or not original_sql:
    # Nothing to repair
    return {}
```

对应代码：

- [easysql/llm/nodes/generate_sql.py](../easysql/llm/nodes/generate_sql.py)
- [easysql/llm/nodes/repair_sql.py](../easysql/llm/nodes/repair_sql.py)

这里至少有两个问题：

- `retry_count` 现在更像“生成/修复尝试次数”，并不等价于“完整失败重试次数”
- `repair_sql` 空返回意味着 legacy loop 存在“走了一步但状态没有实质推进”的可能

如果再和 `sql_agent` 模式放在一起看，问题会更明显。`sql_agent` 里的内部迭代不会自然映射到 legacy 里的 `retry_count`。也就是说，同一个字段名，在两种模式下并不表示同一种运维语义。

### 5. `SqlAgentNode` 更强，但也更黑盒

从架构角度看，`sql_agent` 路径比 legacy 路径更接近项目未来方向，因为它支持内部工具调用、流式事件、强制校验。但它把主要的 agent 循环都包进了一个大节点里，LangGraph 只能看到“进入 sql_agent”与“离开 sql_agent”，中间每一轮工具使用、每一次 validation 尝试都要靠节点内部事件流才能看见。

这不是实现错误，但意味着：

- live streaming 的体验可能不错
- 但 checkpoint replay 和 graph-level postmortem 会比较弱

换句话说，EasySQL 现在把 LangGraph 用成了“外层编排器 + 持久化壳”，而不是“真正可回放的细粒度 agent runtime”。

## 与更稳妥实现方式的对比

EasySQL 已经对齐了 LangGraph 的几项正确实践：

- 使用 `StateGraph`
- 使用 conditional routing
- 用 `thread_id` 作为多轮线程标识
- 用 `interrupt` 处理中断式澄清
- 编译 graph 时挂 checkpointer

真正落差不在“有没有用 LangGraph”，而在“最关键的执行真相是否真的交给 LangGraph 来保存和重放”。

更稳妥的实现一般会有两个特征：

- checkpoint state 是 follow-up / resume / branch 的默认权威来源
- 重要的 agent 行为要么拆成 graph-visible steps，要么至少以结构化 artifact 的形式进入 persisted state

EasySQL 现在的问题是这两件事都只做了一半：

- checkpoint 在用，但没有被完全信任
- agent 在跑，但主要细节被包在单个节点内部

## 评审结论

1. 原先 review 对这条链路的总体判断是合理的：当前最大问题确实不是“有没有 LangGraph”，而是“LangGraph state、service shadow state、legacy/agent 双模式”的边界不够清楚。
2. 当前实现已经具备较好的演进基础，因为 `thread_id`、checkpointer、interrupt、branch 相关逻辑都已经落地，不需要推倒重来。
3. 真正要优先处理的是状态权威收敛，而不是先去改 prompt 或换模型。因为只要 state authority 继续分散，branch correctness、resume correctness、调试成本都会持续偏高。

## 优化方向

### 1. 把 checkpoint state 收敛为 follow-up / branch 的默认权威来源

建议目标：

- `session.state` 只保留 UI 展示和摘要用途
- 任何需要恢复执行语义的逻辑，优先从 checkpoint state 读
- `fork_*` 这类 fallback 字段尽量缩减成只读 projection，而不是执行兜底

依据很直接：当前 `QueryService` 已经大量依赖 `graph.aget_state()`。既然项目已经把 graph state 作为主流程能力的一部分，就应该顺着这个方向继续收敛，而不是让 service 层继续承担第二套状态机。

### 2. 把 state schema 按职责拆分，而不是继续在一个大 `TypedDict` 上叠字段

至少应拆出几类语义：

- 会话/多轮历史
- retrieval/context artifact
- SQL 生成与校验状态
- branch/fork 元数据

这样做的理由不是形式化，而是能减少 `context_output` / `cached_context` 这种重复字段，也能让 follow-up 代码更清楚知道自己依赖的是“历史”还是“缓存”还是“执行产物”。

### 3. 为 legacy 与 agent 模式定义清晰、可比较的 retry 语义

可以选两条路：

- 保留一个统一字段，但严格定义为“完整 SQL 产出尝试次数”
- 或者拆成 `generation_attempts`、`repair_attempts`、`agent_iterations`

无论选哪条，都比现在“一个 `retry_count` 在不同路径里含义不同”更稳。

### 4. 给 legacy loop 增加 progress guard

如果 `repair_sql` 没有生成新 SQL、也没有改变错误状态，就不应该继续在 loop 中推进。否则 legacy path 很容易产生“图上看起来还在跑，但状态实际上没有进展”的情况。

### 5. 视长期目标决定是否把 `SqlAgentNode` 拆成 graph-visible 子步骤

如果你们后面很看重这些能力：

- 精准回放 agent 每轮决策
- 做 node / tool 级别可观测性
- 分析 SQL 修复失败发生在第几轮、哪一类工具调用

那么 `SqlAgentNode` 迟早要往 subgraph 或显式 tool step 的方向演进。反过来，如果你们更看重开发速度、并且当前 streaming 已经满足需求，那么短期可以先不拆，只要先把 persisted artifacts 补齐即可。

## 为什么这些建议成立

这些建议不是“为了架构更漂亮”，而是直接由当前代码推出来的：

- `build_graph()` 已经把工作流中心放在 LangGraph 上，说明 graph 不是装饰层
- `QueryService` 已经依赖 checkpoint state 做 follow-up 和 branch，说明 persisted state 已经承担业务语义
- `session.state` 的 sanitize/fallback 逻辑说明现在线上正确性还受 service 自定义投影影响
- `BuildContextNode`、`generate_sql`、`repair_sql` 这些局部实现已经暴露出 schema 冗余与 retry 语义漂移

因此，下一阶段最值得做的不是增加更多节点，而是先把“哪份状态才是真的”这件事说清楚，并在代码上收敛。

## 建议优先级

- `P0`：收敛 checkpoint state 与 `session.state` 的权威边界，并补 branch / resume 回归测试
- `P0`：修正 legacy loop 的 progress guard 与 retry 语义
- `P1`：清理 `context_output` / `cached_context` 之类的重复状态字段
- `P1`：明确 legacy mode 是长期支持路径，还是迁移兜底路径
- `P2`：视业务需要，逐步把 `SqlAgentNode` 拆成 graph-visible steps 或 subgraph
