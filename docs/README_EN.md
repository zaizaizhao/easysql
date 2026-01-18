<div align="center">

# 🚀 EasySQL

**Enterprise-Grade Text-to-SQL Semantic Retrieval Engine**
<br>
*Powered by Knowledge Graph & RAG*

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-orange)](https://github.com/langchain-ai/langgraph)

[Features](#-features) • [Philosophy](#-philosophy) • [Quick Start](#-quick-start) • [API Docs](#-api-server) • [Configuration](#-configuration)

**[🇨🇳 中文文档](../README.md)**

</div>

---

## 📖 Introduction

**EasySQL** is a Text2SQL solution designed for complex enterprise business scenarios. Unlike simple Prompt Engineering approaches, EasySQL adopts **"Schema Linkage Graph"** technology, combining Neo4j knowledge graphs with Milvus vector retrieval to resolve semantic ambiguity in large-scale database schemas.

The core engine is built on **LangGraph**, employing an Agentic Workflow (multi-agent workflow) with capabilities including **query planning**, **semantic clarification**, **SQL self-correction**, and **code context awareness**.

## ✨ Features

### 🧠 Hybrid Retrieval Architecture
- **Knowledge Graph Enhanced**: Utilizes Neo4j to store table structures, foreign key topology, and business entity relationships for precise schema recall.
- **Semantic Vector Search**: Integrates Milvus/FAISS for semantic fuzzy search on table names, field descriptions, and business metadata.
- **DDD Code Context**: *[Exclusive]* Supports retrieval of business layer code (such as Entity definitions, Enum enumerations), enabling LLMs to understand "business logic in code" beyond just database structures.

### 🤖 Intelligent Agent Workflow
- **LangGraph Driven**: Built-in Planning -> Generation -> Validation -> Repair closed-loop workflow.
- **Self-Healing Mechanism**: If generated SQL encounters execution errors, the Agent automatically analyzes error logs and performs correction retries.
- **Multi-Model Routing**: Intelligent routing between Google Gemini (Flash/Pro), Claude 3.5, or GPT-4o, balancing cost and performance.

### 🔌 Enterprise-Grade Connectivity
- **Multi-Source Databases**: Native support for `MySQL`, `PostgreSQL`, `Oracle`, `SQL Server`.
- **Full-Chain Monitoring**: Integrated with **LangFuse**, providing detailed trace tracking, token consumption statistics, and latency analysis.
- **Automatic Schema Sync**: Automated Pipeline periodically scans database changes and updates the knowledge graph.

---

## 🏗 Philosophy

> *"The gap between natural language and SQL is not a translation problem — it's a context problem."*

EasySQL's core insight: **The root cause of traditional Text2SQL failures is not insufficient LLM capability, but missing and fragmented context.**

We've built a **Context-First** retrieval-augmented architecture—weaving database schemas into knowledge graphs, distilling business logic into vector semantics, and injecting code context into the reasoning chain. When users pose ambiguous business questions, the system doesn't "guess" SQL; it "understands" intent, "recalls" knowledge, and "derives" paths.

This is not another Prompt Wrapper. This is **Semantic Infrastructure for Enterprise Data**.

---

## ⚡ Quick Start

### 1. Environment Setup

Ensure Python 3.10+ environment and install dependencies:

```bash
git clone https://github.com/your-org/easysql.git
cd easysql
pip install -r requirements.txt
```

### 2. Infrastructure Startup

You need to run Neo4j and Milvus. Docker Compose (self-provided) or local installation is recommended.

### 3. Configure Environment

Copy and modify the environment variable configuration file:

```bash
cp .env.example .env
```

Core configuration items (`.env`):
```ini
# Database connection
DB_HIS_TYPE=mysql
DB_HIS_HOST=localhost
DB_HIS_DATABASE=his_db

# Vector & Graph
NEO4J_URI=bolt://localhost:7687
MILVUS_URI=http://localhost:19530

# LLM Model
OPENAI_API_KEY=sk-...
QUERY_MODE=plan  # Enable Agent planning mode
```

### 4. Data Initialization (Schema Ingestion)

Run Pipeline to extract database Schema and build into Neo4j and Milvus:

```bash
# Full run (recommended)
python main.py run

# Schema extraction only, skip writing (for debugging)
python main.py run --no-neo4j --no-milvus
```

### 5. Command Line Test

```bash
python examples/run_agent.py
```
*Example input:* `Query the top 3 departments with the highest registration volume this month`

---

## 🚀 API Server

EasySQL provides high-performance REST interfaces based on FastAPI.

### Start Service

```bash
uvicorn easysql_api.app:app --host 0.0.0.0 --port 8000 --reload
```

### API Documentation

After startup, access Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

- `POST /api/v1/query`: Submit natural language query
- `GET /api/v1/sessions`: Get session history
- `POST /api/v1/pipeline/sync`: Trigger metadata synchronization

---

## 🔧 Configuration

EasySQL supports high customization, managed through `easysql/config.py`.

### Multi-Model Strategy
The system automatically selects the optimal model based on API Key availability, with the following priority:
1. **Google Gemini** (cost-effective for long texts)
2. **Anthropic Claude** (excellent logical reasoning)
3. **OpenAI GPT-4o** (general benchmark)

### Code Context
To enable business code awareness, set in `.env`:
```ini
CODE_CONTEXT_ENABLED=true
CODE_CONTEXT_SUPPORTED_LANGUAGES=java,python
```
This allows the Agent to reference application layer enum definitions and entity logic when generating SQL.

---

## 🤝 Contributing

Pull Requests are welcome! Before submitting, please ensure your code passes local style checks:

```bash
# Code formatting
black .
ruff check . --fix

# Type checking
mypy easysql
```

## 📄 License

This project is open-sourced under the [Apache License 2.0](../LICENSE).
