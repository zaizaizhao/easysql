# EasySQL 配置系统重构设计文档

## 文档版本

- **版本**: v1.0
- **日期**: 2026-04-24
- **状态**: 设计阶段

## 目录

1. [背景与问题](#背景与问题)
2. [设计目标](#设计目标)
3. [四层配置模型](#四层配置模型)
4. [配置项详细分类](#配置项详细分类)
5. [合并与精简方案](#合并与精简方案)
6. [迁移路径](#迁移路径)
7. [实施计划](#实施计划)

---

## 背景与问题

### 当前配置系统的问题

EasySQL 当前配置系统存在以下核心问题：

1. **配置权威不唯一**
   - 顶层 `Settings` + 多个嵌套 `BaseSettings`（`LLMConfig`、`CheckpointerConfig`、`LangfuseConfig`）
   - `.env` / 环境变量 / DB 持久化 override 多层叠加
   - 运行时通过 `setattr` patch 实例，而非统一 source chain

2. **生效时机不明确**
   - 部分配置需要进程重启（Neo4j URI、Milvus URI、Embedding 维度）
   - 部分配置可以热生效（LLM 模型、检索参数）
   - 部分配置需要重建下游资产（业务数据库连接 → Milvus/Neo4j 重建）
   - 文档和代码未明确区分这三种生效时机

3. **配置项冗余**
   - 三套 PostgreSQL 配置（Checkpointer、Session、未来的 Config 持久化）
   - 三套 Milvus Collection Prefix（表 schema、代码上下文、few-shot）
   - 两套 LLM API Key（检索层 filter、生成层）

4. **业务数据库建模不当**
   - `DB_<NAME>_*` 用正则扫环境变量动态解析
   - 本质是一等实体（需要 CRUD、加密、连通性测试、触发索引），却被当成普通配置

5. **invalidate_tags 与运行时对象不对齐**
   - `llm.temperature` 只带 `settings` tag，但 LLM client 实例可能已缓存
   - `llm.use_agent_mode` 带 `graph` tag，但 graph rebuild 逻辑未完全实现

---

## 设计目标

### 核心原则

1. **单一权威来源**：只有顶层 `Settings` 是 `BaseSettings`，嵌套配置改为 `BaseModel`
2. **显式生效时机**：每个配置项明确标注 `reload_mode: process_restart | hot | reindex`
3. **按职责分层**：基础设施 / 运行时调参 / 用户偏好 / 数据源 四层分离
4. **减少冗余**：合并重复配置，统一命名空间
5. **一次性收敛**：项目尚未上线，优先删除旧路径，避免长期兼容分支

### 非目标

- ❌ 不做"配置即代码"（不引入 Terraform/Pulumi 风格的声明式配置）
- ❌ 不做配置版本控制（不在配置系统内实现 Git-like 版本管理）
- ❌ 不做配置审计日志（审计属于独立功能，不在本次重构范围）

---

## 四层配置模型

### 模型概览

```
┌──────────────────┬─────────────────┬─────────────────┬───────────────────┐
│   L1 基础设施    │ L2 运行时调参   │ L3 用户偏好     │  L4 数据源        │
├──────────────────┼─────────────────┼─────────────────┼───────────────────┤
│ .env / 环境变量  │ DB KV 表        │ localStorage    │ 独立表 + 加密列   │
│ 进程重启生效     │ 热生效 + cache  │ 即时（前端）    │ 显式 reindex 流程 │
│                  │ invalidate      │                 │                   │
│ 运维权限         │ 工作区管理员    │ 每个用户        │ 数据负责人        │
│ 不进 API         │ /config/* API   │ 不进后端 API    │ /datasources/*    │
└──────────────────┴─────────────────┴─────────────────┴───────────────────┘
```

### L1 · 基础设施配置（Infrastructure）

**定义**：改了之后必须重启进程或重建底层连接才能安全生效的配置。

**存储位置**：`.env` 文件 / 环境变量 / 容器 secret / Kubernetes ConfigMap

**权限要求**：运维/部署权限

**不进入**：
- ❌ 不进 `config_schema.py`（不可通过 API 编辑）
- ❌ 不进前端配置表单
- ❌ 不进 `easysql_configs` 表

**生效时机**：`reload_mode: process_restart`

**典型配置项**：
- Neo4j 连接（URI、用户名、密码、database）
- Milvus 连接（URI、token）
- PostgreSQL 连接（用于 checkpointer、session、config 持久化）
- Embedding 配置（provider、model、dimension、device、cache_dir）
- 日志配置（log_level、log_file）

---

### L2 · 运行时调参配置（Runtime Tuning）

**定义**：改了之后下一次 query/pipeline 执行就能生效，不需要重启进程的配置。

**存储位置**：后端数据库表（`workspace_runtime_settings` 或沿用 `easysql_configs`）

**权限要求**：工作区管理员

**暴露方式**：
- ✅ 进 `config_schema.py`（可通过 API 编辑）
- ✅ 进前端配置表单
- ✅ 持久化到 DB

**生效时机**：`reload_mode: hot`（通过 `CacheInvalidator` + graph rebuild）

**典型配置项**：
- LLM 配置（query_mode、模型选择、temperature、max_retries、agent_mode）
- 检索配置（top_k、expand_fk、semantic_filter、bridge_protection）
- Few-Shot 配置（enabled、max_examples、min_similarity）
- Code Context 配置（enabled、top_k、score_threshold）
- Langfuse 配置（enabled、keys、host）

---

### L3 · 用户偏好配置（User Preferences）

**定义**：只影响这个用户看到的 UI，不影响 SQL 生成结果的配置。

**存储位置**：
- 主要：浏览器 `localStorage`
- 可选：后端 `user_preferences` 表（如果需要跨设备同步）

**权限要求**：每个用户自己

**不进入**：
- ❌ 不进 `Settings` 对象
- ❌ 不进 `config_schema.py`
- ❌ 不影响后端逻辑

**生效时机**：即时（前端）

**典型配置项**：
- UI 主题（dark/light）
- 语言（zh/en）
- 侧边栏展开状态
- 表格密度
- 日期格式
- 默认分页大小
- 上次打开的数据源
- 最近查询历史

---

### L4 · 数据源配置（Datasources）

**定义**：改了之后需要触发 Milvus/Neo4j 重建流程的配置，是一等实体而非普通配置。

**存储位置**：独立表 `datasources`（带加密列、状态机、审计字段）

**权限要求**：数据负责人

**暴露方式**：
- ✅ 独立 API `/datasources/*`（CRUD + 连通性测试 + 触发索引）
- ✅ 前端独立页面（数据源管理）
- ❌ 不进 `config_schema.py`（不是普通配置）

**生效时机**：`reload_mode: reindex`（显式触发 pipeline）

**典型配置项**：
- 数据库连接信息（type、host、port、user、password、database、schema）
- 业务元数据（system_type、description）
- 索引状态（status: draft | testing | ready | indexing | indexed | stale | failed）
- 关联资源（milvus_collection、neo4j_label_scope）

---

## 配置项详细分类

### L1 配置项清单（基础设施）

| 配置项 | 当前位置 | 默认值 | 说明 | 是否保留 |
|--------|---------|--------|------|---------|
| **项目命名空间** | | | | |
| `PROJECT_NAMESPACE` | ❌ 新增 | `default` | 应用级逻辑命名空间，用于 Milvus collection prefix、Neo4j 节点/关系 scope | ✅ 新增 |
| **Neo4j** | | | | |
| `NEO4J_URI` | Settings | `bolt://localhost:7687` | Neo4j 连接 URI | ✅ 保留 |
| `NEO4J_USER` | Settings | `neo4j` | Neo4j 用户名 | ✅ 保留 |
| `NEO4J_PASSWORD` | Settings | `""` | Neo4j 密码 | ✅ 保留 |
| `NEO4J_DATABASE` | Settings | `neo4j` | Neo4j database 名，属于部署级基础设施配置 | ✅ 保留 |
| **Milvus** | | | | |
| `MILVUS_URI` | Settings | `http://localhost:19530` | Milvus 连接 URI | ✅ 保留 |
| `MILVUS_TOKEN` | Settings | `None` | Milvus 认证 token | ✅ 保留 |
| `MILVUS_COLLECTION_PREFIX` | Settings | `""` | Milvus collection 前缀 | ❌ 删除（用 PROJECT_NAMESPACE） |
| **PostgreSQL（统一）** | | | | |
| `POSTGRES_URI` | ❌ 新增 | - | 统一 PostgreSQL 连接输入，代码派生 async/sync URI | ✅ 新增 |
| `POSTGRES_POOL_MIN_SIZE` | ❌ 新增 | `2` | 连接池最小连接数 | ✅ 新增 |
| `POSTGRES_POOL_MAX_SIZE` | ❌ 新增 | `20` | 连接池最大连接数 | ✅ 新增 |
| `CHECKPOINTER_BACKEND` | CheckpointerConfig | `memory` | Checkpointer 后端（memory/postgres） | ✅ 保留 |
| `CHECKPOINTER_POSTGRES_*` | CheckpointerConfig | - | Checkpointer 专用 PG 配置 | ❌ 删除（用 POSTGRES_URI） |
| `SESSION_BACKEND` | Settings | `postgres` | Session 后端 | ✅ 保留 |
| `SESSION_POSTGRES_URI` | Settings | `None` | Session 专用 PG URI | ❌ 删除（用 POSTGRES_URI） |
| **Embedding** | | | | |
| `EMBEDDING_PROVIDER` | Settings | `local` | Embedding provider（local/openai_api/tei） | ✅ 保留 |
| `EMBEDDING_MODEL` | Settings | `BAAI/bge-large-zh-v1.5` | Embedding 模型名 | ✅ 保留 |
| `EMBEDDING_DIMENSION` | Settings | `1024` | Embedding 向量维度 | ✅ 保留（开发需要） |
| `EMBEDDING_DEVICE` | Settings | `None` | 本地推理设备（cpu/cuda） | ✅ 保留（可选） |
| `EMBEDDING_CACHE_DIR` | Settings | `None` | 本地模型缓存目录 | ✅ 保留（可选） |
| `EMBEDDING_API_BASE` | Settings | `None` | API provider 端点 | ✅ 保留 |
| `EMBEDDING_API_KEY` | Settings | `None` | API provider key | ✅ 保留（可选） |
| `EMBEDDING_TIMEOUT` | Settings | `60.0` | API 请求超时 | ❌ 删除（硬编码） |
| **日志** | | | | |
| `LOG_LEVEL` | Settings | `INFO` | 日志级别 | ✅ 保留 |
| `LOG_FILE` | Settings | `None` | 日志文件路径 | ✅ 保留（可选） |

---

### L2 配置项清单（运行时调参）

#### 已在 config_schema.py 中

| 配置项 | category | invalidate_tags | 说明 | 建议 |
|--------|----------|-----------------|------|------|
| **LLM 配置** | | | | |
| `query_mode` | llm | settings | 查询模式（plan/fast） | ✅ 保持 |
| `openai_llm_model` | llm | settings | OpenAI 模型名 | ✅ 保持 |
| `google_llm_model` | llm | settings | Google 模型名 | ✅ 保持 |
| `anthropic_llm_model` | llm | settings | Anthropic 模型名 | ✅ 保持 |
| `model_planning` | llm | settings | Plan 阶段专用模型 | ✅ 保持 |
| `temperature` | llm | settings | LLM 采样温度 | ✅ 保持，tag 加 llm_client |
| `use_agent_mode` | llm | settings, graph | 启用 Agent 模式 | ✅ 保持 |
| `agent_max_iterations` | llm | settings | Agent 最大迭代次数 | ✅ 保持 |
| `max_sql_retries` | llm | settings | SQL 生成最大重试次数 | ✅ 保持 |
| `openai_api_key` | llm | settings | OpenAI API key | ⚠️ 看产品定位 |
| `openai_api_base` | llm | settings | OpenAI API base | ⚠️ 看产品定位 |
| `google_api_key` | llm | settings | Google API key | ⚠️ 看产品定位 |
| `anthropic_api_key` | llm | settings | Anthropic API key | ⚠️ 看产品定位 |
| **检索配置** | | | | |
| `retrieval_search_top_k` | retrieval | settings, retrieval_cache | Milvus 检索 top-k | ✅ 保持 |
| `retrieval_expand_fk` | retrieval | settings, retrieval_cache | 启用 FK 扩展 | ✅ 保持 |
| `retrieval_expand_max_depth` | retrieval | settings, retrieval_cache | FK 扩展最大深度 | ✅ 保持 |
| `semantic_filter_enabled` | retrieval | settings, retrieval_cache | 启用语义过滤 | ✅ 保持 |
| `semantic_filter_threshold` | retrieval | settings, retrieval_cache | 语义过滤阈值 | ✅ 保持 |
| `semantic_filter_min_tables` | retrieval | settings, retrieval_cache | 语义过滤最小保留表数 | ✅ 保持 |
| `bridge_protection_enabled` | retrieval | settings, retrieval_cache | 启用桥表保护 | ✅ 保持 |
| `bridge_max_hops` | retrieval | settings, retrieval_cache | 桥表检测最大跳数 | ❌ 删除（硬编码 3） |
| `core_tables` | retrieval | settings, retrieval_cache | 核心表白名单 | ✅ 保持 |
| `llm_filter_enabled` | retrieval | settings, retrieval_cache | 启用 LLM 过滤 | ✅ 保持 |
| `llm_filter_max_tables` | retrieval | settings, retrieval_cache | LLM 过滤最大表数 | ✅ 保持 |
| `llm_filter_model` | retrieval | settings, retrieval_cache | LLM 过滤模型名 | ✅ 保持，复用生成层 key |
| `llm_api_key` | retrieval | settings, retrieval_cache | 检索层 LLM key | ❌ 删除（复用生成层） |
| `llm_api_base` | retrieval | settings, retrieval_cache | 检索层 LLM base | ❌ 删除（复用生成层） |
| **Few-Shot 配置** | | | | |
| `few_shot_enabled` | few_shot | settings, few_shot_cache | 启用 Few-Shot | ✅ 保持 |
| `few_shot_max_examples` | few_shot | settings, few_shot_cache | 最大示例数 | ✅ 保持 |
| `few_shot_min_similarity` | few_shot | settings, few_shot_cache | 最小相似度 | ✅ 保持 |
| `few_shot_collection_name` | few_shot | settings, few_shot_cache | Milvus collection 名 | ❌ 删除（自动生成） |
| **Code Context 配置** | | | | |
| `code_context_enabled` | code_context | settings, code_context_cache | 启用代码上下文 | ✅ 保持 |
| `code_context_search_top_k` | code_context | settings, code_context_cache | 代码检索 top-k | ✅ 保持 |
| `code_context_score_threshold` | code_context | settings, code_context_cache | 代码检索阈值 | ✅ 保持 |
| `code_context_max_snippets` | code_context | settings, code_context_cache | 最大代码片段数 | ✅ 保持 |
| **Langfuse 配置** | | | | |
| `langfuse.enabled` | langfuse | settings, callbacks, langfuse_env | 启用 Langfuse | ✅ 保持 |
| `langfuse.host` | langfuse | settings, callbacks, langfuse_env | Langfuse 服务地址 | ✅ 保持 |
| `langfuse.public_key` | langfuse | settings, callbacks, langfuse_env | Langfuse public key | ✅ 保持 |
| `langfuse.secret_key` | langfuse | settings, callbacks, langfuse_env | Langfuse secret key | ✅ 保持 |

#### 应该加入 L2 但当前不在 schema 中

| 配置项 | 当前位置 | 说明 | 建议 invalidate_tags |
|--------|---------|------|---------------------|
| `batch_size` | Settings | Pipeline 批处理大小 | settings |
| `enable_schema_extraction` | Settings | 启用 schema 提取 | ❌ 删除（永远 true） |
| `enable_neo4j_write` | Settings | 启用 Neo4j 写入 | ❌ 删除（永远 true） |
| `enable_milvus_write` | Settings | 启用 Milvus 写入 | ❌ 删除（永远 true） |
| `code_context_supported_languages` | Settings | 支持的代码语言 | ❌ 删除（硬编码） |

---

### L3 配置项清单（用户偏好）

| 配置项 | 存储位置 | 说明 | 是否跨设备同步 |
|--------|---------|------|--------------|
| `theme` | localStorage | UI 主题（dark/light） | 可选 |
| `locale` | localStorage | 语言（zh/en） | 可选 |
| `sidebar_collapsed` | localStorage | 侧边栏展开状态 | 否 |
| `table_density` | localStorage | 表格密度 | 可选 |
| `date_format` | localStorage | 日期格式 | 可选 |
| `default_page_size` | localStorage | 默认分页大小 | 可选 |
| `last_datasource_id` | localStorage | 上次打开的数据源 | 可选 |
| `recent_queries` | localStorage | 最近查询历史（前 10 条） | 否 |

---

### L4 配置项清单（数据源）

#### datasources 表结构

```sql
CREATE TABLE datasources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    db_type VARCHAR(50) NOT NULL,  -- mysql, postgresql, oracle, sqlserver
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL,
    user VARCHAR(255) NOT NULL,
    password_encrypted TEXT NOT NULL,  -- AES 加密
    database VARCHAR(255) NOT NULL,
    schema VARCHAR(255),
    system_type VARCHAR(100),  -- HIS, LIS, PACS, etc.
    description TEXT,

    -- 索引状态
    status VARCHAR(50) NOT NULL DEFAULT 'draft',  -- draft, testing, ready, indexing, indexed, stale, failed
    last_indexed_at TIMESTAMP,
    last_error TEXT,

    -- 关联资源
    milvus_collection VARCHAR(255),
    neo4j_label_scope VARCHAR(255),

    -- 审计字段
    created_by VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP  -- 软删除
);
```

---

## 合并与精简方案

### 合并方案

#### 1. PostgreSQL 配置合并（优先级最高）

**当前问题**：三套 PostgreSQL 配置，实际大概率指向同一个数据库

```ini
# 当前（10+ 个配置项）
CHECKPOINTER_POSTGRES_HOST=localhost
CHECKPOINTER_POSTGRES_PORT=5432
CHECKPOINTER_POSTGRES_USER=postgres
CHECKPOINTER_POSTGRES_PASSWORD=111111
CHECKPOINTER_POSTGRES_DATABASE=easysql
CHECKPOINTER_POOL_MIN_SIZE=1
CHECKPOINTER_POOL_MAX_SIZE=10

SESSION_POSTGRES_URI=postgresql+asyncpg://postgres:password@localhost:5432/easysql
```

**合并后（3 个配置项）**：

```ini
# 统一 PostgreSQL 配置输入（用于 checkpointer、session、config 持久化）
POSTGRES_URI=postgresql://postgres:password@localhost:5432/easysql
POSTGRES_POOL_MIN_SIZE=2
POSTGRES_POOL_MAX_SIZE=20
```

**代码改动**：
- `Settings` 暴露 `postgres_async_uri` 和 `postgres_sync_uri`
- `session_postgres_uri` / API SQLAlchemy async engine 使用 `postgres_async_uri`
- `CheckpointerConfig` / LangGraph checkpointer 使用 `postgres_sync_uri`
- 各模块用不同 table prefix 或 schema 隔离

**收益**：从 10+ 个配置项减到 3 个

---

#### 2. Milvus Namespace 合并

**当前问题**：三个 prefix 配置，实际都是为了多租户/多项目隔离

```ini
# 当前（3 个配置项）
MILVUS_COLLECTION_PREFIX=
CODE_CONTEXT_COLLECTION_PREFIX=
FEW_SHOT_COLLECTION_NAME=medical_few_shot_examples
```

**合并后（1 个配置项）**：

```ini
# 统一 Milvus 命名空间（所有 collection 自动加前缀）
PROJECT_NAMESPACE=medical

# 自动生成的 collection 名：
# - medical_table_embeddings
# - medical_code_chunks
# - medical_few_shot_examples
```

**代码改动**：
- 删掉 `milvus_collection_prefix`、`code_context_collection_prefix`、`few_shot_collection_name`
- 新增 `project_namespace`，默认值 `default`
- 各模块内部拼接：`f"{namespace}_{collection_type}"`

**收益**：从 3 个配置项减到 1 个

---

#### 3. LLM API Key 合并

**当前问题**：两套 LLM 配置，一套给检索层 filter，一套给生成层

```ini
# 当前（5 个配置项）
LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=your_deepseek_api_key
LLM_FILTER_MODEL=deepseek-chat

OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key
```

**合并后（1 个配置项）**：

```ini
# 只保留生成层配置
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
ANTHROPIC_API_KEY=...

# 检索层 filter 直接用生成层的 provider
LLM_FILTER_MODEL=gpt-4o-mini  # 自动用对应 provider 的 key
```

**代码改动**：
- 删掉 `llm_api_key` 和 `llm_api_base`（检索层专用）
- `llm_filter_model` 改成从 `LLMConfig` 里解析 provider 并复用 key

**收益**：从 5 个配置项减到 1 个

---

#### 4. Project Namespace 和 Neo4j Database 边界

**当前问题**：`NEO4J_DATABASE` 和 `MILVUS_COLLECTION_PREFIX` 都和隔离有关，但它们不是同一层职责。

**设计原则**：
- `NEO4J_DATABASE` 是部署级基础设施配置，表示连接到哪个 Neo4j database
- `PROJECT_NAMESPACE` 是应用级逻辑命名空间，表示 EasySQL 当前项目的数据 scope
- 一个 Neo4j database 内可以承载一个或多个项目 scope，项目隔离不应强制要求创建新的 Neo4j database

```ini
# 部署级连接目标
NEO4J_DATABASE=neo4j

# 应用级逻辑命名空间
PROJECT_NAMESPACE=medical

# 自动映射：
# - Neo4j database: neo4j
# - Neo4j node/relationship scope: project_namespace=medical
# - Milvus collections: medical_table_embeddings, medical_code_chunks, ...
```

**代码改动**：
- 保留 `neo4j_database`，连接 Neo4j 时仍使用它
- 新增 `project_namespace`，默认值 `default`
- Neo4j 写入/读取时为节点、关系、查询条件加入 `project_namespace`
- Milvus collection 名自动加 `project_namespace` 前缀

**收益**：部署拓扑和业务项目隔离解耦，避免把应用级 scope 误建模成数据库级能力

**注意**：`PROJECT_NAMESPACE` 仍需要校验命名规则，因为它会进入 Milvus collection 名和 Neo4j scope 字段

---

### 精简方案

#### 1. 删除"几乎不会改"的配置

| 配置项 | 当前默认值 | 删除理由 | 建议 |
|--------|-----------|---------|------|
| `BATCH_SIZE` | 1000 | 99% 场景不需要调 | 硬编码 1000 |
| `ENABLE_SCHEMA_EXTRACTION` | true | 关了就没法用 | 硬编码 true |
| `ENABLE_NEO4J_WRITE` | true | 关了就没法用 | 硬编码 true |
| `ENABLE_MILVUS_WRITE` | true | 关了就没法用 | 硬编码 true |
| `EMBEDDING_TIMEOUT` | 60.0 | 默认值够用 | 硬编码 60 |
| `CHECKPOINTER_POOL_MIN_SIZE` | 1 | 默认值够用 | 硬编码 2 |
| `CHECKPOINTER_POOL_MAX_SIZE` | 10 | 默认值够用 | 硬编码 20 |
| `CODE_CONTEXT_CACHE_DIR` | `.code_context_cache` | 默认值够用 | 硬编码 |
| `CODE_CONTEXT_SUPPORTED_LANGUAGES` | `csharp,python,...` | 默认值够用 | 硬编码 |
| `BRIDGE_MAX_HOPS` | 3 | 默认值够用 | 硬编码 3 |

**收益**：减少 10 个配置项

---

#### 2. 改成自动推导的配置

| 配置项 | 当前需要手动配 | 自动推导方案 | 收益 |
|--------|---------------|-------------|------|
| `EMBEDDING_DIMENSION` | 1024 | 从 `EMBEDDING_MODEL` 自动查表 | ⚠️ **不建议**（开发需要手动调） |
| `OPENAI_API_BASE` | `https://api.openai.com/v1` | 默认值，只有用代理时才需要改 | 提供默认值 |
| `LANGFUSE_BASE_URL` | `http://localhost:4000` | 默认 `https://cloud.langfuse.com` | 提供默认值 |

**注意**：`EMBEDDING_DIMENSION` 不建议自动推导，因为开发/调优场景需要手动测试不同维度。

---

#### 3. 改成功能开关的配置

**当前问题**：每个功能都有 3-7 个详细配置项，新手不知道怎么调

**精简方案**：只保留 `ENABLED` 开关，其他用默认值

```ini
# 当前（15 个配置项）
CODE_CONTEXT_ENABLED=false
CODE_CONTEXT_SEARCH_TOP_K=5
CODE_CONTEXT_SCORE_THRESHOLD=0.3
CODE_CONTEXT_MAX_SNIPPETS=3
CODE_CONTEXT_CACHE_DIR=.code_context_cache
CODE_CONTEXT_SUPPORTED_LANGUAGES=csharp,python,java,javascript,typescript
CODE_CONTEXT_COLLECTION_PREFIX=

FEW_SHOT_ENABLED=false
FEW_SHOT_MAX_EXAMPLES=3
FEW_SHOT_MIN_SIMILARITY=0.6
FEW_SHOT_COLLECTION_NAME=medical_few_shot_examples

LLM_FILTER_ENABLED=false
LLM_FILTER_MAX_TABLES=8
LLM_FILTER_MODEL=deepseek-chat
LLM_API_KEY=...
```

**精简后（3 个配置项）**：

```ini
# 功能开关（详细参数用默认值，高级用户可通过 L2 API 调整）
CODE_CONTEXT_ENABLED=false
FEW_SHOT_ENABLED=false
LLM_FILTER_ENABLED=false
```

**收益**：从 15 个配置项减到 3 个

---

### 精简前后对比

| 维度 | 当前 | 精简后 | 减少 |
|------|------|--------|------|
| 配置项总数 | ~60 | ~25 | **-58%** |
| 必填项 | ~15 | ~8 | **-47%** |
| PostgreSQL 配置 | 10 项（3 套） | 3 项 | **-70%** |
| Milvus 配置 | 3 项 | 1 项 | **-67%** |
| LLM 配置 | 12 项 | 5 项 | **-58%** |
| 功能开关 | 15 项 | 3 项 | **-80%** |
| `.env.example` 行数 | 267 行 | ~120 行 | **-55%** |

---

## 迁移路径

### 阶段 1：一次性切到新配置边界

**目标**：项目未上线，不保留旧配置 fallback，直接收敛到新的配置契约。

**实现**：

```python
class Settings(BaseSettings):
    postgres_uri: str
    postgres_pool_min_size: int = 2
    postgres_pool_max_size: int = 20
    project_namespace: str = "default"
    neo4j_database: str = "neo4j"

    @property
    def postgres_async_uri(self) -> str:
        return normalize_postgres_driver(self.postgres_uri, driver="asyncpg")

    @property
    def postgres_sync_uri(self) -> str:
        return normalize_postgres_driver(self.postgres_uri, driver="psycopg2")
```

**测试**：
- `POSTGRES_URI=postgresql://...` 能派生 async/sync URI
- `POSTGRES_URI=postgresql+asyncpg://...` 能派生 sync URI
- `POSTGRES_URI=postgresql+psycopg2://...` 能派生 async URI
- `PROJECT_NAMESPACE` 不改变 `NEO4J_DATABASE`

---

### 阶段 2：删除旧配置入口

**目标**：减少配置权威来源，避免维护旧字段和新字段的双路径。

**实现**：
- 删除 `CHECKPOINTER_POSTGRES_*`
- 删除 `SESSION_POSTGRES_URI`
- 删除 `MILVUS_COLLECTION_PREFIX`
- 删除 `CODE_CONTEXT_COLLECTION_PREFIX`
- 删除 `FEW_SHOT_COLLECTION_NAME`
- 删除检索层专用 `LLM_API_KEY` / `LLM_API_BASE`

---

### 阶段 3：更新配置和部署文档

**目标**：让 `.env.example`、部署文档、前端配置说明与新边界一致。

**文档**：
- 更新 `.env.example`
- 更新 `docs/ENVIRONMENT.md`
- 明确 L1 只能重启生效，L2 可由前端配置并热生效，L4 需要 reindex

---

### 迁移检查清单

**本地/部署环境**：
- [ ] 备份当前 `.env` 文件
- [ ] 创建新 `.env`，按新格式填写
- [ ] 测试环境验证新配置

**开发人员**：
- [ ] 更新本地 `.env`
- [ ] 更新 CI/CD 配置
- [ ] 更新 Docker Compose / Kubernetes manifests
- [ ] 更新文档和示例

---

## 实施计划

### Phase 1：基础重构（2 周）

**目标**：统一配置 authority，收敛到单一 `BaseSettings`

**任务**：

1. **重构 Settings 结构**
   - [ ] 把 `LLMConfig`、`CheckpointerConfig`、`LangfuseConfig` 改为 `BaseModel`
   - [ ] 只保留顶层 `Settings` 为 `BaseSettings`
   - [ ] 删除 `_apply_override_path` 的 `setattr` patch 逻辑
   - [ ] 实现 `resolve_effective_settings()` 统一构建流程

2. **合并 PostgreSQL 配置**
   - [ ] 新增 `POSTGRES_URI` 配置项
   - [ ] 实现 `postgres_async_uri` / `postgres_sync_uri` 派生 helper
   - [ ] API session 持久化使用 `postgres_async_uri`
   - [ ] LangGraph checkpointer 使用 `postgres_sync_uri`

3. **新增 PROJECT_NAMESPACE**
   - [ ] 新增配置项，默认值 `default`
   - [ ] 自动应用到 Milvus collection prefix
   - [ ] 自动应用到 Neo4j 节点/关系的 `project_namespace` scope
   - [ ] 保留 `NEO4J_DATABASE` 作为部署级连接配置

4. **测试**
   - [ ] 单元测试：新配置能正常加载
   - [ ] 单元测试：PostgreSQL sync/async URI 派生正确
   - [ ] 单元测试：`PROJECT_NAMESPACE` 不覆盖 `NEO4J_DATABASE`
   - [ ] 集成测试：Neo4j、Milvus、PostgreSQL 连接正常
   - [ ] 回归测试：现有功能不受影响

**交付物**：
- 重构后的 `easysql/config.py`
- 更新的单元测试
- 更新后的配置说明

---

### Phase 2：L2 配置完善（1 周）

**目标**：完善运行时调参配置，修正 invalidate_tags

**任务**：

1. **修正 invalidate_tags**
   - [ ] `llm.temperature` 加 `llm_client` tag
   - [ ] 审查所有 `config_schema.py` 中的 tags，确保覆盖真实运行时对象
   - [ ] 实现 `CacheInvalidator` 对 LLM client 实例的失效逻辑

2. **删除冗余配置**
   - [ ] 删除 `llm_api_key` 和 `llm_api_base`（检索层专用）
   - [ ] 实现检索层 LLM filter 复用生成层 API key
   - [ ] 删除 `few_shot_collection_name`（自动生成）
   - [ ] 删除 `bridge_max_hops`（硬编码 3）

3. **补充缺失配置**
   - [ ] 把 `batch_size` 加入 `config_schema.py`（可选）
   - [ ] 删除 `enable_schema_extraction` 等永远 true 的开关

4. **测试**
   - [ ] 测试配置热更新是否真正生效
   - [ ] 测试 invalidate_tags 是否正确触发 cache 清理
   - [ ] 测试检索层 LLM filter 能否复用生成层 key

**交付物**：
- 更新的 `config_schema.py`
- 更新的 `CacheInvalidator`
- 配置热更新测试用例

---

### Phase 3：L4 Datasources 实现（2 周）

**目标**：把业务数据库从配置系统迁移到一等实体

**任务**：

1. **数据库表设计**
   - [ ] 创建 `datasources` 表（带加密列、状态机）
   - [ ] 实现密码加密/解密逻辑（AES-256）

2. **API 实现**
   - [ ] `POST /datasources` - 创建数据源
   - [ ] `GET /datasources` - 列出数据源
   - [ ] `GET /datasources/{id}` - 获取数据源详情
   - [ ] `PUT /datasources/{id}` - 更新数据源
   - [ ] `DELETE /datasources/{id}` - 删除数据源（软删除）
   - [ ] `POST /datasources/{id}/test` - 连通性测试
   - [ ] `POST /datasources/{id}/reindex` - 触发索引

3. **测试**
   - [ ] 单元测试：CRUD 操作
   - [ ] 集成测试：连通性测试、触发索引
   - [ ] 安全测试：密码加密、SQL 注入防护

**交付物**：
- `datasources` 相关表和 API
- API 文档

---

### Phase 4：前端实现（2 周）

**目标**：提供配置管理和数据源管理 UI

**任务**：

1. **L2 配置管理页面**
   - [ ] 实现配置表单（按 category 分组）
   - [ ] 实现配置重置功能
   - [ ] 显示配置是否被 override
   - [ ] 显示 invalidate_tags（高级模式）

2. **L4 数据源管理页面**
   - [ ] 数据源列表（带状态、最后索引时间）
   - [ ] 创建/编辑数据源表单
   - [ ] 连通性测试按钮
   - [ ] 触发索引按钮（带进度显示）
   - [ ] 删除确认对话框

3. **L3 用户偏好**
   - [ ] 实现 `useUserPreferences` hook
   - [ ] localStorage 存储
   - [ ] 主题切换、语言切换

4. **测试**
   - [ ] E2E 测试：配置修改流程
   - [ ] E2E 测试：数据源创建和索引流程
   - [ ] 可访问性测试

**交付物**：
- 配置管理页面
- 数据源管理页面
- E2E 测试用例

---

### Phase 5：文档和发布（1 周）

**目标**：完善文档，准备发布

**任务**：

1. **文档更新**
   - [ ] 更新 `docs/ENVIRONMENT.md`
   - [ ] 更新 `.env.example`
   - [ ] 编写配置边界说明
   - [ ] 更新 API 文档

2. **发布准备**
   - [ ] 编写 CHANGELOG
   - [ ] 标记 Breaking Changes
   - [ ] 准备发布说明
   - [ ] 更新版本号（v2.0.0）

3. **回归测试**
   - [ ] 完整功能测试
   - [ ] 性能测试（配置热更新延迟）
   - [ ] 安全测试（密码加密、权限控制）

**交付物**：
- 完整文档
- 发布说明
- v2.0.0 release

---

### 时间线总览

```
Week 1-2:  Phase 1 - 基础重构
Week 3:    Phase 2 - L2 配置完善
Week 4-5:  Phase 3 - L4 Datasources 实现
Week 6-7:  Phase 4 - 前端实现
Week 8:    Phase 5 - 文档和发布
```

**总计**：8 周（2 个月）

---

## 风险与缓解

### 风险 1：配置边界划分错误导致运行期行为不稳定

**影响**：高
**概率**：中

**缓解措施**：
- L1/L2/L4 每个配置项都标注 `reload_mode`
- L1 只允许启动时读取，不进前端可编辑配置
- L2 通过 `config_schema.py` 暴露，并绑定明确的 invalidate tags
- L4 数据源变更必须显式触发 reindex

---

### 风险 2：多 worker 部署下配置热更新不生效

**影响**：中
**概率**：高

**缓解措施**：
- 文档明确说明"单进程可立即失效，多进程需要广播或显式 reload"
- 未来可以引入 Redis pub/sub 广播失效
- 提供 `/admin/reload-config` API 手动触发所有 worker 重载

---

### 风险 3：密码加密密钥管理

**影响**：高
**概率**：低

**缓解措施**：
- 使用环境变量 `ENCRYPTION_KEY`（不进 `.env` 文件）
- 提供密钥轮转机制
- 文档说明密钥丢失后果（无法解密已存储的密码）
- 建议使用 KMS（AWS KMS、HashiCorp Vault）

---

## 附录

### A. 精简后的 .env.example

```ini
# =============================================================================
# EasySQL Configuration v2.0
# =============================================================================

# =============================================================================
# 项目命名空间（应用到 Milvus collection prefix 和 Neo4j 数据 scope）
# =============================================================================
PROJECT_NAMESPACE=default

# =============================================================================
# 基础设施连接
# =============================================================================

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
NEO4J_DATABASE=neo4j

# Milvus
MILVUS_URI=http://localhost:19530
# MILVUS_TOKEN=your_milvus_token  # 可选

# PostgreSQL（用于 checkpointer、session、config 持久化）
POSTGRES_URI=postgresql://postgres:password@localhost:5432/easysql
# POSTGRES_POOL_MIN_SIZE=2
# POSTGRES_POOL_MAX_SIZE=20

# Checkpointer 后端（memory 或 postgres）
CHECKPOINTER_BACKEND=memory

# =============================================================================
# Embedding 配置
# =============================================================================
EMBEDDING_PROVIDER=local  # local | openai_api | tei
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
EMBEDDING_DIMENSION=1024

# 本地推理配置（仅 EMBEDDING_PROVIDER=local 时需要）
# EMBEDDING_DEVICE=cuda
# EMBEDDING_CACHE_DIR=./models

# API Provider 配置（仅 openai_api/tei 时需要）
# EMBEDDING_API_BASE=http://localhost:11434/v1
# EMBEDDING_API_KEY=

# =============================================================================
# LLM 配置
# =============================================================================
QUERY_MODE=plan  # plan | fast

# API Keys（至少配一个）
OPENAI_API_KEY=your_openai_api_key
# GOOGLE_API_KEY=your_google_api_key
# ANTHROPIC_API_KEY=your_anthropic_api_key

# 模型选择（可选，有默认值）
# OPENAI_LLM_MODEL=gpt-4o
# GOOGLE_LLM_MODEL=gemini-1.5-pro
# ANTHROPIC_LLM_MODEL=claude-3-5-sonnet-20241022

LLM_TEMPERATURE=0.0

# =============================================================================
# 功能开关（可选，默认全关，详细参数通过前端配置）
# =============================================================================
CODE_CONTEXT_ENABLED=false
FEW_SHOT_ENABLED=false
LLM_FILTER_ENABLED=false

# =============================================================================
# Langfuse 可观测性（可选）
# =============================================================================
LANGFUSE_ENABLED=false
# LANGFUSE_PUBLIC_KEY=pk-xxxxx
# LANGFUSE_SECRET_KEY=sk-xxxxx
# LANGFUSE_BASE_URL=https://cloud.langfuse.com  # 默认值，自建时修改

# =============================================================================
# 日志配置
# =============================================================================
LOG_LEVEL=INFO
# LOG_FILE=logs/easysql.log

# =============================================================================
# 业务数据库
# =============================================================================
# 通过前端"数据源管理"页面配置，不再使用 DB_<NAME>_* 环境变量
```

---

### B. 参考资料

- [Pydantic Settings 最佳实践](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [FastAPI Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [12-Factor App: Config](https://12factor.net/config)

---

## 变更历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-24 | - | 初始版本 |

---

**文档结束**
