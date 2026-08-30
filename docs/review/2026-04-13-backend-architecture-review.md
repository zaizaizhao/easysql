# 后端架构评审

## 范围与核心判断

本文只讨论 EasySQL 的 Python 后端架构，不讨论前端页面设计。关注范围包括：

- CLI 与 schema pipeline 入口
- FastAPI 生命周期与依赖注入
- `QueryService` 的职责边界
- 会话持久化与仓储层
- 运行时资源的 ownership

整体判断是：这个项目在目录层面已经具备“看起来合理”的分层，例如 `routers / services / domain / infrastructure / pipeline` 都已经存在；但真正的问题不在“有没有分层”，而在“运行时资源到底归谁管”这件事不够清楚。当前很多核心对象依赖进程级全局状态和缓存，导致代码表面分层还可以，但运行时耦合偏强。

## 当前实现（结合代码）

### 1. CLI 入口同时承载了两种后端运行模式

`easysql/main.py` 里，默认 callback 直接跑 schema pipeline，而 `serve` 子命令负责启动 API：

```python
app = typer.Typer(..., invoke_without_command=True)

@app.callback(invoke_without_command=True)
def main_callback(...):
    if ctx.invoked_subcommand is not None:
        return
    _run_pipeline(...)

@app.command()
def serve(...):
    uvicorn.run("easysql_api.app:app", ...)
```

对应代码位置：

- [easysql/main.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/main.py#L18)
- [easysql/main.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/main.py#L27)
- [easysql/main.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/main.py#L182)

这说明仓库里实际上并存两套后端运行形态：

- 一套是本地同步执行的 schema pipeline
- 一套是长生命周期的 API 服务

这本身不是问题，但它要求项目在资源管理方式上更统一，否则很容易出现“pipeline 那边是局部对象 ownership，API 这边是全局 singleton ownership”的架构风格割裂。

### 2. `SchemaPipeline` 的资源 ownership 反而是清楚的

`SchemaPipeline` 通过 lazy property 局部管理 Neo4j、Milvus、writer、embedding service：

```python
class SchemaPipeline:
    @property
    def neo4j_repo(self) -> Neo4jRepository:
        if self._neo4j_repo is None:
            self._neo4j_repo = Neo4jRepository(...)
        return self._neo4j_repo
```

对应代码位置：

- [easysql/pipeline/schema_pipeline.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/pipeline/schema_pipeline.py#L64)
- [easysql/pipeline/schema_pipeline.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/pipeline/schema_pipeline.py#L119)

这一层其实是好的示范：资源在对象内部延迟初始化，生命周期比较清晰，谁创建、谁使用、谁负责这一点很明确。

### 3. API 生命周期是 `lifespan`，但运行时资源落在全局变量里

FastAPI 入口本身写得不差，`lifespan` 已经用上了：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    ...
    init_engine(session_uri)
    repository = SqlAlchemySessionRepository(get_sessionmaker())
    set_session_repository(repository)
    ...
    yield
    clear_session_repository()
    clear_config_service()
    await dispose_engine()
```

对应代码位置：

- [easysql_api/app.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/app.py#L25)
- [easysql_api/app.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/app.py#L39)
- [easysql_api/app.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/app.py#L67)

但问题在于，生命周期虽然在 `lifespan` 里，真正的资源访问路径却通过 `deps.py` 里的全局变量暴露：

```python
_session_repository: SessionRepository | None = None
_config_service: ConfigService | None = None

def get_session_repository_dep() -> SessionRepository:
    if _session_repository is None:
        raise RuntimeError(...)
    return _session_repository
```

对应代码位置：

- [easysql_api/deps.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/deps.py#L12)
- [easysql_api/deps.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/deps.py#L20)
- [easysql_api/deps.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/deps.py#L36)

也就是说，现在并不是 “app 拥有 service，request 从 app 取 service”，而是 “启动阶段把对象塞到模块级全局变量里，后续所有请求再去读这个全局变量”。这会带来两个问题：

- startup 顺序变成 correctness 的一部分
- 多 worker / 测试隔离 / 热更新时的状态边界会变得模糊

### 4. 数据库基础设施层也是全局 singleton

`easysql_api/infrastructure/db.py` 里 engine 和 sessionmaker 也是模块级全局变量：

```python
_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None

def init_engine(uri: str) -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        return
```

对应代码位置：

- [easysql_api/infrastructure/db.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/infrastructure/db.py#L10)
- [easysql_api/infrastructure/db.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/infrastructure/db.py#L24)

这和上面的 `deps.py` 一起，构成了当前后端最核心的 runtime ownership 问题：资源虽然被“初始化”了，但没有被“显式拥有”。

### 5. `QueryService` 已经承担了过多职责

`QueryService` 目前同时做这些事：

- graph 缓存与 callback 缓存
- session 创建与状态更新
- follow-up / fork / branch 逻辑
- turn 与 message 持久化协调
- stream 事件输出
- graph 结果整理与 state sanitize

例如下面几个片段都在同一个类里：

```python
class QueryService:
    @property
    def graph(self) -> Any:
        if self._graph is None:
            self._graph = build_graph()
        return self._graph
```

```python
async def fork_session_with_branch_context(...):
    ...
```

```python
async def stream_query(...):
    ...
```

对应代码位置：

- [easysql_api/services/query_service.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/services/query_service.py#L24)
- [easysql_api/services/query_service.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/services/query_service.py#L164)
- [easysql_api/services/query_service.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/services/query_service.py#L666)
- [easysql_api/services/query_service.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/services/query_service.py#L902)

这类“大服务类”在项目早期很常见，但一旦分支会话、图状态、few-shot、chart、streaming 都往里长，它就会成为后续演进的瓶颈。

### 6. 仓储边界总体是对的，但持久化模型开始反向影响领域逻辑

仓储接口本身是存在的：

- [SessionRepository](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/domain/repositories/session_repository.py)

但具体实现里，`_map_session()` 要靠 `generated_sql` 和消息顺序去猜 turn/message 的对应关系：

```python
for turn in session.turns:
    ...
    for idx, message in enumerate(remaining):
        if message.generated_sql == turn.final_sql:
            matched = message
            ...
    if matched is None and remaining:
        matched = remaining.pop(0)
```

对应代码位置：

- [easysql_api/infrastructure/persistence/session_repository.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/infrastructure/persistence/session_repository.py#L320)

这说明持久化层没有直接表达领域真正依赖的关系，只能在读取时做启发式恢复。这不是致命 bug，但已经是明确的架构信号：模型结构落后于业务行为。

## 与更成熟实践的对比

和更成熟的 FastAPI 项目相比，EasySQL 当前的差异不在“有没有 router/service/repository”，而在“这些对象由谁拥有”。

更稳定的做法通常是：

- `lifespan` 负责初始化共享资源
- 资源挂在 `app.state` 或显式应用容器上
- request 依赖从 `Request.app.state` 中解析
- service 不依赖模块级可变单例

EasySQL 目前已经做对了第一步：用了 `lifespan`。但第二步和第三步还没落地，所以运行时模型依旧偏隐式。

另一个很重要的对比是：`SchemaPipeline` 的写法其实比 API 路径更稳。它的资源 ownership 是局部对象化的，而 API 路径则回退成了 service locator + singleton。这意味着项目内部已经同时存在“更健康的 ownership 风格”和“更脆弱的 ownership 风格”两套范式。

## 主要问题

### 1. 最高优先级问题：运行时资源 ownership 过于隐式

不是说现在代码一定会立刻出错，而是它的正确性依赖很多隐含前提：

- `lifespan` 必须先跑
- 全局变量必须先设好
- cache invalidation 必须手动做到位
- 多进程或测试场景下不能出现状态漂移

这类问题在功能增加后会越来越难追。

### 2. `QueryService` 已经超出单一职责

从代码体量和职责范围来看，它同时承担：

- orchestration
- persistence coordination
- transport shaping
- runtime cache access

这会让后续任何一个功能都倾向继续往这个类里堆。

### 3. backend config 与 runtime graph / service 的耦合已经穿透分层

从目录看，好像 config、service、graph 是分开的；但运行时看，它们通过全局对象、cache、sanitized state 和 callback 连接在了一起。换句话说，当前后端“看起来分层”，但运行时边界还不够硬。

### 4. 持久化层开始承担“猜测业务关系”的工作

当仓储实现需要猜 turn 和 message 的映射时，说明领域模型和持久化模型已经出现了偏差。继续往后发展，会在 branch、few-shot、history replay 上不断积累隐性复杂度。

## 优化方向

### 方向 1：把全局 service locator 改成 app-scoped ownership

最小可行改法不是重写架构，而是把：

- repository
- config service
- graph-related shared service

放到 `app.state` 或显式应用容器中，然后让依赖函数从 request/app 上取，而不是从模块级变量上取。

### 方向 2：拆分 `QueryService`

建议至少拆成三块：

- graph runtime 协调
- session / turn / message 持久化协调
- API streaming / response shaping

这样后续改 graph、改 persistence、改 stream 协议时，不会都落在一个类里。

### 方向 3：显式建模 message 与 turn 的关系

不要继续让仓储层用 SQL 文本和顺序去猜映射关系。最好在存储模型里直接表达 turn 对应的 message，后续 branch 和 few-shot 的正确性会稳定很多。

### 方向 4：统一 backend 里的资源管理风格

建议把 `SchemaPipeline` 这一侧“局部 ownership、分阶段 orchestration”的风格，抽象成后端的默认范式；避免 API 路径继续强化“全局 singleton + setter/getter”这条线。

## 建议为何成立

这些建议不是为了“让架构更漂亮”，而是因为现在的问题已经体现在代码里：

- `deps.py` 和 `db.py` 证明 runtime ownership 过于依赖全局状态
- `QueryService` 证明 orchestration 与 transport 已经混在一起
- `session_repository.py` 证明存储模型没有跟上领域关系

换句话说，当前真正的风险不是少了某一层，而是：

> 运行时状态和资源 ownership 太隐式，导致系统演进会越来越依赖上下文记忆，而不是依赖显式结构。

## 优先级与待确认问题

优先级建议：

- `P0`：去掉 `deps.py` / `db.py` 这条全局 service locator 路径
- `P1`：拆分 `QueryService`
- `P1`：把 runtime config refresh 做成显式生命周期机制
- `P2`：给 message / turn 建立直接关系，去掉启发式恢复

待确认问题：

- 这个 API 未来是否会跑多 worker / 多进程？
- 运行时配置热更新是不是刚需？如果不是，很多复杂度可以显著下降。
- session store 的 schema readiness 是否希望由应用自检负责，而不是完全依赖外部手工迁移？
