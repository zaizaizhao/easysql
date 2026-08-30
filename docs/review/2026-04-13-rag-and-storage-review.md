# RAG 与存储链路评审

## 范围与核心判断

本文关注 EasySQL 的检索与存储链路，主要包括：

- schema retrieval
- Milvus / Neo4j 的职责边界
- filter chain
- few-shot 存储
- code context retrieval
- prompt 组装时 retrieval artifact 的传递方式

先给结论：这条链路功能上已经比较完整，Milvus 做语义召回，Neo4j 做关系扩展，few-shot 和 code context 也都接进来了；但当前实现更像“围绕存储实现的一大段 imperative workflow”，还不是“围绕稳定 retrieval contract 设计的一组可组合 stage”。因此它最大的风险不是单点 bug，而是三个更底层的问题：

- 主 schema 检索对 `db_name` 的隔离做得不够硬
- filter contract 不纯，执行顺序影响含义
- retrieval artifact 往下游传递时过于依赖 `dict` 与手工重建

## 当前实现（结合代码）

### 1. Milvus 存了 `database_name`，但主检索接口没有把它做成一等输入

`MilvusSchemaReader` 的表检索接口只有 `filter_expr`，列检索接口也只支持按表名过滤：

```python
def search_tables(
    self,
    query: str,
    top_k: int = 10,
    filter_expr: str | None = None,
) -> list[dict]:
    ...
    results = self.client.search(
        collection_name=self.table_collection,
        data=[query_embedding],
        limit=top_k,
        search_params=search_params,
        filter=filter_expr,
        output_fields=[
            "database_name",
            "table_name",
            "chinese_name",
            "description",
            "business_domain",
        ],
    )
```

```python
def search_columns(
    self,
    query: str,
    top_k: int = 20,
    table_filter: list[str] | None = None,
) -> list[dict]:
    ...
    if table_filter:
        tables_str = ", ".join(f'"{t}"' for t in table_filter)
        filter_expr = f"table_name in [{tables_str}]"
```

对应代码：

- [easysql/readers/milvus_reader.py](../easysql/readers/milvus_reader.py)

这里最关键的矛盾是：

- 写入侧已经把 `database_name` 存进了 Milvus
- 读出侧却没有强制要求调用者显式传入 `db_name`

这意味着如果一个 collection prefix 下未来承载多个逻辑数据库，主 schema retrieval 路径很可能先把别的库的表召回出来，后面再靠 Neo4j 扩展和 filter 慢慢收敛。这种“先污染、再修正”的模式会让召回和精排边界变得很模糊。

### 2. `SchemaRetrievalService.retrieve()` 把太多阶段揉进了一个方法

主检索方法里同时做了：

- Milvus 表召回
- Neo4j FK 扩展
- bridge table 识别
- must-keep 保护
- filter chain 执行
- FK target 补全
- 列级召回
- join path 查询

其中一段核心逻辑如下：

```python
search_results = self._milvus.search_tables(
    query=question,
    top_k=self.config.search_top_k,
)
...
expanded_tables = self._neo4j.expand_with_related_tables(
    table_names=original_tables,
    max_depth=self.config.expand_max_depth,
    db_name=db_name,
)
...
filter_result = self._filter_chain.execute(expanded_tables, context)
final_tables = filter_result.tables
...
column_results = self._milvus.search_columns(
    query=question,
    top_k=20,
    table_filter=final_tables,
)
```

对应代码：

- [easysql/retrieval/schema_retrieval.py](../easysql/retrieval/schema_retrieval.py)

这种写法的问题不是“代码长”，而是 stage boundary 不清楚：

- 哪一步负责 recall
- 哪一步负责 graph augmentation
- 哪一步负责 post-process
- 哪一步负责 prompt-facing artifact assembly

当这些职责都堆在一个方法里时，你很难单独 benchmark 某一层，也很难替换其中一层而不影响整条链路。

### 3. FK 扩展后又回头查 Milvus，形成额外耦合与 N+1 查询

FK 扩展之后，代码会对新增表逐个回查 Milvus，给它们补 score：

```python
for table in expanded_tables:
    if table not in table_scores:
        result = self._milvus.search_tables(
            query=question,
            top_k=1,
            filter_expr=f'table_name == "{table}"',
        )
        if result:
            table_scores[table] = result[0]["score"]
        else:
            table_scores[table] = 0.0
```

对应代码：

- [easysql/retrieval/schema_retrieval.py](../easysql/retrieval/schema_retrieval.py)

这段代码透露出一个更深层的问题：图扩展阶段本来应该产出“图上需要保留的表”，现在却还要回到向量检索层给它补一份语义分数。结果就是：

- graph stage 依赖 vector stage 的细节
- 新增表越多，这段逻辑越像 N+1 查询
- “这个表为什么被保留”会同时混合语义得分和关系拓扑原因

更稳妥的做法应该是让 candidate 自带 provenance，例如：

- 来自向量召回
- 来自 FK 扩展
- 来自 bridge protection
- 来自 must-keep 规则

而不是把所有来源都硬塞成一套 `table_scores`。

### 4. filter chain 名义上可组合，但上下文是可变的

`BridgeFilter` 会直接修改 `context.original_tables`：

```python
for bridge in bridge_tables:
    if bridge not in result_tables:
        result_tables.append(bridge)
        added.append(bridge)
        if bridge not in context.original_tables:
            context.original_tables.append(bridge)
```

对 direct neighbor 的保护也一样：

```python
if table in self._protected_tables and table not in result_tables:
    result_tables.append(table)
    direct_neighbors.append(table)
    if table not in context.original_tables:
        context.original_tables.append(table)
```

对应代码：

- [easysql/retrieval/bridge_filter.py](../easysql/retrieval/bridge_filter.py)

这会带来一个非常具体的问题：`original_tables` 名字上是“最初召回结果”，但运行中却会被后置 filter 动态篡改。这样后面的 filter 或统计逻辑就分不清：

- 哪些表真的是 Milvus 原始召回
- 哪些表是桥表保护追加进来的
- 哪些表是 direct neighbor 强行保留的

一旦 provenance 被写坏，排序、解释性、debugging 都会跟着变差。

### 5. code context retrieval 只有“把表名拼进 query”这一层弱关联

`CodeMilvusReader.search_with_tables()` 的做法是把相关表名直接拼接到 query 里：

```python
def search_with_tables(
    self,
    query: str,
    table_names: list[str] | None = None,
    top_k: int = 5,
    score_threshold: float = 0.3,
) -> list[dict[str, Any]]:
    enhanced_query = query
    if table_names:
        enhanced_query = f"{query} {' '.join(table_names)}"

    return self.search(
        query=enhanced_query,
        top_k=top_k,
        score_threshold=score_threshold,
    )
```

对应代码：

- [easysql/code_context/storage/milvus_reader.py](../easysql/code_context/storage/milvus_reader.py)

这说明 code context 目前并没有真正结构化的“表级过滤”能力，只是做了一个 query expansion。它能起到一定增强作用，但很难保证：

- 真正关联到这些表的代码一定优先命中
- 无关代码不会因为语义接近而混入

### 6. code context 在 prompt 组装层又绕开了既有 section abstraction

`RetrieveCodeNode` 不是把 code context 作为一个 section 交给 `ContextBuilder`，而是直接把原始文本拼接到 `user_prompt` 尾部：

```python
if code_context:
    context_output = state.get("context_output")
    if context_output:
        updated_user_prompt = context_output["user_prompt"] + "\n\n" + code_context
        return {
            "context_output": {
                **context_output,
                "user_prompt": updated_user_prompt,
            },
            "code_context": code_context,
        }
```

但 `ContextBuilder` 本身其实已经有一套多 section 组装机制：

```python
builder.add_section(SchemaSection(), SectionConfig(priority=0))
builder.add_section(FewShotSection(...), SectionConfig(priority=5))
builder.add_section(JoinPathSection(), SectionConfig(priority=10))
```

对应代码：

- [easysql/llm/nodes/retrieve_code.py](../easysql/llm/nodes/retrieve_code.py)
- [easysql/context/builder.py](../easysql/context/builder.py)

这说明 code context 已经成为 retrieval 主链路的一部分，但还没进入统一的 prompt artifact 模型。结果就是：

- schema / join path / few-shot 有结构
- code context 还是“末尾追加文本”

后面如果要做 token budget、section-level truncation、artifact explainability，这一块会明显落后。

### 7. few-shot 的去重与写入不在同一个向量空间

few-shot 去重时只编码 `question`：

```python
query_embedding = self._embedding_service.encode(question)
...
filter=f'db_name == "{safe_db_name}"'
```

但真正写入时编码的是 `question + sql`：

```python
embed_text = f"{question}\n{sql}"
embedding = self._embedding_service.encode(embed_text)
```

对应代码：

- [easysql/writers/few_shot_writer.py](../easysql/writers/few_shot_writer.py)

这会导致一个很具体的不一致：

- “是否重复”的判断基于问题语义
- “后续检索相似 example”的向量却同时包含 SQL

如果两条问题相似但 SQL 差异很大，或者问题稍有措辞差异但 SQL 几乎一致，当前去重策略都会变得不稳定。

## 与更成熟实现方式的对比

Milvus 与 Neo4j 的使用本身没有问题，问题在于 contract 设计得太松。

更成熟的混合检索实现通常会把链路拆成几层：

- base retriever
- graph augmentation / expansion
- postprocessor
- prompt artifact builder

每层都产出结构明确的对象，而不是把大量业务语义塞在一个 service 方法和一组可变 `dict` 里。

EasySQL 现在已经有这些层的雏形：

- MilvusSchemaReader
- Neo4jSchemaReader
- FilterChain
- ContextBuilder

但这些抽象还没有完全变成稳定边界。尤其是：

- `db_name` 没有成为主 schema 检索的一等 contract
- filter 仍然能改写 provenance
- code context 没有并入统一 section 体系

## 评审结论

1. 原 review 对这条链路的判断是合理的：当前主要矛盾不是“有没有做混合检索”，而是“检索 contract 还不够纯，导致正确性、可解释性、可测试性都被拖累”。
2. 风险最高的点是主 schema retrieval 的库级隔离不够硬。因为 few-shot 路径其实已经展示了更稳妥的 `db_name` 过滤模式，说明仓库内部已经有更好的做法可以复用。
3. 第二优先级问题是 stage boundary 不清晰，导致任何 retrieval 调优最后都容易落成“大方法内继续加逻辑”，长期会越来越难维护。

## 优化方向

### 1. 把 `db_name` 提升为主 schema retrieval 的一等参数

建议直接把以下 contract 固化下来：

- `search_tables(query, db_name, top_k, ...)`
- `search_columns(query, db_name, table_filter, top_k, ...)`

由 reader 自己负责组装 Milvus filter，而不是把数据库隔离留给调用方通过 `filter_expr` 自行拼接。

### 2. 用 typed candidate 替换现在的 `list[str] + mutable context`

候选表至少应携带这些信息：

- `table_name`
- `db_name`
- `score`
- `source`
- `must_keep_reason`

这样 bridge protection、FK expansion、semantic filter 才能在不破坏 provenance 的前提下协作。

### 3. 把 `SchemaRetrievalService.retrieve()` 拆成可独立测试的 stage

至少拆成：

- table recall
- graph expansion
- candidate postprocess
- column retrieval
- prompt artifact assembly

拆完之后你们才能回答这些关键问题：

- 性能瓶颈到底在哪一层
- recall 问题到底是 Milvus 不准，还是 filter 太狠
- bridge table 是必要保留，还是误召回放大器

### 4. 去掉 FK 扩展后的逐表 Milvus 回查

如果扩展出来的表只是为了 join correctness，就应该把它标记成 graph-required candidate，而不是强行为它补一份向量分数。除非你们真的需要“扩展表也必须拥有统一语义分数”，那也应该设计批量 metadata lookup，而不是当前这种逐表 search。

### 5. 让 code context 成为真正的 prompt section

`ContextBuilder` 既然已经有 section abstraction，就应该把 code context 也纳入这套体系。这样才能统一处理：

- token budget
- section priority
- section-level truncation
- prompt artifact explainability

### 6. 统一 few-shot 去重与写入的 embedding 语义

要么都基于 `question`
要么都基于 `question + sql`

但不应继续保持“去重看一个空间，存储检索看另一个空间”的状态。

## 为什么这些建议成立

这些建议完全来自当前代码，而不是抽象偏好：

- `MilvusSchemaReader` 已经暴露出“字段里有 `database_name`，接口上却不强制用”的不一致
- `SchemaRetrievalService.retrieve()` 已经把过多语义耦合在一个方法里
- `BridgeFilter` 已经实际改写了 `original_tables`
- `RetrieveCodeNode` 和 `ContextBuilder` 已经形成两套 prompt artifact 体系
- `FewShotWriter` 已经在去重与写入上使用了不同 embedding 语义

所以这次优化的重点不是“再加一个检索器”，而是先把现有检索链路的 contract 收紧，让每一层都知道自己到底负责什么。

## 建议优先级

- `P0`：把 `db_name` 变成主 schema / column 检索的强约束，并补跨库隔离测试
- `P1`：拆分 `SchemaRetrievalService.retrieve()`，同时引入 typed candidate / provenance
- `P1`：修复 `BridgeFilter` 对 `original_tables` 的可变污染
- `P1`：把 code context 并入统一 section abstraction
- `P2`：统一 few-shot 去重与写入的 embedding 语义
