# 独立 ADK Agent 与增量 Wiki

这是 EasySQL 当前的 Text2SQL 实现。一个 Google ADK `LlmAgent` 自主选择上下文工具、判断证据是否足够、生成和验证 SQL。它不调用 LangGraph，也不先跑一条固定检索 workflow。原有 LangGraph 代码保留为历史实现。

## 启动

在项目根目录执行：

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn easysql_agentic.app:app --port 8000
```

前端保持原来的启动方式：

```bash
cd easysql_web
npm install
npm run dev
```

`easysql_api.app:app` 入口也默认使用 ADK。新增的唯一运行时选择是 `QUERY_BACKEND=adk`，已经是默认值。只有要恢复历史流程时才设置 `QUERY_BACKEND=langgraph`。

继续复用现有设置：

- `POSTGRES_URI`：Wiki、EasySQL 会话和 ADK 会话共用现有控制面 PostgreSQL。ADK 的 `DatabaseSessionService` 接收 `ControlPlaneDatabaseManager` 的引擎，不单独配置连接池。
- 原有模型提供商、模型名、API key 和 API base。ADK 通过官方 `LiteLlm` 适配器使用这些设置；没有第二份 ADK 模型配置。
- 原有数据源设置、逻辑数据库别名和 dblink 连接名。
- `AGENT_MAX_ITERATIONS`、`AGENT_TIMEOUT_SECONDS`、`QUERY_TIMEOUT_SECONDS`：继续控制模型调用和请求预算。
- 原有 Neo4j、Milvus、Embedding 配置：用于已有 Schema 检索和可重建的 Wiki 索引。

当前多 dblink 执行后端支持 PostgreSQL 到 PostgreSQL；它不等同于 Oracle 的 `table@link`。

## 目录与职责

```text
easysql_agentic/
├── agent.py             # 单个查询 Agent 的指令、工具装配和预算检查
├── models.py            # 复用现有设置创建 ADK/LiteLLM 模型
├── runtime.py           # ADK Runner、持久会话与工具进度
├── service.py           # 聊天、追问、澄清、分支与 API 适配
├── app.py               # 独立运行入口，复用公共 API 外壳
├── api.py               # 上传 Markdown、Wiki 浏览及来源管理
├── dependencies.py      # 复用数据库管理器与配置的小型工厂
├── knowledge/
│   ├── models.py        # 页面、原文引用、跨库关联与复合键契约
│   ├── organizer.py     # Markdown 章节解析与 ADK 结构化整理
│   ├── repository.py    # PostgreSQL 原子发布、历史与查询
│   ├── service.py       # 增量建立与分层读取
│   ├── index.py         # Milvus/Neo4j 可重建投影
│   └── tables.py        # 控制面 ORM 模型
└── tools/
    ├── context.py       # Agent 可直接调用的上下文及完成工具
    ├── catalog.py       # 复用 Schema 检索和数据源元数据
    ├── joins.py         # 物理关系与文档关系的联合路径
    └── sql.py           # SQLGlot 校验本地和远端查询，复用 dblink 执行器
```

## Markdown 如何增量建立知识库

在侧栏进入“知识库”，选择适用的数据源，上传 UTF-8 的 `.md` 或 `.markdown` 文件。每个文件上限为 512 KiB。上传的数据库别名必须对应项目已配置的数据源；MD 不会创建或修改业务数据库中的表。

1. 按 Markdown 章节拆分，超长章节完整分段处理。
2. LLM 整理术语、指标、Schema 说明、关联规则、SQL 示例和业务规则，输出 Pydantic 契约。
3. 校验引用必须逐字存在于原文，表引用必须属于上传范围。文档未说明的关联、基数、指标定义不能补造。
4. PostgreSQL 在一笔事务中发布新版本和页面。新文件增加来源；同一 `source_key` 替换该来源的全部旧页面，包含已经从原文移除的条目。其他来源不受影响。
5. 完全相同的内容和数据库范围重复上传会直接返回 `unchanged`，不重复调用 LLM。LLM/校验失败不会改变已发布版本。
6. 发布后同步 Milvus 和 Neo4j。索引失败时记录 `pending`，可以点击“重试索引”；Wiki 目录、正文和 PostgreSQL 关键词检索继续可用。每个向量命中都重新核对控制面的来源、范围和版本，旧索引不会恢复已删除知识。

默认 `source_key` 是文件名。同名文件表示更新；两个独立来源请使用不同文件名，API 也支持显式传入 `source_key`。不同来源的知识和引用都会保留，Agent 看到业务口径冲突时需要澄清，不能静默选择某个版本。

Wiki 存储为有领域路径的 Markdown 页面，而不是在服务器任意写入上传文件路径。来源全文及每版页面快照保存在 PostgreSQL 中。跨库规则保留完整的 `database.schema.table`、全部 `column_pairs`、基数、粒度和附加条件，并投影到 Neo4j。

## 渐进式读取与 Agent 工具

Agent 先阅读目录或搜索摘要，再选择需要的页面。`browse_wiki` 每次展开一级领域；`list_wiki_pages` 每次最多返回 20 个摘要；`read_wiki_page` 每次读取最多 8,000 字符并返回 `next_offset`。不会预先把整份 Wiki 注入模型。

上下文工具包括：

- `describe_database_scope`：允许的库、方言与不含凭据的连接名。
- `browse_wiki`、`list_wiki_pages`、`search_knowledge`、`read_wiki_page`：分层 Wiki。
- `search_tables`、`search_columns`：复用现有语义检索。
- `list_database_tables`、`get_table_schema`：按需读取真实表名与完整字段类型。
- `expand_related_tables`、`find_join_paths`：物理外键与 MD 跨库业务关联。
- `search_sql_examples`：复用已有 Few-shot 示例。
- `check_dblink_routes`：复用有方向的真实连接探测。
- `assess_context`：Agent 显式报告缺口、已加载证据和判断理由。
- `submit_final_sql`：校验并提交完整 SQL。
- `ask_clarification`、`report_insufficient_context`：遇到业务歧义或无法补齐的信息时结束本轮。

`assess_context` 不能引用未加载的证据。提交前必须加载 SQL 涉及的真实表结构；纯文本 SQL 不会被当作成功。工具错误可以反馈给 Agent，模型调用数、工具调用数、输出分页和总耗时都有边界。

## dblink

复用 `DatabaseScope`、`FederatedSqlExecutor`、`DblinkSessionManager` 和现有数据库凭据。一个查询可以引用多个命名连接，始终只在选定的 `primary_db` 上提交一条完整 SQL。

只需一个主库能够访问本次选中的其余库；远端库无需反向连接主库。状态探测保留每个主库候选的有向通路，Agent 从通路就绪的候选中选择执行入口。

SQLGlot 分别解析外层 SQL 与每个 dblink 字符串内的远端 SQL，检查只读查询、数据库和 Schema 范围、已配置连接名，拒绝嵌套 dblink、连接管理函数、连接串和多语句。未限定 Schema 的表会补上已配置的 Schema，防止连接的 search_path 选择同名表。每个远端 SELECT 先单独检查执行计划，再真实执行受限的完整查询，以免空的本地结果让远端验证被跳过。PostgreSQL 本地验证使用只读事务，远端沿用只读会话；失败回滚后再清理命名连接。

外层 `LIMIT 1` 仅限制验证返回行数，不承诺远端只扫描一行。Agent 指令要求在远端尽早筛选、按正确业务粒度聚合，并保留超时限制。跨库读取也不自动提供多个数据库的统一快照。

## API

```text
POST   /api/v1/knowledge/documents                        multipart: file, db_names, source_key?
GET    /api/v1/knowledge/documents                        来源及版本/索引状态
GET    /api/v1/knowledge/documents/{id}/revisions          历史版本清单
POST   /api/v1/knowledge/documents/{id}/reindex            重试索引
DELETE /api/v1/knowledge/documents/{id}                   删除该来源的知识
GET    /api/v1/knowledge/wiki?domain=医疗                 下一级目录
GET    /api/v1/knowledge/pages?domain=医疗&offset=0       页面摘要
GET    /api/v1/knowledge/pages/{id}?offset=0             页面正文与原文引用
GET    /api/v1/knowledge/search?q=MPI                     摘要检索
```

读取接口可重复传递 `db_names` 查询参数限制数据范围。现有 `/query`、`/sessions/.../message`、`continue`、`branch` 和 `fork` API 继续可用。已有 LangGraph 对话仍可查看；它的检查点不能直接当作 ADK 检查点进行分支，应在 ADK 中发起新对话。

## 验证

```bash
# 使用真实 ADK Runner；模型响应由测试模型稳定提供，不产生外部 LLM 费用。
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest tests/agentic -q

# 另启临时 PostgreSQL 集群，真实测试迁移、Wiki 增量发布、持久 ADK 会话和三库 dblink。
# 需要本机 initdb/pg_ctl；测试结束自动停止，完全不使用应用 .env 的数据库凭据。
PYTHON_DOTENV_DISABLED=1 EASYSQL_AGENTIC_TEST_POSTGRES=1 .venv/bin/python -m pytest tests/agentic -q

cd easysql_web
npm run build
```

ADK 接口以本次验证的 2.9.2 为基础。Google GenAI 2.x 与旧版 LangChain Google 适配器有依赖冲突，因此历史依赖中的 `langchain-google-genai` 同步要求 4.4.0 或更新的兼容版本。

官方参考：[ADK Function Tools](https://google.github.io/adk-docs/tools-custom/function-tools/)、[ADK Sessions](https://google.github.io/adk-docs/sessions/session/)、[LiteLLM 模型适配](https://google.github.io/adk-docs/agents/models/litellm/)、[PostgreSQL dblink](https://www.postgresql.org/docs/current/contrib-dblink-function.html)。
