<div align="center">

# 🚀 EasySQL

**企业级 Text2SQL 语义检索引擎**
<br>
*Enterprise-Grade Text-to-SQL Engine powered by Knowledge Graph & RAG*

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-orange)](https://github.com/langchain-ai/langgraph)

[特性](#-核心特性) • [理念](#-设计理念) • [快速开始](#-快速开始) • [API 文档](#-api-服务) • [配置](#-配置指南)

</div>

---

## 📖 简介 | Introduction

**EasySQL** 是一个面向企业复杂业务场景的 Text2SQL 解决方案。不同于简单的 Prompt Engineering，EasySQL 采用 **"Schema Linkage Graph"** (架构链接图谱) 技术，结合 Neo4j 知识图谱与 Milvus 向量检索，解决大规模数据库表结构下的语义歧义问题。

核心引擎基于 **LangGraph** 构建，采用 Agentic Workflow（多智能体工作流），具备**查询规划**、**语义澄清**、**SQL 自修正**及**代码上下文感知**能力。

## ✨ 核心特性 | Features

### 🧠 混合检索架构 (Hybrid Retrieval)
- **知识图谱增强**: 利用 Neo4j 存储表结构、外键拓扑及业务实体关系，实现精确的 Schema 召回。
- **语义向量检索**: 集成 Milvus/FAISS，支持对表名、字段描述及业务元数据的语义模糊搜索。
- **DDD 代码上下文**: *[独家]* 支持检索业务层代码（如 Entity 定义、Enum 枚举），让 LLM 理解 "代码中的业务逻辑" 而不仅仅是数据库结构。

### 🤖 智能 Agent 工作流
- **LangGraph 驱动**: 内置 Planning -> Generation -> Validation -> Repair 闭环工作流。
- **自愈机制**: 生成的 SQL 若执行报错，Agent 会自动分析错误日志并进行修正重试。
- **多模型路由**: 智能路由 Google Gemini (Flash/Pro)、Claude 3.5 或 GPT-4o，平衡成本与性能。

### 🔌 企业级连接性
- **多源数据库**: 原生支持 `MySQL`, `PostgreSQL`, `Oracle`, `SQL Server`.
- **全链路监控**: 集成 **LangFuse**，提供详细的 Trace 追踪、Token 消耗统计及延迟分析。
- **Schema 自动同步**: 自动化 Pipeline 定期扫描数据库变更并更新知识图谱。

---

## 🏗 设计理念 | Philosophy

> *"The gap between natural language and SQL is not a translation problem — it's a context problem."*

EasySQL 的核心洞察：**传统 Text2SQL 失败的根源不在于 LLM 能力不足，而在于上下文的缺失与碎片化。** 

我们构建了一套 **Context-First** 的检索增强架构——将数据库 Schema 编织成知识图谱，将业务逻辑沉淀为向量语义，将代码上下文注入推理链路。当用户提出一个模糊的业务问题时，系统不是在"猜测"SQL，而是在"理解"意图、"召回"知识、"推演"路径。

这不是又一个 Prompt Wrapper，这是 **Semantic Infrastructure for Enterprise Data**。

---

## ⚡ 快速开始 | Quick Start

### 1. 环境准备

确保 Python 3.10+ 环境，并安装依赖：

```bash
git clone https://github.com/your-org/easysql.git
cd easysql
pip install -r requirements.txt
```

### 2. 基础设施启动

你需要运行 Neo4j 和 Milvus。推荐使用 Docker Compose (自备) 或本地安装。

### 3. 配置环境

复制并修改环境变量配置文件：

```bash
cp .env.example .env
```

核心配置项（`.env`）：
```ini
# 数据库连接
DB_HIS_TYPE=mysql
DB_HIS_HOST=localhost
DB_HIS_DATABASE=his_db

# 向量与图谱
NEO4J_URI=bolt://localhost:7687
MILVUS_URI=http://localhost:19530

# LLM 模型
OPENAI_API_KEY=sk-...
QUERY_MODE=plan  # 开启 Agent 规划模式
```

### 4. 数据初始化 (Schema Ingestion)

运行 Pipeline 将数据库 Schema 提取并构建到 Neo4j 和 Milvus 中：

```bash
# 完整运行 (推荐)
python main.py run

# 仅提取 Schema，跳过写入 (调试用)
python main.py run --no-neo4j --no-milvus
```

### 5. 命令行测试

```bash
python examples/run_agent.py
```
*输入示例：* `查询本月挂号量最高的前3个科室`

---

## 🚀 API 服务 | API Server

EasySQL 提供基于 FastAPI 的高性能 REST 接口。

### 启动服务

```bash
uvicorn easysql_api.app:app --host 0.0.0.0 --port 8000 --reload
```

### 接口文档

启动后访问 Swagger UI： [http://localhost:8000/docs](http://localhost:8000/docs)

- `POST /api/v1/query`: 提交自然语言查询
- `GET /api/v1/sessions`: 获取历史会话
- `POST /api/v1/pipeline/sync`: 触发元数据同步

---

## 🔧 配置指南 | Configuration

EasySQL 支持高度定制化，通过 `easysql/config.py` 管理。

### 多模型策略
系统会根据 API Key 的存在情况自动选择最优模型，优先级如下：
1. **Google Gemini** (高性价比长文本)
2. **Anthropic Claude** (极强的逻辑推理)
3. **OpenAI GPT-4o** (通用基准)

### 代码上下文 (Code Context)
若需开启业务代码感知，请在 `.env` 中设置：
```ini
CODE_CONTEXT_ENABLED=true
CODE_CONTEXT_SUPPORTED_LANGUAGES=java,python
```
这将允许 Agent 在生成 SQL 时参考应用层的枚举定义和实体逻辑。

---

## 🤝 贡献 | Contributing

欢迎提交 Pull Request！在提交前，请确保通过本地的代码规范检查：

```bash
# 代码格式化
black .
ruff check . --fix

# 类型检查
mypy easysql
```

## 📄 许可证 | License

本项目采用 [MIT 许可证](LICENSE) 开源。
