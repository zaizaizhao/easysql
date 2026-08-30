# 配置与运行时评审

## 范围与核心判断

本文关注 EasySQL 的配置系统与运行时配置行为，主要包括：

- `.env` / 环境变量 / CLI `--env`
- `Settings` 与嵌套配置模型
- API 启动时的持久化配置加载
- 配置控制面（config API）
- live override 对 graph / node cache 的影响

核心判断是：这个项目已经有了“看起来像一个配置系统”的东西，但还没有形成一个真正清晰的一致性模型。现在至少存在四种配置权威来源：

- 顶层 `Settings`
- 嵌套 `BaseSettings`
- DB 持久化 override
- 运行时环境变量副作用

这会直接影响 operator 对“当前到底以谁为准”的理解，也会影响 live config change 是否真的生效。

## 当前实现（结合代码）

### 1. 文档和 CLI 入口已经有第一层漂移

`docs/ENVIRONMENT.md` 仍然写着：

```bash
python main.py run --env /path/to/.env
```

但当前 CLI 实现里并没有 `run` 子命令，真正的 `--env` 是挂在 callback 和 `config` 命令上的：

```python
@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    env_file: Optional[Path] = typer.Option(None, "--env", "-e", ...)
):
    ...
```

对应代码位置：

- [docs/ENVIRONMENT.md](/Users/zhaoyanan/Downloads/demo/easysql/docs/ENVIRONMENT.md#L6)
- [easysql/main.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/main.py#L27)
- [easysql/main.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/main.py#L138)

这不是小问题，因为它说明 operator contract 已经和实际配置加载路径不完全一致。

### 2. 顶层 `Settings` 是一个配置源，但不是唯一配置源

顶层 `Settings` 使用 `BaseSettings`，并从 `.env` 和环境变量读取：

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )
```

对应代码位置：

- [easysql/config.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/config.py#L315)

但问题在于，`LLMConfig`、`LangfuseConfig`、`CheckpointerConfig` 也都是单独的 `BaseSettings`：

```python
class CheckpointerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", ...)

class LangfuseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", ...)

class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", ...)
```

对应代码位置：

- [easysql/config.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/config.py#L131)
- [easysql/config.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/config.py#L194)
- [easysql/config.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/config.py#L224)

这意味着当前系统不是“一个 `Settings` 从所有 source 中统一装配”，而更像是“一个顶层 settings + 多个嵌套 settings loader 并存”。

### 3. API 启动后又引入了 DB 持久化 override 这一层 authority

FastAPI 启动时，`ConfigService.bootstrap_from_db()` 会把 DB 中的持久化配置加载进全局 override map：

```python
async def bootstrap_from_db(self) -> None:
    rows = await self._repository.load_all()
    overrides: dict[str, Any] = {}
    ...
    replace_runtime_overrides(overrides)
    get_settings.cache_clear()
```

对应代码位置：

- [easysql_api/services/config_service.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/services/config_service.py#L44)

而 `get_settings()` 在返回时又会把 override 逐个打到实例上：

```python
@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    with _RUNTIME_OVERRIDES_LOCK:
        for path, value in _RUNTIME_OVERRIDES.items():
            _apply_override_path(settings, path, value)
    return settings
```

对应代码位置：

- [easysql/config.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/config.py#L582)

这说明：

- 配置不是在模型构造阶段一次性决定
- 而是在模型构造后，再通过路径赋值进行二次修改

这就是当前配置系统最核心的不透明点之一。

### 4. live override 的 invalidate 范围并不总是和真实运行时对象一致

`CONFIG_SPEC_LIST` 为每个可编辑 key 定义了 invalidate tags。例如：

```python
_spec(
    "llm", "use_agent_mode", "llm.use_agent_mode", "bool",
    invalidate_tags={"settings", "graph"}
)

_spec(
    "llm", "temperature", "llm.temperature", "float",
    invalidate_tags={"settings"}
)
```

对应代码位置：

- [easysql_api/services/config_schema.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/services/config_schema.py#L146)
- [easysql_api/services/config_schema.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/services/config_schema.py#L182)

这里的问题非常具体：有些配置改动会真正影响 graph 和 node 内缓存的对象，但 invalidate tag 却只有 `settings` 没有 `graph`。这意味着 config API 可能告诉你“改成功了”，但运行时 compiled graph 未必真的吃到了新值。

### 5. config control plane 实际只覆盖了部分 runtime

从 `config_schema.py` 看，可持久化可编辑的范围主要覆盖：

- `llm`
- `retrieval`
- `few_shot`
- `code_context`
- `langfuse`

但并不覆盖：

- session store
- checkpointer
- source DB group
- embedding
- logging
- Neo4j / Milvus endpoint

对应代码位置：

- [easysql_api/services/config_schema.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/services/config_schema.py#L146)
- [easysql_api/services/config_schema.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql_api/services/config_schema.py#L415)

所以现在的 persisted config 更像“部分调参面板”，但因为它已经叫 config，又提供 `/config/editable`、`/config/overrides` 等接口，使用者很容易误以为它是完整控制面。

### 6. 文档写“必须有 SESSION_POSTGRES_URI”，代码却允许 fallback

这段代码很关键：

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

对应代码位置：

- [easysql/config.py](/Users/zhaoyanan/Downloads/demo/easysql/easysql/config.py#L439)

这说明代码里的 precedence 和文档里的说法已经不完全一致了。这个 fallback 可能是实用设计，但它一定要被清楚写出来，否则配置语义就不透明。

## 与更成熟实践的对比

更成熟的配置体系通常会尽量做到两件事：

1. **只有一个 authoritative settings boundary**
2. **source precedence 是显式定义的**

以 Pydantic Settings 的最佳实践来说，更推荐：

- 顶层一个 `BaseSettings`
- 嵌套结构用普通 `BaseModel`
- 如果要支持 DB override，就把它建模成显式 source 或 rebuild 流程

FastAPI 层面则更强调：

- `get_settings()` 作为唯一依赖入口
- 测试时用 dependency override 明确控制行为

EasySQL 当前的问题是：API 看起来是这样设计的，但内部真实行为已经不是“一个统一 settings 入口”，而是“统一入口 + 多个隐含来源 + post-hoc mutation”。

## 主要问题

### 1. 最高优先级问题：配置 authority 不唯一

如果你问“当前配置最终是谁说了算”，答案不是一句话能讲清的：

- `.env`
- env vars
- nested settings loader
- DB override
- runtime env side effect

这些一起存在时，就很难保证 operator、开发者和系统本身拥有同样的理解。

### 2. `--env` 很可能不是完整意义上的统一入口

从代码形态看，`Settings(_env_file=...)` 并不天然保证嵌套 `BaseSettings` 也用同一个 env file。这个问题如果不通过测试钉住，后面很容易演变成“顶层配置对了，nested LLM 配置却还是旧的”。

### 3. live override 只在“配置层”成功，不一定在“运行时对象层”成功

当前 config API 的成功语义，更像是：

- DB 已写入
- runtime override map 已更新
- 部分 cache 已失效

但这不等于：

- compiled graph 已重建
- node 内部缓存的 llm / config 已刷新
- 运行中实例一定用到了新值

### 4. persisted config 的边界没有讲清楚

目前它既不像“完整控制面”，也不只是“少量调参参数”。边界不清楚会直接造成运维和开发协作上的误解。

### 5. operator-facing 配置面噪音偏大

文档里同时出现：

- 已废弃命令写法
- not-yet-wired 变量
- 与真实运行路径不一致的说明

这些都会放大配置系统的学习成本。

## 优化方向

### 方向 1：只保留一个 authoritative settings boundary

建议把顶层 `Settings` 保留为唯一 `BaseSettings`，而把 `LLMConfig`、`LangfuseConfig`、`CheckpointerConfig` 改成普通嵌套模型。这样 precedence 才能真正统一下来。

### 方向 2：把 DB override 改成显式 source 或显式 rebuild

不要继续依赖“实例生成后再 setattr 覆盖”的模式。更稳的方式是：

- 通过显式 source 构建 settings
- 或在 override 变化后重建一个完整、重新校验过的 settings 实例

### 方向 3：live config change 必须绑定到真实 runtime object

需要明确：

- 哪些 key 影响 graph 结构
- 哪些 key 影响 llm instance
- 哪些 key 只影响普通读取逻辑

然后分别做：

- rebuild graph
- clear model cache
- or simple settings refresh

而不是一律只打 `settings` tag。

### 方向 4：明确 persisted config 的产品定位

必须先回答一个问题：

> persisted config 到底是“调参控制面”，还是“真正的运行时控制面”？

两种定位都可以，但不能同时模糊存在。

### 方向 5：压缩 operator-facing 配置噪音

建议把文档拆清楚：

- 当前真实支持的 runtime 配置
- 历史兼容 alias
- 未来预留但未接线的变量

## 建议为何成立

这些建议之所以重要，不是因为当前默认值多差，而是因为当前系统的**配置语义不够透明**。一旦一个系统里“设置成功”和“真正生效”不是同一件事，它后续的 debug 成本会迅速上升。

从代码上看，这个问题已经不是猜测：

- `Settings` 与嵌套 `BaseSettings` 并存
- `ConfigService` 在运行后再把值 patch 到实例上
- invalidate tag 与 graph/runtime object 影响范围不完全对应

这三点已经足够说明：当前配置系统需要的是“统一 authority 模型”，而不是继续加新的 config key。

## 优先级与待确认问题

优先级建议：

- `P0`：统一配置 source precedence
- `P0`：保证 live LLM / graph config change 真正作用到运行时对象
- `P1`：修正 docs 与 `.env.example`
- `P1`：明确 persisted config 是 tuning layer 还是 control plane
- `P2`：补 precedence 和 staleness 测试

待确认问题：

- session store / checkpointer 配置未来是否也要进入 API 控制面？
- 运行时配置变更是否要求立即生效，还是允许 restart-level consistency？
- process env 是否要保留为高优先级 emergency override？
