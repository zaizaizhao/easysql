# EasySQL 数据库层重构指导文档

> 更新日期: 2026-04-25
> 状态: 控制面连接管理与 repository 事务收敛已实施，数据面连接注册表作为后续阶段。

## 1. 架构结论

EasySQL 应明确采用双层数据库架构：

| 层级 | 责任 | 数据库 | SQLAlchemy 模式 | 所属代码 |
| --- | --- | --- | --- | --- |
| 控制面 | API 会话、运行时配置、LangGraph checkpoint | PostgreSQL 13+ | async SQLAlchemy | `easysql_api/infrastructure/` |
| 数据面 | 目标库 schema 提取、SQL 生成后的查询执行 | MySQL/PostgreSQL/Oracle/SQL Server | sync SQLAlchemy | `easysql/` core |

控制面保持 PostgreSQL 专用是合理的。它依赖 JSONB、ARRAY、UUID、UPSERT 和
LangGraph Postgres saver，这些属于 EasySQL 自身运行状态，不是用户被分析的业务库。
数据面继续保持多数据库支持，不能被控制面的 PostgreSQL 选择污染。

## 2. 配置原则

数据库配置遵循两个边界：

1. 用户只填写一个 `POSTGRES_URI`。
2. 代码按消费者派生不同 DSN。

当前配置模块中的派生入口：

| 消费者 | 使用配置 |
| --- | --- |
| API async SQLAlchemy | `settings.postgres_sqlalchemy_async_uri` 或由 control-plane manager 内部规范化 |
| LangGraph/Postgres psycopg 消费者 | `settings.postgres_psycopg_uri` |
| 建库/管理库连接 | `settings.postgres_admin_psycopg_uri` |

控制面连接池属于启动期基础设施配置，不应放进前端运行时配置。前端运行时配置适合 LLM、
检索、few-shot、namespace 等业务参数；连接池大小、连接回收、pre-ping 等参数在引擎创建后
不会自动生效，放到前端会造成“已保存但未生效”的维护问题。

启动期连接池配置：

```ini
POSTGRES_POOL_SIZE=10
POSTGRES_MAX_OVERFLOW=20
POSTGRES_POOL_TIMEOUT=30
POSTGRES_POOL_RECYCLE=3600
POSTGRES_POOL_PRE_PING=true
```

## 3. 命名边界

`PROJECT_NAMESPACE` 不替代 `NEO4J_DATABASE`：

- `NEO4J_DATABASE` 是部署层能力，用于选择 Neo4j 物理/逻辑数据库。
- `PROJECT_NAMESPACE` 是应用逻辑隔离，用于 Milvus collection prefix、Neo4j label/property scope。

这不是兼容性问题，而是可维护性问题。把部署层数据库名和应用层 namespace 混在一起，会让
多项目隔离、运维备份、Neo4j 权限和数据清理都变得难以解释。

## 4. 实施阶段

### 阶段 1: 文档与配置对齐

目标：

- 文档只描述一个 `POSTGRES_URI`。
- 删除旧的 `SESSION_POSTGRES_URI`、`CHECKPOINTER_POSTGRES_*` 思路。
- 保留 `NEO4J_DATABASE`，将 `PROJECT_NAMESPACE` 定义为应用逻辑隔离。
- 明确前端运行时配置和启动期基础设施配置的边界。

验收：

- 配置测试覆盖 async/psycopg DSN 派生。
- 配置 schema 不暴露启动期连接池参数。

### 阶段 2: API 控制面连接管理器

目标：

- 在 `easysql_api/infrastructure/db_manager.py` 建立 `ControlPlaneDatabaseManager`。
- 由 manager 持有 async engine 和 async sessionmaker。
- 由 manager 提供事务上下文，统一 commit/rollback。
- `easysql_api/infrastructure/db.py` 保留为薄门面，减少调用点一次性迁移成本。

当前设计：

```python
db_manager = get_control_plane_db_manager()
db_manager.init_control_plane(
    settings.postgres_uri,
    ControlPlanePoolConfig.from_settings(settings),
)

async with db_manager.session() as session:
    ...
```

控制面 manager 只管理 API PostgreSQL 控制面，不管理数据面目标库。这样可以避免
`easysql` core 反向依赖 `easysql_api`。

验收：

- `postgresql://` 会规范化为 `postgresql+asyncpg://`。
- 连接池参数来自 `POSTGRES_POOL_*`。
- session context 成功时 commit，异常时 rollback。
- `dispose()` 可关闭并清空 engine/sessionmaker。

### 阶段 3: Repository 事务收敛

目标：

- 新增或调整 repository 构造方式，让 repository 依赖 control-plane session provider。
- 删除 repository 内部重复的手动 commit/rollback，由 `ControlPlaneDatabaseManager.session()` 统一处理。
- 保持 PostgreSQL 专属 UPSERT，因为它属于控制面。

当前设计：

```python
repository = ConfigRepository(get_control_plane_db_manager())
session_repository = SqlAlchemySessionRepository(get_control_plane_db_manager())
```

验收：

- `ConfigRepository` 和 `SqlAlchemySessionRepository` 不直接调用 `commit()` / `rollback()`。
- 写操作通过 control-plane session provider 进入事务上下文。
- `SqlAlchemySessionRepository.create()` 在 commit 前执行 `flush()` / `refresh()`，确保返回实体有数据库默认字段。

### 阶段 4: 数据面同步 engine registry

目标：

- 在 `easysql` core 或中立 infrastructure 中建立数据面 engine registry。
- registry 只管理目标业务库的 sync SQLAlchemy engines。
- `SQLAlchemySchemaExtractor` 和 `SqlAlchemyExecutor` 复用 registry。

边界：

- 不能放到 `easysql_api`，否则 core 会依赖 API。
- 不要把数据面强行改成 async。schema reflection、跨数据库驱动和现有 executor 都是同步栈，
  保持 sync SQLAlchemy 更简单、更稳定。

## 5. 维护性判断

当前方向合理，原因是：

- 控制面 async SQLAlchemy 和数据面 sync SQLAlchemy 不是“混乱”，而是两个职责层的技术选择。
- API 请求路径需要 async PostgreSQL session，避免阻塞 FastAPI 事件循环。
- 数据面面对多种目标数据库，同步 SQLAlchemy + Inspector 的兼容性和驱动支持更直接。
- 统一的是每一层内部的连接生命周期，不是把所有数据库访问强行抽象成一个类。

不建议做的事：

- 不要支持 MySQL/Oracle/SQL Server 作为控制面。
- 不要让 `easysql` core 导入 `easysql_api`。
- 不要把启动期 infra 参数放入前端运行时配置。
- 不要用一个跨层 `DatabaseManager` 同时管理控制面和数据面。

## 6. 验证清单

阶段 2 至少运行：

```bash
./.venv/bin/python -m pytest tests/test_control_plane_db_manager.py -v
./.venv/bin/python -m pytest tests/test_settings_refactor.py -v
./.venv/bin/python -m ruff check easysql_api/infrastructure/db_manager.py easysql_api/infrastructure/db.py easysql_api/app.py easysql_api/deps.py easysql/configuration/factory.py easysql/configuration/models.py tests/test_control_plane_db_manager.py tests/test_settings_refactor.py
```

阶段 3 至少运行：

```bash
./.venv/bin/python -m pytest tests/test_repository_transaction_contexts.py -v
```

阶段 4 需要补 extractor/executor 的 engine 复用测试，避免每次创建新 engine。
