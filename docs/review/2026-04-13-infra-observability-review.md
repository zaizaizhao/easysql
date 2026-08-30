# 基础设施与可观测性评审

## 范围与核心判断

本文关注 EasySQL 的运行与观测面，包括：

- README 与环境文档
- `docker-compose.yml`
- Alembic 迁移路径
- FastAPI 生命周期
- 健康检查与 readiness
- 日志初始化
- Langfuse / service observability

整体判断是：项目已经具备比较清晰的生命周期切点，例如 `lifespan`、Alembic、Langfuse tracing 都有了，但对外暴露的运维契约还偏“乐观”。换句话说，系统内部知道自己依赖什么，外部接口却没有把这些依赖真实地表达出来。

## 当前实现（结合代码）

### 1. 文档和真实启动方式没有完全对齐

README 基本已经更新到了当前命令：

- `python main.py`
- `uvicorn easysql_api.app:app`

但 `docs/ENVIRONMENT.md` 里仍然保留着：

```bash
python main.py run --env /path/to/.env
```

对应位置：

- [README.md](/Users/zhaoyanan/Downloads/demo/easysql/README.md#L113)
- [docs/ENVIRONMENT.md](/Users/zhaoyanan/Downloads/demo/easysql/docs/ENVIRONMENT.md#L6)

这意味着 operator 文档层面已经存在漂移。

### 2. compose 只起了 Neo4j 和 Milvus，不是完整本地运行栈

`docker-compose.yml` 当前只有：

- `neo4j`
- `milvus`

没有：

- session store PostgreSQL
- API service

对应代码位置：

- [docker-compose.yml](/Users/zhaoyanan/Downloads/demo/easysql/docker-compose.yml#L3)

所以 compose 的真实含义应该是“依赖基础设施子集”，不是“完整本地一键启动栈”。

### 3. API 启动时的真实依赖比 health endpoint 表达得严格得多

API 生命周期里明确要求：

- session backend 必须是 postgres
- 必须能解析 session postgres URI
- 启动时要 init engine、bootstrap config、可选 setup checkpointer

代码片段如下：

```python
if not settings.is_session_postgres():
    raise RuntimeError("SESSION_BACKEND must be set to postgres.")

session_uri = settings.get_session_postgres_uri()
if not session_uri:
    raise RuntimeError(...)
```

对应代码位置：

- [easysql_api/app.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/app.py#L25)
- [easysql_api/app.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/app.py#L30)

但 health router 现在是这样的：

```python
@router.get("/health")
async def health_check():
    return {"status": "healthy"}

@router.get("/ready")
async def readiness_check():
    return {"status": "ready"}
```

对应代码位置：

- [easysql_api/routers/health.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/routers/health.py#L39)
- [easysql_api/routers/health.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/routers/health.py#L79)

这就是当前 infra / observability 最具体的问题之一：系统内部知道自己依赖很多东西，health endpoint 却一律“无条件健康”。

### 4. API 实际没有按文档 bootstrap logging

日志工具是有的：

```python
def setup_logging(level: str = "INFO", log_file: str | Path | None = None, ...):
    logger.remove()
    logger.add(sys.stderr, level=level, ...)
    if log_file:
        logger.add(log_file, ...)
```

对应代码位置：

- [easysql/utils/logger.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/utils/logger.py#L14)

CLI 和 pipeline 会调用它：

- [easysql/main.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/main.py#L79)
- [easysql/pipeline/schema_pipeline.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/pipeline/schema_pipeline.py#L72)

但 API 启动路径没有调用 `setup_logging()`。所以现在文档里虽然写了 `LOG_LEVEL`、`LOG_FILE`，API 实际并没有严格按这个入口初始化。

### 5. 迁移路径和 session store 配置是耦合的

Alembic 通过 `get_session_postgres_uri()` 来决定目标数据库：

```python
def _get_database_url() -> str:
    settings = get_settings()
    uri = settings.get_session_postgres_uri()
    ...
```

对应代码位置：

- [alembic/env.py](/Users/zhaoyanan/Downloads/demo/easysql/alembic/env.py#L21)

而 `get_session_postgres_uri()` 又允许 fallback 到 checkpointer postgres URI：

- [easysql/config.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/config.py#L439)

这不是错误，但必须明确写进运行说明，否则迁移与运行时到底连到哪个库，对 operator 来说并不透明。

### 6. 现在更像“LLM tracing”，而不是“service observability”

Langfuse 已经接得不错：

- config precedence 有测试
- query 执行带 callback
- sql agent 带 span

但 service 级别还没有：

- request tracing
- dependency tracing
- startup phase tracing
- exportable metrics

所以现在更准确的说法应该是：

> 项目已经有 LLM 可观测性，但还没有完整的服务可观测性。

## 与更成熟实践的对比

更成熟的服务型系统通常会把三种信号区分得很清楚：

- **liveness**：进程还活着
- **readiness**：当前可以对外提供服务
- **observability**：出了问题时能不能快速定位

EasySQL 当前：

- liveness 基本是有的
- readiness 几乎没有表达真实依赖
- observability 主要集中在 LLM 调用链，不覆盖完整服务

这和更成熟的 FastAPI/OTel 风格相比，差距主要不在“有没有某个库”，而在“有没有把真实运行约束表达成可观察信号”。

## 主要问题

### 1. 最高优先级问题：health / readiness 语义失真

当前 `/health` 和 `/ready` 的值，不能证明：

- session repo 可用
- config bootstrap 已完成
- DB 可连接
- checkpointer 可用

这会让上层部署系统得到错误的健康信号。

### 2. API logging contract 没有真正落地

日志配置文档、日志工具、API 启动行为三者没有闭环。结果就是 operator 以为可以通过配置控制日志，但 API 实际未必按该配置启动。

### 3. 本地运行说明是碎片化的

README、ENVIRONMENT、compose、Alembic、session store requirement 这些信息分散存在，而且没有统一成一条“最短正确启动路径”。

### 4. 迁移与运行数据库 fallback 语义不透明

`SESSION_POSTGRES_URI` 与 checkpointer postgres 的 fallback 逻辑如果不讲清楚，后续非常容易变成“为什么迁移跑到另一个库里了”的排障问题。

### 5. 可观测性仍然偏 LLM 层

Langfuse 对模型链路帮助很大，但对服务级排障来说不够。例如：

- readiness 为什么错
- DB 什么时候初始化失败
- 哪次启动 phase 卡住了

这些今天还不在主要观测面里。

## 优化方向

### 方向 1：重写 health / readiness 语义

建议：

- `/live` 继续保持进程级
- `/ready` 至少验证 session repo / DB 可用
- `/health` 要么删掉，要么做成综合依赖摘要

### 方向 2：把 API logging bootstrap 补完整

FastAPI 启动时就应读取 `LOG_LEVEL` / `LOG_FILE`，而不是只在 CLI / pipeline 路径生效。

### 方向 3：统一 operator 启动说明

建议明确拆成四步：

1. compose 起哪些依赖
2. 还缺哪些外部依赖
3. 迁移命令从哪里执行
4. API 用什么命令启动

### 方向 4：从 Langfuse 扩展到 service-level observability

保留 Langfuse 作为 LLM tracing，但服务层还需要：

- request tracing
- dependency spans
- startup diagnostics
- 更像 telemetry backend 的 metrics 输出

### 方向 5：补生命周期测试

应该补的不是更多 happy path，而是：

- 缺 session postgres 时启动失败
- readiness 在依赖不可用时返回失败
- API 启动日志是否按配置初始化

## 建议为何成立

这些建议之所以重要，是因为当前代码已经清楚表达了真实依赖图，但这些依赖没有同步体现在：

- health endpoint
- operator docs
- logging contract

这会让部署和排障层面的复杂度比代码本身看起来更高。

## 优先级与待确认问题

优先级建议：

- `P0`：修正 health / readiness 语义，补 API logging bootstrap
- `P1`：统一 README / ENVIRONMENT / compose / migration 运行说明
- `P1`：补 lifecycle / startup failure 测试
- `P2`：增加 service-level tracing 与 metrics

待确认问题：

- `SESSION_POSTGRES_URI -> checkpointer.postgres_uri` fallback 是生产级契约，还是仅本地便利？
- `/metrics` 未来是继续保留 JSON endpoint，还是转向 Prometheus / OTel 风格？
- Langfuse 是主观测后端，还是只承担 LLM slice？
