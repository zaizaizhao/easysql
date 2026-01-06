# Chat Conversation

Note: _This is purely the output of the chat conversation and does not contain any raw data, codebase snippets, etc. used to generate the output._

### User Input

目前项目中已经完成了context层的构建，下一步应该就是集成llm了，是否需要以agent的形式来构建llm层，如果我需要在用户query的时候实现HITL,多次反问用户，来生成更详细的query呢？那么这个llm层是不是要同时支持用户query的完善生成，sql的生成，同时我也会对生成的sql进行tool的调用，以此让llm通过调用mc或者tool的形式来校验sql，请你详细阅读当前项目的实现，在仔细分析我上述方案的可行性，给出llm层的技术选型（使用什么技术、框架），给出详细的可行性分析，直接告诉我就行

### Planner Response

我来详细阅读当前项目的实现，然后为您分析 LLM 层的技术选型和可行性。

*Listed directory [easysql](file:///Users/zhucaiyunxiaodi/Downloads/easysql) *

*Listed directory [easysql](file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql) *

*Listed directory [context](file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/context) *

*Listed directory [retrieval](file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/retrieval) *

*Viewed [templates.py](file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/context/templates.py) *

*Viewed [requirements.txt](file:///Users/zhucaiyunxiaodi/Downloads/easysql/requirements.txt) *

*Viewed [builder.py](file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/context/builder.py) *

*Viewed [schema_retrieval.py](file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/retrieval/schema_retrieval.py) *

*Viewed [llm_filter.py](file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/retrieval/llm_filter.py) *

*Viewed [models.py](file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/context/models.py) *

*Viewed [config.py](file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/config.py) *

*Viewed [main.py](file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/main.py) *

### Planner Response

我已经仔细阅读了项目的当前实现。让我为您详细分析 LLM 层的技术选型和可行性。

---

## 📊 当前项目架构分析

您的项目已经实现了一个完整的 **Text2SQL** 的前半部分：

```
Schema Extraction → Neo4j/Milvus存储 → Retrieval检索 → Context构建 → (待实现) LLM层
```

**关键组件**：
- [SchemaRetrievalService](cci:2://file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/retrieval/schema_retrieval.py:99:0-358:9): 多阶段过滤流水线（Milvus语义搜索 → FK扩展 → 语义过滤 → Bridge保护 → LLM过滤）
- [ContextBuilder](cci:2://file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/context/builder.py:14:0-237:22): 将 retrieval 结果组装成 prompt（system + user）
- [PromptTemplate](cci:2://file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/context/templates.py:38:0-134:21): 模板管理，支持 YAML 自定义
- [LLMFilter](cci:2://file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/retrieval/llm_filter.py:45:0-230:13): 已有的简单 LLM 调用（用于表过滤）

---

## 🎯 您的需求分析

您需要 LLM 层支持 **三个核心场景**：

| 场景 | 描述 | 交互模式 |
|------|------|----------|
| **Query 完善** | HITL 多轮反问，澄清用户意图 | 多轮对话 |
| **SQL 生成** | 基于 context 生成 SQL | 单次生成 |
| **SQL 校验** | 通过 Tool/MCP 调用验证 SQL 正确性 | Agent式工具调用 |

---

## ✅ 可行性分析

### 方案：**LangGraph Agent 架构**

**强烈推荐使用 LangGraph**，理由如下：

#### 1. **HITL（Human-in-the-Loop）支持** ✅
```
LangGraph 原生支持 interrupt_before/interrupt_after
可以在任意节点暂停，等待用户输入，完美适配多轮反问
```

#### 2. **多场景统一** ✅
```python
# 伪代码示意
graph = StateGraph(EasySQLState)
graph.add_node("clarify_query", clarify_agent)      # Query完善
graph.add_node("generate_sql", sql_generator)       # SQL生成
graph.add_node("validate_sql", sql_validator)       # SQL校验（调用Tool）
graph.add_node("human_review", human_review_node)   # HITL节点
```

#### 3. **Tool/MCP 调用** ✅
```
- LangGraph 可绑定 LangChain Tools
- 可以轻松接入 MCP（Model Context Protocol）服务
- SQL 校验可以通过 Tool 执行真实查询验证
```

#### 4. **与现有架构兼容** ✅
```
您的 ContextBuilder 已经输出 system_prompt + user_prompt
可以直接作为 LangGraph 节点的输入
LLMFilter 可复用其 OpenAI 客户端配置
```

---

## 🛠 技术选型建议

### 核心框架

| 组件 | 推荐方案 | 理由 |
|------|----------|------|
| **Agent框架** | **LangGraph** | 原生 HITL、状态持久化、可视化调试 |
| **LLM客户端** | **LangChain ChatModel** | 统一接口，支持 DeepSeek/OpenAI/本地模型 |
| **Tool定义** | **LangChain Tools** | 标准化工具定义，支持 Pydantic Schema |
| **MCP集成** | **langchain-mcp-adapters** | LangChain 官方 MCP 适配器 |
| **状态管理** | **LangGraph Checkpointer** | 支持对话历史持久化 |

### 为什么不选择其他方案？

| 方案 | 不推荐理由 |
|------|-----------|
| **原生 OpenAI SDK** | 无 HITL 支持，状态管理需自己实现 |
| **LangChain Agent** | 已被 LangGraph 取代，功能受限 |
| **AutoGen** | 更适合多Agent协作，对您的场景过重 |
| **CrewAI** | 同上，且不如 LangGraph 灵活 |

---

## 🏗 推荐的 LLM 层架构

```
┌─────────────────────────────────────────────────────────────┐
│                     EasySQLAgent (LangGraph)                │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  Clarifier  │───▶│ SQLGenerator│───▶│  Validator  │     │
│  │   (HITL)    │◀───│             │◀───│   (Tools)   │     │
│  └──────┬──────┘    └─────────────┘    └──────┬──────┘     │
│         │                                      │            │
│         ▼                                      ▼            │
│  ┌─────────────┐                       ┌─────────────┐     │
│  │ HumanInput  │                       │ MCP/Tools   │     │
│  │   Node      │                       │ (SQL执行)   │     │
│  └─────────────┘                       └─────────────┘     │
├─────────────────────────────────────────────────────────────┤
│  State: query, context, sql, validation_result, messages   │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│              现有模块 (保持不变)                              │
├─────────────────────────────────────────────────────────────┤
│  SchemaRetrievalService → ContextBuilder → PromptTemplate  │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 需要新增的依赖

```txt
# requirements.txt 追加
langgraph>=0.2.0
langchain>=0.3.0
langchain-openai>=0.2.0      # 或 langchain-community
langchain-mcp-adapters>=0.1.0  # MCP集成（可选）
```

---

## 🎯 结论

| 问题 | 答案 |
|------|------|
| 是否需要 Agent 形式？ | **是**，LangGraph 是最佳选择 |
| 能否支持 HITL？ | **能**，LangGraph 原生支持 interrupt |
| 能否统一 Query完善/SQL生成/SQL校验？ | **能**，三者作为 Graph 的不同节点 |
| 能否集成 MCP/Tool？ | **能**，通过 LangChain Tools 或 langchain-mcp-adapters |
| 与现有架构兼容性？ | **高**，ContextBuilder 输出可直接作为输入 |

**建议下一步**：如果您认可这个方案，我可以为您设计详细的 `implementation_plan.md`，包含具体的目录结构、类设计和代码示例。

### User Input

请讲讲你的更详细的llm层的设计思路

### Planner Response

好的，让我详细讲解 LLM 层的设计思路。

## 🏗 LLM 层详细设计

### 1. 核心设计理念：**状态机 + 分阶段处理**

整个 LLM 层本质是一个**有状态的工作流**，每个阶段有明确的输入输出和转移条件：

```
┌────────────────────────────────────────────────────────────────────────┐
│                          EasySQLAgent 状态图                            │
└────────────────────────────────────────────────────────────────────────┘

     START
       │
       ▼
┌─────────────┐    需要澄清     ┌─────────────┐
│   analyze   │───────────────▶│   clarify   │◀──┐
│   query     │                │   (HITL)    │───┘ 继续澄清
└─────────────┘                └──────┬──────┘
       │                              │
       │ 意图清晰                      │ 用户确认
       ▼                              ▼
┌─────────────────────────────────────────────┐
│              retrieve_schema                 │
│     (调用现有 SchemaRetrievalService)         │
└─────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│              build_context                   │
│        (调用现有 ContextBuilder)              │
└─────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│              generate_sql                    │
│            (LLM 生成 SQL)                    │
└─────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│              validate_sql                    │
│      (Tool调用：语法检查、执行验证)            │
└─────────────────────────────────────────────┘
         │                    │
         │ 验证通过            │ 验证失败
         ▼                    ▼
      ┌──────┐         ┌─────────────┐
      │ END  │         │   repair    │───▶ 重新生成
      └──────┘         └─────────────┘
```

---

### 2. 状态设计（State Schema）

LangGraph 的核心是**状态驱动**，所有节点共享一个状态对象：

```python
from typing import TypedDict, Annotated, Literal, Optional, List
from langgraph.graph.message import add_messages

class EasySQLState(TypedDict):
    """Agent 全局状态"""
    
    # === 输入阶段 ===
    raw_query: str                    # 用户原始问题
    clarified_query: Optional[str]    # 澄清后的问题
    clarification_needed: bool        # 是否需要澄清
    clarification_questions: List[str] # 待询问的问题
    
    # === 检索阶段 ===
    db_name: Optional[str]            # 目标数据库
    retrieval_result: Optional[dict]  # SchemaRetrievalService 结果
    
    # === 上下文阶段 ===
    context_output: Optional[dict]    # ContextBuilder 输出
    
    # === SQL 生成阶段 ===
    generated_sql: Optional[str]      # 生成的 SQL
    sql_explanation: Optional[str]    # SQL 解释
    
    # === 验证阶段 ===
    validation_result: Optional[dict] # 验证结果
    validation_passed: bool           # 是否通过
    error_message: Optional[str]      # 错误信息
    
    # === 对话历史（HITL 核心） ===
    messages: Annotated[list, add_messages]  # 支持消息累积
    
    # === 控制流 ===
    retry_count: int                  # 重试次数
    max_retries: int                  # 最大重试
    current_step: str                 # 当前步骤（调试用）
```

---

### 3. 各节点详细设计

#### 3.1 Query 分析节点（AnalyzeQuery）

**目的**：判断用户 query 是否足够清晰，是否需要 HITL 澄清

```python
class AnalyzeQueryNode:
    """
    分析用户 query 的完整性和清晰度
    
    判断逻辑：
    1. 是否存在歧义？（如"销售额"可能指多个字段）
    2. 时间范围是否明确？
    3. 聚合粒度是否明确？（按天？按月？）
    4. 过滤条件是否完整？
    """
    
    ANALYZE_PROMPT = """分析以下用户问题，判断是否需要进一步澄清：

用户问题：{query}

请判断：
1. 问题是否足够清晰可以直接生成 SQL？
2. 如果不够清晰，需要追问哪些问题？

返回 JSON 格式：
{
  "is_clear": true/false,
  "clarification_questions": ["问题1", "问题2"],
  "reasoning": "判断理由"
}
"""
    
    def __call__(self, state: EasySQLState) -> dict:
        # 调用 LLM 分析
        result = self.llm.invoke(
            self.ANALYZE_PROMPT.format(query=state["raw_query"])
        )
        
        parsed = json.loads(result.content)
        
        return {
            "clarification_needed": not parsed["is_clear"],
            "clarification_questions": parsed.get("clarification_questions", []),
            "current_step": "analyze_query"
        }
```

#### 3.2 HITL 澄清节点（Clarify）

**目的**：多轮对话收集用户意图，这是整个设计的**核心创新点**

```python
class ClarifyNode:
    """
    Human-in-the-Loop 澄清节点
    
    工作流程：
    1. 向用户提出澄清问题
    2. 等待用户回答（interrupt）
    3. 更新 clarified_query
    4. 判断是否还需要继续澄清
    """
    
    CLARIFY_PROMPT = """基于用户的原始问题和对话历史，生成最终的完善后问题：

原始问题：{raw_query}

对话历史：
{conversation}

请输出一个完整的、不含歧义的问题描述，用于后续的 SQL 生成。
"""
    
    def __call__(self, state: EasySQLState) -> dict:
        questions = state["clarification_questions"]
        
        if questions:
            # 返回需要用户回答的问题
            # LangGraph 会在这里 interrupt
            return {
                "messages": [
                    AIMessage(content=f"为了更准确地理解您的需求，请回答以下问题：\n" + 
                              "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions)))
                ],
                "current_step": "waiting_for_user"
            }
        else:
            # 所有问题已回答，生成最终 query
            conversation = format_messages(state["messages"])
            clarified = self.llm.invoke(
                self.CLARIFY_PROMPT.format(
                    raw_query=state["raw_query"],
                    conversation=conversation
                )
            )
            
            return {
                "clarified_query": clarified.content,
                "clarification_needed": False,
                "current_step": "clarification_complete"
            }
```

**LangGraph HITL 配置**：
```python
# 在 clarify 节点设置 interrupt
graph.add_node("clarify", clarify_node)
graph = graph.compile(
    interrupt_before=["clarify"],  # 在 clarify 前暂停等待用户输入
    checkpointer=MemorySaver()     # 状态持久化
)
```

#### 3.3 Schema 检索节点（RetrieveSchema）

**目的**：复用现有的 [SchemaRetrievalService](cci:2://file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/retrieval/schema_retrieval.py:99:0-358:9)

```python
class RetrieveSchemaNode:
    """
    调用现有的 Schema 检索服务
    """
    
    def __init__(self, retrieval_service: SchemaRetrievalService):
        self.service = retrieval_service
    
    def __call__(self, state: EasySQLState) -> dict:
        query = state["clarified_query"] or state["raw_query"]
        
        result = self.service.retrieve(
            question=query,
            db_name=state.get("db_name")
        )
        
        return {
            "retrieval_result": result.__dict__,
            "current_step": "schema_retrieved"
        }
```

#### 3.4 Context 构建节点（BuildContext）

**目的**：复用现有的 [ContextBuilder](cci:2://file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/context/builder.py:14:0-237:22)

```python
class BuildContextNode:
    """
    调用现有的 Context 构建器
    """
    
    def __init__(self, context_builder: ContextBuilder):
        self.builder = context_builder
    
    def __call__(self, state: EasySQLState) -> dict:
        from easysql.retrieval.schema_retrieval import RetrievalResult
        from easysql.context.models import ContextInput
        
        # 重建 RetrievalResult 对象
        retrieval_result = RetrievalResult(**state["retrieval_result"])
        
        context_input = ContextInput(
            question=state["clarified_query"] or state["raw_query"],
            retrieval_result=retrieval_result,
            db_name=state.get("db_name")
        )
        
        output = self.builder.build(context_input)
        
        return {
            "context_output": {
                "system_prompt": output.system_prompt,
                "user_prompt": output.user_prompt,
                "total_tokens": output.total_tokens,
            },
            "current_step": "context_built"
        }
```

#### 3.5 SQL 生成节点（GenerateSQL）

**目的**：基于 context 生成 SQL

```python
class GenerateSQLNode:
    """
    生成 SQL 的核心节点
    """
    
    def __call__(self, state: EasySQLState) -> dict:
        context = state["context_output"]
        
        response = self.llm.invoke([
            SystemMessage(content=context["system_prompt"]),
            HumanMessage(content=context["user_prompt"])
        ])
        
        sql = self._extract_sql(response.content)
        
        return {
            "generated_sql": sql,
            "sql_explanation": response.content,
            "current_step": "sql_generated"
        }
    
    def _extract_sql(self, content: str) -> str:
        """从 LLM 输出中提取 SQL"""
        # 处理 markdown 代码块
        import re
        match = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content.strip()
```

#### 3.6 SQL 验证节点（ValidateSQL）— **Tool 调用核心**

**目的**：通过 Tool/MCP 验证生成的 SQL

```python
class ValidateSQLNode:
    """
    SQL 验证节点 - 支持多种验证方式
    
    验证策略：
    1. 语法验证（sqlparse）
    2. EXPLAIN 执行计划检查
    3. 实际执行验证（可选，危险）
    4. MCP 调用外部服务验证
    """
    
    def __init__(self, tools: List[BaseTool]):
        self.tools = {t.name: t for t in tools}
    
    def __call__(self, state: EasySQLState) -> dict:
        sql = state["generated_sql"]
        
        # 1. 语法检查
        syntax_result = self.tools["sql_syntax_check"].invoke({"sql": sql})
        if not syntax_result["valid"]:
            return {
                "validation_passed": False,
                "error_message": f"语法错误: {syntax_result['error']}",
                "current_step": "validation_failed"
            }
        
        # 2. EXPLAIN 检查
        explain_result = self.tools["sql_explain"].invoke({
            "sql": sql,
            "db_name": state.get("db_name")
        })
        if not explain_result["valid"]:
            return {
                "validation_passed": False,
                "error_message": f"执行计划错误: {explain_result['error']}",
                "current_step": "validation_failed"
            }
        
        return {
            "validation_passed": True,
            "validation_result": {
                "syntax": syntax_result,
                "explain": explain_result,
            },
            "current_step": "validation_passed"
        }
```

---

### 4. Tool 定义

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class SQLSyntaxCheckInput(BaseModel):
    sql: str = Field(description="SQL 语句")

class SQLExplainInput(BaseModel):
    sql: str = Field(description="SQL 语句")
    db_name: str = Field(description="数据库名称")

@tool(args_schema=SQLSyntaxCheckInput)
def sql_syntax_check(sql: str) -> dict:
    """检查 SQL 语法是否正确"""
    import sqlparse
    try:
        parsed = sqlparse.parse(sql)
        if not parsed or not parsed[0].tokens:
            return {"valid": False, "error": "空 SQL"}
        return {"valid": True, "error": None}
    except Exception as e:
        return {"valid": False, "error": str(e)}

@tool(args_schema=SQLExplainInput)
def sql_explain(sql: str, db_name: str) -> dict:
    """通过 EXPLAIN 检查 SQL 执行计划"""
    # 连接数据库执行 EXPLAIN
    try:
        engine = get_engine_for_db(db_name)
        with engine.connect() as conn:
            result = conn.execute(text(f"EXPLAIN {sql}"))
            plan = result.fetchall()
            return {"valid": True, "plan": plan, "error": None}
    except Exception as e:
        return {"valid": False, "error": str(e)}

@tool
def execute_sql_readonly(sql: str, db_name: str, limit: int = 10) -> dict:
    """执行 SQL 并返回结果（只允许 SELECT）"""
    if not sql.strip().upper().startswith("SELECT"):
        return {"success": False, "error": "只允许 SELECT 语句"}
    
    try:
        engine = get_engine_for_db(db_name)
        with engine.connect() as conn:
            result = conn.execute(text(f"{sql} LIMIT {limit}"))
            rows = result.fetchall()
            return {"success": True, "rows": rows, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

---

### 5. MCP 集成方案（可选）

如果您需要通过 MCP 调用外部服务进行验证：

```python
from langchain_mcp_adapters.tools import load_mcp_tools

# 加载 MCP Server 暴露的 Tools
mcp_tools = load_mcp_tools(
    server_params={
        "command": "npx",
        "args": ["-y", "@your-org/sql-validator-mcp"],
    }
)

# 将 MCP Tools 与普通 Tools 合并
all_tools = [sql_syntax_check, sql_explain, *mcp_tools]
```

---

### 6. 完整 Graph 构建

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

def build_easysql_agent(
    retrieval_service: SchemaRetrievalService,
    context_builder: ContextBuilder,
    llm: BaseChatModel,
    tools: List[BaseTool],
) -> CompiledGraph:
    """构建完整的 EasySQL Agent"""
    
    graph = StateGraph(EasySQLState)
    
    # 添加节点
    graph.add_node("analyze", AnalyzeQueryNode(llm))
    graph.add_node("clarify", ClarifyNode(llm))
    graph.add_node("retrieve", RetrieveSchemaNode(retrieval_service))
    graph.add_node("build_context", BuildContextNode(context_builder))
    graph.add_node("generate_sql", GenerateSQLNode(llm))
    graph.add_node("validate_sql", ValidateSQLNode(tools))
    graph.add_node("repair_sql", RepairSQLNode(llm))
    
    # 设置入口
    graph.set_entry_point("analyze")
    
    # 条件边：分析后判断是否需要澄清
    graph.add_conditional_edges(
        "analyze",
        lambda s: "clarify" if s["clarification_needed"] else "retrieve"
    )
    
    # 澄清后进入检索
    graph.add_edge("clarify", "retrieve")
    
    # 线性流程
    graph.add_edge("retrieve", "build_context")
    graph.add_edge("build_context", "generate_sql")
    graph.add_edge("generate_sql", "validate_sql")
    
    # 验证后的分支
    graph.add_conditional_edges(
        "validate_sql",
        lambda s: END if s["validation_passed"] else "repair_sql"
    )
    
    # 修复后重新验证
    graph.add_conditional_edges(
        "repair_sql",
        lambda s: END if s["retry_count"] >= s["max_retries"] else "validate_sql"
    )
    
    # 编译，启用 HITL
    return graph.compile(
        interrupt_before=["clarify"],  # HITL 断点
        checkpointer=MemorySaver()
    )
```

---

### 7. 使用示例

```python
# 初始化
agent = build_easysql_agent(
    retrieval_service=retrieval_service,
    context_builder=ContextBuilder.default(),
    llm=ChatOpenAI(model="deepseek-chat"),
    tools=[sql_syntax_check, sql_explain],
)

# 第一次调用（可能在 clarify 处暂停）
config = {"configurable": {"thread_id": "user-session-123"}}
result = agent.invoke(
    {"raw_query": "查询销售额", "max_retries": 3, "retry_count": 0},
    config
)

# 如果需要澄清，result 会包含 clarification_questions
# 用户回答后继续执行
if result.get("clarification_needed"):
    # 用户提供了答案
    result = agent.invoke(
        {"messages": [HumanMessage(content="我要查询2024年1月的销售额")]},
        config  # 同一个 thread_id 继续
    )

# 最终结果
print(result["generated_sql"])
print(result["validation_result"])
```

---

### 8. 目录结构建议

```
easysql/
├── llm/                          # 新增 LLM 层
│   ├── __init__.py
│   ├── state.py                  # EasySQLState 定义
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── analyze.py            # 分析节点
│   │   ├── clarify.py            # HITL 澄清节点
│   │   ├── retrieve.py           # Schema 检索节点
│   │   ├── build_context.py      # Context 构建节点
│   │   ├── generate_sql.py       # SQL 生成节点
│   │   ├── validate_sql.py       # SQL 验证节点
│   │   └── repair_sql.py         # SQL 修复节点
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── syntax_check.py       # 语法检查 Tool
│   │   ├── explain.py            # EXPLAIN Tool
│   │   └── execute.py            # 执行验证 Tool
│   ├── prompts/
│   │   ├── analyze.py            # 分析 Prompt
│   │   ├── clarify.py            # 澄清 Prompt
│   │   └── repair.py             # 修复 Prompt
│   └── agent.py                  # Graph 构建入口
├── context/                      # 现有模块（保持不变）
├── retrieval/                    # 现有模块（保持不变）
└── ...
```

---

这就是完整的 LLM 层设计思路。核心优势是：
1. **模块化**：每个节点职责单一，易于测试和替换
2. **可控性**：通过条件边精确控制流程
3. **HITL 友好**：原生支持多轮对话
4. **与现有代码兼容**：复用 [SchemaRetrievalService](cci:2://file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/retrieval/schema_retrieval.py:99:0-358:9) 和 [ContextBuilder](cci:2://file:///Users/zhucaiyunxiaodi/Downloads/easysql/easysql/context/builder.py:14:0-237:22)

LangGraph 1.0+ 官方文档调研报告
1. HITL（Human-in-the-Loop）实现：与 llm_plan.md 对比
llm_plan.md 中的描述（第 77-81 行、396-404 行）：

python
# llm_plan.md 的方案
graph = graph.compile(
    interrupt_before=["clarify"],  # 在 clarify 前暂停等待用户输入
    checkpointer=MemorySaver()
)
LangGraph 1.0+ 官方最新推荐：

特性	llm_plan.md 描述	LangGraph 1.0+ 官方文档
中断机制	interrupt_before/interrupt_after	✅ 仍支持，但推荐使用 interrupt() 函数
恢复方式	未明确描述	使用 Command(resume=...) 恢复
中断位置	节点级别静态定义	可在任意节点内部动态调用
🔄 关键变化：LangGraph 1.0+ 推荐使用 interrupt() 函数替代静态的 interrupt_before

新的官方推荐写法：

python
from langgraph.types import interrupt, Command
def clarify_node(state: State):
    # 动态中断，payload 会返回给调用方
    user_response = interrupt({
        "question": "请问您要查询哪个时间段的销售额？",
        "options": ["本月", "本年", "自定义"]
    })
    
    # 用户回答后，代码从这里继续执行
    return {"clarified_query": user_response}
# 恢复执行
config = {"configurable": {"thread_id": "session-123"}}
result = graph.invoke({"raw_query": "查询销售额"}, config)
# 检查中断
if result.get("__interrupt__"):
    # 用户回答后恢复
    resumed = graph.invoke(
        Command(resume="我要查询2024年的销售额"),
        config
    )
✅ 结论：llm_plan.md 的 HITL 设计思路完全正确，但代码写法需要更新。interrupt_before 仍可用（适合调试和静态断点），但生产环境推荐使用 interrupt() 函数，更灵活。

2. Middleware 是否需要集成？
答案：不是必需的，但推荐用于高级场景

LangGraph 1.0 引入了 middleware hooks（2025年底正式发布），但这是可选的高级功能：

Hook	作用	您的场景是否需要
before_model	在 LLM 调用前修改 state	🟡 可选：用于 token 限制、消息历史管理
modify_model_request	修改发送给 LLM 的请求	🟡 可选：动态切换模型或修改 tools
after_model	LLM 调用后处理输出	🟡 可选：输出验证、安全检查
对于您的 EasySQLAgent，目前不需要 middleware。您的需求完全可以通过标准的节点（nodes）实现：

Query 分析 → analyze_query 节点
SQL 验证 → validate_sql 节点
只有当您需要跨节点的通用逻辑（如统一的日志记录、安全检查）时才需考虑 middleware。

3. Graph 构建流程：与 llm_plan.md 对比
llm_plan.md 中的构建方式（第 639-698 行）：

python
graph = StateGraph(EasySQLState)
graph.add_node("analyze", AnalyzeQueryNode(llm))
graph.add_node("clarify", ClarifyNode(llm))
graph.set_entry_point("analyze")
graph.add_conditional_edges("analyze", lambda s: ...)
graph.add_edge("clarify", "retrieve")
return graph.compile(interrupt_before=["clarify"], checkpointer=MemorySaver())
LangGraph 1.0+ 官方 Quickstart 的构建方式：

python
from langgraph.graph import StateGraph, START, END
builder = StateGraph(MessagesState)
builder.add_node("llm_call", llm_call)
builder.add_node("tool_node", tool_node)
builder.add_edge(START, "llm_call")  # 使用 START 常量
builder.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
builder.add_edge("tool_node", "llm_call")
agent = builder.compile()
✅ 对比结论：

方面	llm_plan.md	LangGraph 1.0+	状态
StateGraph 使用	✅ 一致	✅ 一致	✅
add_node	✅ 一致	✅ 一致	✅
add_edge	✅ 一致	✅ 一致	✅
add_conditional_edges	✅ 一致	✅ 一致	✅
入口点	set_entry_point()	add_edge(START, ...)	🔄 需更新
compile()	✅ 一致	✅ 一致	✅
唯一需要修改的：set_entry_point("analyze") 应改为 add_edge(START, "analyze")

4. DBHub MCP 集成：替代自建 SQL Tool
DBHub 是什么：

由 Bytebase 开发的 零依赖、token 高效的 MCP Server
支持 PostgreSQL、MySQL、MariaDB、SQL Server、SQLite
提供两个核心 Tool：
execute_sql：执行 SQL 查询
search_objects：搜索数据库 schema
集成方案：使用 langchain-mcp-adapters 将 DBHub 的 MCP Tools 转换为 LangChain Tools

python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition
from langchain.chat_models import init_chat_model
# 1. 配置 DBHub MCP 连接
client = MultiServerMCPClient({
    "dbhub": {
        "url": "http://localhost:8080/mcp",  # DBHub HTTP 端口
        "transport": "http",
    }
})
# 2. 获取 MCP Tools（execute_sql, search_objects）
tools = await client.get_tools()
# 3. 构建 LangGraph Agent
model = init_chat_model("deepseek-chat")
def call_model(state: MessagesState):
    response = model.bind_tools(tools).invoke(state["messages"])
    return {"messages": response}
builder = StateGraph(MessagesState)
builder.add_node("call_model", call_model)
builder.add_node("tools", ToolNode(tools))  # 这里的 tools 包含 DBHub 的 execute_sql
builder.add_edge(START, "call_model")
builder.add_conditional_edges("call_model", tools_condition)
builder.add_edge("tools", "call_model")
graph = builder.compile()
DBHub 启动命令：

bash
# Docker 方式
docker run --rm --init \
  --name dbhub \
  --publish 8080:8080 \
  bytebase/dbhub \
  --transport http \
  --port 8080 \
  --dsn "postgres://user:password@host:5432/dbname"
# 或 NPM 方式
npx @bytebase/dbhub@latest --transport http --port 8080 --dsn "mysql://..."
✅ 集成可行性：

问题	答案
能否替代自建 SQL Tool？	✅ 完全可以，DBHub 提供 execute_sql 和 search_objects
是否需要改代码？	🔄 需要修改 ValidateSQLNode，把自定义 Tool 替换为 DBHub MCP Tools
安全性如何？	✅ DBHub 支持只读模式、行数限制、查询超时
多数据库支持？	✅ 支持 PostgreSQL/MySQL/MariaDB/SQL Server/SQLite
需要注意的点：

DBHub 需要单独启动（Docker 或 NPX）
您的 Agent 通过 HTTP 与 DBHub 通信
加 langchain-mcp-adapters 到 requirements.txt
5. 总结：llm_plan.md 需要更新的内容
项目	原始设计	更新建议
HITL 中断	interrupt_before=["clarify"]	改用节点内 interrupt() 函数
恢复机制	未描述	添加 Command(resume=...) 恢复逻辑
入口点	set_entry_point("analyze")	改为 add_edge(START, "analyze")
SQL 验证 Tool	自定义 sql_syntax_check、sql_explain	可选替换为 DBHub 的 execute_sql（验证用 EXPLAIN）
Middleware	未使用	不需要，当前设计已足够
依赖版本	langgraph>=0.2.0	建议升级至 langgraph>=1.0.0
更新后的示例代码：

python
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
class EasySQLState(TypedDict):
    raw_query: str
    clarified_query: Optional[str]
    messages: Annotated[list, add_messages]
    # ... 其他字段
def clarify_node(state: EasySQLState):
    """HITL 澄清节点 - 使用新的 interrupt() API"""
    response = interrupt({
        "question": "请问您要查询的具体时间范围是？",
        "context": state["raw_query"]
    })
    return {
        "clarified_query": response,
        "messages": [AIMessage(content=f"好的，我理解您要查询: {response}")]
    }
# 构建 Graph
builder = StateGraph(EasySQLState)
builder.add_node("analyze", analyze_node)
builder.add_node("clarify", clarify_node)
builder.add_node("retrieve", retrieve_node)
builder.add_node("generate_sql", generate_sql_node)
builder.add_node("validate_sql", validate_sql_node)
builder.add_edge(START, "analyze")  # ✅ 新写法
builder.add_conditional_edges("analyze", route_after_analyze)
builder.add_edge("clarify", "retrieve")
builder.add_edge("retrieve", "generate_sql")
builder.add_edge("generate_sql", "validate_sql")
builder.add_conditional_edges("validate_sql", route_after_validate)
graph = builder.compile(checkpointer=MemorySaver())
# 使用
config = {"configurable": {"thread_id": "user-123"}}
result = graph.invoke({"raw_query": "查询销售额"}, config)
if result.get("__interrupt__"):
    # 用户回答后恢复
    result = graph.invoke(Command(resume="2024年全年"), config)