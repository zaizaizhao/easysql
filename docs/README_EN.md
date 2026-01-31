<div align="center">
  <img src="../easysql_web/public/easysql_icon.svg" width="120" height="120" alt="EasySQL Logo" />
  <h1>EasySQL</h1>
  <p><strong>DDD Domain Modeling × Knowledge Graph Reasoning × Vector Semantic Search</strong></p>
  <p>A continuously evolving, increasingly accurate enterprise-grade intelligent SQL engine</p>

  <a href="https://zaizaizhao.github.io/easysql/">Website</a> •
  <a href="../README.md">中文</a> •
  <a href="https://github.com/zaizaizhao/easysql">GitHub</a>

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

</div>

> ⚠️ **Work in Progress** - This project is under active development. APIs and features may change. Feedback welcome!

---

## Interface Preview

![EasySQL Interface](images/example_pic1.png)

---

## Why EasySQL?

Enterprise databases often contain hundreds of tables. Directly feeding schemas to LLMs causes:
- Token explosion, exceeding context limits
- Similar table names lead to wrong selections
- Lost foreign key relationships result in incorrect JOINs

EasySQL's approach:
1. Build **knowledge graphs with Neo4j** to store table structures and foreign key relationships for relation reasoning
2. Use **Milvus for vector semantic search** to deeply understand business intent
3. Orchestrate agents with **LangGraph**: Intent understanding → Schema retrieval → SQL generation → Validation & repair
4. Support **DDD domain modeling** for AI to understand business context
5. **Few-Shot learning** + user feedback loop for continuous improvement

## Core Features

- **DDD Business Context**: Deep understanding of business domains, automatically identifying core concepts like orders, inventory, and customers
- **Knowledge Graph Driven**: Neo4j precisely captures foreign keys, indexes, and constraints for optimal JOIN paths
- **Few-Shot Learning**: Quickly adapts to specific business scenarios with minimal labeled samples
- **Gets Smarter Over Time**: Continuously learns from user feedback, steadily improving query accuracy
- **Composable Architecture**: Retrieval, generation, validation, and repair components are independently configurable
- **Semantic Vector Search**: "Monthly sales" automatically maps to order_detail, beyond simple keyword matching
- **Self-Healing Execution**: Automatic diagnosis and repair of SQL errors for higher end-to-end success rates
- **Full Database Support**: MySQL, PostgreSQL, Oracle, SQL Server - one solution for all
- **Full Observability**: LangFuse integration for token usage and latency metrics at a glance

## Quick Start

### Requirements

- Python 3.10+
- Neo4j 4.0+
- Milvus 2.0+

### Installation

```bash
git clone https://github.com/zaizaizhao/easysql.git
cd easysql
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
# Edit .env with the minimum required settings
```

Minimum configuration (to run the full Text2SQL pipeline end-to-end):
```ini
# Source database (at least one DB_<NAME>_*)
DB_HIS_TYPE=mysql
DB_HIS_HOST=localhost
DB_HIS_PORT=3306
DB_HIS_USER=root
DB_HIS_PASSWORD=your_mysql_password
DB_HIS_DATABASE=your_db

# Neo4j & Milvus
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
MILVUS_URI=http://localhost:19530

# LLM (choose one provider)
OPENAI_API_KEY=sk-xxx
# For Google/Anthropic, set both *_API_KEY and *_LLM_MODEL
# GOOGLE_API_KEY=xxx
# GOOGLE_LLM_MODEL=gemini-1.5-pro
# ANTHROPIC_API_KEY=xxx
# ANTHROPIC_LLM_MODEL=claude-3-5-sonnet-20241022
```

### Initialize Schema

First run syncs database schema to Neo4j and Milvus:

```bash
python main.py run
```

### Start Services

```bash
# API server
uvicorn easysql_api.app:app --port 8000 --reload

# Frontend (optional)
cd easysql_web && npm install && npm run dev
```

Visit http://localhost:8000/docs for API documentation.

## Project Structure

```
easysql/           # Core logic
  ├── config.py    # Configuration management
  ├── llm/         # LangGraph Agent
  ├── retrieval/   # Schema retrieval
  └── extractors/  # Database schema extraction
easysql_api/       # FastAPI endpoints
easysql_web/       # React frontend
```

## Development

```bash
# Formatting
black .
ruff check . --fix

# Type checking
mypy easysql

# Testing
pytest
```

## License

Apache 2.0
