# 后端架构深度分析

## 问题定义

EasySQL 的目录分层看起来是合理的，但运行时 ownership 不够显式。资源创建、服务实例、graph 缓存、数据库引擎都在不同层里以“全局变量 + lazy cache”的方式分散存在，最后导致系统在静态目录上像分层架构，在运行时却更像 service locator 驱动的共享进程状态。

这就是为什么这篇会进入优先级前三：它不是一个单点 bug，而是很多后续问题的放大器。只要 ownership 不清楚，配置刷新、graph 重建、测试隔离、后续服务拆分都会变难。

## 关键代码证据

### 1. API 依赖是通过模块级全局变量暴露的

`deps.py` 里直接维护全局仓储和全局配置服务：

```python
_session_repository: SessionRepository | None = None
_config_service: ConfigService | None = None

def get_session_repository_dep() -> SessionRepository:
    if _session_repository is None:
        raise RuntimeError("SessionRepository not initialized. Ensure app lifespan initialized it.")
    return _session_repository

def set_session_repository(repository: SessionRepository) -> None:
    global _session_repository
    _session_repository = repository
```

对应代码：

- [easysql_api/deps.py](../easysql_api/deps.py)

这类写法的问题不是“不能跑”，而是把启动顺序硬编码进了正确性条件：

- 生命周期必须先执行 `set_session_repository`
- 请求阶段才能安全读 `get_session_repository_dep()`

这意味着运行时 owner 不是 `app`，而是“某个先前执行过的模块级 setter”。一旦测试并发、热重载、多 worker、手动重建 service，边界就会开始变得脆弱。

### 2. 基础设施层的 engine / sessionmaker 也是进程级单例

数据库基础设施同样采用模块级全局：

```python
_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None

def init_engine(uri: str) -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        return
    normalized = _normalize_async_uri(uri)
    _engine = create_async_engine(normalized, pool_pre_ping=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
```

对应代码：

- [easysql_api/infrastructure/db.py](../easysql_api/infrastructure/db.py)

这说明仓库当前把“连接资源所有权”定义成了“整个 Python 进程共享一个 engine”。如果以后要支持：

- 更细粒度的测试隔离
- 按 app 实例切换连接
- 更明确的 startup / shutdown 行为

这套模式就会越来越难扩展。

### 3. `QueryService` 既是编排器，又缓存 graph / callbacks，还通过全局默认实例对外暴露

`QueryService` 内部自己缓存 graph 和 callbacks：

```python
class QueryService:
    def __init__(self, repository: SessionRepository) -> None:
        self._graph: Any = None
        self._repo = repository
        self._callbacks: list[Any] | None = None

    @property
    def graph(self) -> Any:
        if self._graph is None:
            self._graph = build_graph()
        return self._graph
```

同时模块底部还维护一个 `_default_service`：

```python
_default_service: QueryService | None = None

def get_query_service(repository: SessionRepository) -> QueryService:
    global _default_service
    if _default_service is None:
        _default_service = QueryService(repository=repository)
    elif _default_service._repo is not repository:
        _default_service = QueryService(repository=repository)
    return _default_service
```

对应代码：

- [easysql_api/services/query_service.py](../easysql_api/services/query_service.py)

这段代码说明 `QueryService` 当前至少承担了四种角色：

- graph runtime owner
- session repository coordinator
- Langfuse callback owner
- API 查询流程编排器

职责一旦集中到这个程度，后面不管是拆分 branch 逻辑、拆分 SSE transport，还是做 graph cache invalidation，都会先撞到 `QueryService` 这个大对象。

### 4. 仓库内部其实已经存在两种不同的 ownership 风格

CLI pipeline 入口里是相对局部、明确的资源风格：

```python
def _run_pipeline(...):
    if env_file:
        settings = load_settings(env_file)
    else:
        settings = get_settings()
    ...
    pipeline = SchemaPipeline(settings)
    stats = pipeline.run(...)
```

对应代码：

- [easysql/main.py](../easysql/main.py)

这说明项目并不是不会写清晰 ownership，只是两条后端路径用了两种不同风格：

- pipeline 路径偏局部对象 ownership
- API 路径偏模块级 service locator ownership

这会让团队在继续开发时缺少一个稳定默认值。新代码到底应该挂到 app lifecycle 上，还是继续往 module global 里塞，答案现在并不统一。

## 根因分析

根因不是“作者不会分层”，而是系统是在功能不断累加中长出来的：

- 一开始 API 面很小，用全局变量最快
- 后面接入 LangGraph、session branch、chart、config control plane 后，更多责任继续堆进现有 service
- 目录结构保留了 clean architecture 的样子，但运行时 ownership 没有同步收敛

因此你看到的不是混乱，而是“演进到中期但尚未统一 runtime model”的典型状态。

## 为什么这件事优先级高

这项问题的杠杆非常大，因为它会直接影响其他几个 review 主题：

- 配置系统想做 live reload，先要知道谁拥有 graph 与 service
- LangGraph 想把 checkpoint state 设成唯一权威，先要知道 service 边界在哪里
- 可观测性想加 request / dependency span，先要知道资源从哪里创建、谁来销毁

换句话说，后端 ownership 不是一个“纯架构洁癖”问题，而是其他演进工作的前置条件。

## 目标架构方向

建议的目标不是“重写后端”，而是把 ownership 显式化：

- 资源在 `lifespan` 或显式 app container 中创建
- request dependency 从 `request.app.state` 或容器中解析
- `QueryService` 缩成一个主编排服务，而不是运行时所有能力的聚合体
- graph runtime、callback owner、session persistence coordinator 逐步拆开

可以保留现有目录结构，不需要大改文件树，重点是把运行时真相收回来。

## 分阶段优化建议

### 第一阶段：先去掉最脆弱的全局 ownership

- 把 `SessionRepository`、`ConfigService`、engine/sessionmaker 的 owner 收敛到 app lifecycle
- 让 dependency 函数从 app context 读取，而不是依赖模块级 setter

这一阶段做完，最直接的收益是：

- startup/shutdown 更容易验证
- 测试替换依赖更容易
- 多实例/多 worker 语义更清楚

### 第二阶段：拆 `QueryService`

建议至少拆成三个方向：

- graph runtime coordinator
- session / turn persistence coordinator
- transport / stream adapter

现在很多 bug 一旦进到 `QueryService`，定位会变成“要看这个大对象几十个方法”。拆完之后，graph 与 persistence 的边界会清楚很多。

### 第三阶段：把关系型持久化模型中的“隐含业务规则”收回领域层

当前仓储层已经承担了不少 session / turn / message 的重建逻辑。后续应尽量让：

- 数据模型显式表达关系
- repository 做读写
- 业务规则放回 service / domain

否则基础设施层会越来越像“半个业务层”。

## 迁移风险与约束

最大风险是改动会碰到 API 主链路，因为 `QueryService` 现在就在核心路径上。要降低风险，顺序应该是：

1. 先把 ownership 移到 app scope，但外部依赖接口不变
2. 再拆 `QueryService` 内部职责
3. 最后再清理多余的全局缓存和历史兼容逻辑

还要注意一个现实约束：如果你们短期内仍然是单进程部署，这些问题不会天天爆炸，但越往后拖，拆分成本越高。因为每新增一个 service、一个 cache、一个 runtime hook，都会继续沿着现在这条 ownership 路径累积技术债。
