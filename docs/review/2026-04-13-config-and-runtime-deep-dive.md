# 配置与运行时深度分析

## 问题定义

EasySQL 现在已经不只是“读 `.env` 的配置系统”了，而是一个混合了环境变量、嵌套 settings、数据库持久化 override、运行时 cache invalidation 的半控制面系统。它能工作，但代价是 operator 很难回答这些关键问题：

- 当前到底哪一层配置最权威
- API 改了配置以后，哪些对象立即生效，哪些对象需要重建
- `--env`、环境变量、DB override 之间谁覆盖谁

这也是这篇会排到第一名的原因：配置权威不清楚时，系统表面上“可调”，实际却很容易出现“看起来更新成功了，但运行时仍然没变”的情况。

## 关键代码证据

### 1. 顶层 `Settings` 之外，还存在多个独立的 `BaseSettings`

`CheckpointerConfig`、`LangfuseConfig`、`LLMConfig` 都是单独的 `BaseSettings`：

```python
class CheckpointerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

class LangfuseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
```

同时顶层还有一个 `Settings(BaseSettings)`：

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )
```

对应代码：

- [easysql/config.py](../easysql/config.py)

这说明当前系统不是“一个 settings 对象统一装配全部来源”，而是“顶层 settings + 多个嵌套 settings loader”并存。问题在于，这些 loader 看起来像一个整体，实际上可能在不同入口、不同生命周期下分别读取环境。

### 2. `get_settings()` 在实例创建后再打运行时 override

当前配置读取流程不是纯声明式 source chain，而是先创建 `Settings()`，再对实例做路径级覆写：

```python
@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    with _RUNTIME_OVERRIDES_LOCK:
        for path, value in _RUNTIME_OVERRIDES.items():
            _apply_override_path(settings, path, value)
    return settings
```

而 `_apply_override_path()` 最终是直接 `setattr`：

```python
def _apply_override_path(settings: "Settings", path: str, value: Any) -> None:
    ...
    setattr(target, leaf, value)
```

对应代码：

- [easysql/config.py](../easysql/config.py)

这带来的问题很具体：

- override 并不是走完整的 settings source 解析过程
- 修改是“实例后 patch”，不是“新实例按统一优先级构建”
- 一旦某些子对象内部还保留自己的加载逻辑，就很难一眼判断 override 是否真的覆盖到了最终运行值

### 3. API 启动后会把 DB 中的配置再灌进内存 override

`ConfigService.bootstrap_from_db()` 会把 DB 中配置装入 `_RUNTIME_OVERRIDES`，然后清掉 `get_settings()` 缓存：

```python
async def bootstrap_from_db(self) -> None:
    rows = await self._repository.load_all()
    overrides: dict[str, Any] = {}
    ...
    replace_runtime_overrides(overrides)
    get_settings.cache_clear()
```

对应代码：

- [easysql_api/services/config_service.py](../easysql_api/services/config_service.py)

这意味着 API 启动之后，真实运行值已经不再只是 `.env` 与环境变量，而是：

- 初始环境配置
- 运行时内存 override
- DB 持久化配置回灌

本质上，这已经是个 runtime control plane 了，只是还没有把自己的 precedence model 明文写出来。

### 4. 配置项虽然有 `invalidate_tags`，但运行时依赖图仍然不完全显式

`config_schema.py` 里已经开始给配置项打失效标签：

```python
_spec(
    "llm",
    "temperature",
    "llm.temperature",
    "float",
    validator=_validate_temperature,
    invalidate_tags={"settings"},
)
_spec(
    "llm", "use_agent_mode", "llm.use_agent_mode", "bool", invalidate_tags={"settings", "graph"}
)
```

对应代码：

- [easysql_api/services/config_schema.py](../easysql_api/services/config_schema.py)

这说明项目已经意识到“改配置不等于自动生效”，有些配置要连带失效 graph / settings cache。但当前仍有两个现实问题：

- 依赖图是人工维护的，容易遗漏
- 配置项与 runtime object 的对应关系没有集中呈现

例如只看 schema，很难立刻知道：

- 哪些配置改了要重建 compiled graph
- 哪些配置改了只要清 `get_settings()` cache
- 哪些配置其实根本不该做 live update

### 5. session 存储 URI 的 fallback 本身就在放大“隐式权威”

`Settings.get_session_postgres_uri()` 里，如果没设置 `session_postgres_uri`，会回落到 checkpointer 的 Postgres URI：

```python
def get_session_postgres_uri(self) -> str | None:
    if self.session_postgres_uri:
        return self.session_postgres_uri
    if self.checkpointer.is_postgres():
        logger.warning(
            "SESSION_POSTGRES_URI not set; falling back to checkpointer Postgres URI"
        )
        return self.checkpointer.postgres_uri
    return None
```

对应代码：

- [easysql/config.py](../easysql/config.py)

这段代码当然很实用，但它也说明 operator contract 正在被弱化：

- 文档层面你以为 session store 和 checkpointer 是两套配置
- 代码层面它们又可能自动合流

如果没有明确文档和启动时诊断信息，这类 fallback 很容易让使用者误判系统实际依赖。

## 根因分析

根因是配置系统按功能点逐步演进，但没有在中途停下来统一 precedence model：

- 最早是 `.env` / 环境变量
- 后来为了组织清晰，加入了嵌套 settings
- 再后来为了在线可调，引入 DB 持久化 override
- 最后为了让 live update 真正生效，又加了 cache invalidation

每一步都合理，但组合起来就形成了“部分显式、部分隐式”的控制面。

## 为什么这是优先级第一

配置系统是跨主题问题：

- LangGraph 的 graph rebuild 依赖它
- 后端 service ownership 依赖它
- infra / observability 的 operator contract 也依赖它

如果配置权威不清楚，那么很多功能表面上都能工作，但会出现最难排查的一类问题：

- 改了配置，服务没完全刷新
- 两个入口读到的配置不一样
- 文档告诉你的和运行时实际行为不一致

这类问题的破坏性在于它不会立刻报错，而是以“系统偶尔不符合预期”的形式出现。

## 目标方向

建议目标是把当前系统收敛成一个真正可解释的配置模型：

- 只有顶层 `Settings` 是 `BaseSettings`
- 内嵌配置段落改成普通 `BaseModel`
- precedence 明确写成：默认值 -> `.env` -> 环境变量 -> DB persisted overrides
- live update 不再靠实例后 patch，而是产出一个新的、完整校验过的 settings 结果
- 每个可编辑配置项都明确声明依赖哪些 runtime object

这不要求你们删掉 config API；恰恰相反，这是让 config API 真正可靠的前提。

## 分阶段优化建议

### 第一阶段：先把当前真实 precedence 写清楚并补测试

优先补三类回归测试：

- `--env` 是否真的覆盖到所有相关配置
- DB override 与环境变量冲突时谁优先
- 修改某个 config key 后，graph / settings / callback cache 是否按预期失效

这一步的价值很高，因为你们会第一次把“当前系统到底怎么读配置”真正固定下来。

### 第二阶段：收敛到单一 `BaseSettings`

把嵌套 `BaseSettings` 改成普通模型，由顶层 `Settings` 一次性完成装配。这样能消掉现在“顶层是一个 source，子模型又像另一套 source”的歧义。

### 第三阶段：把 runtime override 做成可验证的重建流程

无论最终实现是：

- 自定义 settings source
- 还是 “读取 sources 后重建一个新 Settings 实例”

核心原则都应该是：override 进入的是统一构建流程，而不是后置 `setattr` patch。

### 第四阶段：明确 persisted config 的产品定位

必须选清楚它到底是：

- 安全的 tuning surface
- 还是完整的 runtime control plane

这两个方向对 UI、权限、缓存失效、operator 预期都完全不同。现在代码有点介于两者之间，这正是歧义的来源。

## 迁移风险与约束

最大风险是改 precedence 以后影响现有部署。因为线上可能已经有人依赖：

- 环境变量兜底
- session/checkpointer URI 合流
- 某些配置项“改了立即生效”的现状

所以迁移时不应该直接“重写配置系统”，而应该先把当前行为用测试钉住，再逐步替换底层实现。

另一个现实约束是多 worker 部署。如果未来要多进程运行，仅靠进程内 `_RUNTIME_OVERRIDES` 是不够的。这个问题不一定马上解决，但应尽早体现在设计判断里，否则“live config”只会在单进程场景下看起来成立。
