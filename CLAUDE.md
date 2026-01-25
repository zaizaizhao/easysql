# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EasySQL is an enterprise Text2SQL solution that handles databases with hundreds of tables. It uses:
- **Neo4j** to store table relationships/foreign keys as a knowledge graph
- **Milvus** for semantic vector search to find relevant tables
- **LangGraph** to orchestrate SQL generation with validation and self-repair

## Common Commands

### Python Backend

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e ".[dev]"        # Dev tools (pytest, black, ruff, mypy)

# Run schema extraction pipeline (sync DB schema to Neo4j + Milvus)
python main.py run

# Start API server
uvicorn easysql_api.app:app --port 8000 --reload

# Linting and formatting
ruff check .                   # Lint
ruff check . --fix             # Auto-fix
black .                        # Format

# Type checking
mypy easysql

# Testing
pytest                         # All tests
pytest tests/test_file.py::test_name  # Single test
pytest -v -x --tb=short        # Verbose, stop on first failure
```

### Web Frontend

```bash
cd easysql_web
npm install
npm run dev       # Vite dev server
npm run build     # Production build
npm run lint      # ESLint
```

## Architecture

### Data Flow

```
User Query → Milvus (semantic search) → Neo4j (FK expansion) → Filter Chain → LLM → SQL → Validation → [Repair if needed]
```

### Key Directories

- `easysql/llm/` - LangGraph agent with nodes for each pipeline stage
  - `agent.py` - Graph assembly and routing logic
  - `state.py` - `EasySQLState` TypedDict that flows through the graph
  - `nodes/` - Individual processing nodes (retrieve, generate_sql, validate_sql, repair_sql)
  - `tools/` - SQL execution (MCP or SQLAlchemy)
- `easysql/retrieval/` - Schema retrieval with filter chain pattern (semantic → bridge → LLM filters)
- `easysql/extractors/` - Database schema extraction via SQLAlchemy
  - `metadata_providers/` - DB-specific extractors (MySQL, PostgreSQL, Oracle, SQL Server)
- `easysql/context/` - Prompt construction with modular sections
- `easysql/embeddings/` - Embedding service (local sentence-transformers, OpenAI, or TEI)
- `easysql_api/` - FastAPI REST endpoints
- `easysql_web/` - React + TypeScript + Zustand frontend

### LangGraph Modes

1. **Fast Mode**: Direct SQL generation without HITL
2. **Plan Mode**: Schema analysis with optional user clarification
3. **Agent Mode**: ReAct loop with iterative SQL generation and tool use

### LLM Selection Priority

1. Google Gemini (if `GOOGLE_API_KEY` set)
2. Anthropic Claude (if `ANTHROPIC_API_KEY` set)
3. OpenAI (fallback)

### State Persistence

- Development: `MemorySaver`
- Production: `AsyncPostgresSaver` (configure via `CHECKPOINTER_BACKEND=postgres`)

## Configuration

Copy `.env.example` to `.env`. Key settings:

```ini
# Target database to analyze
DB_HIS_TYPE=mysql
DB_HIS_HOST=localhost
DB_HIS_DATABASE=your_db

# Infrastructure
NEO4J_URI=bolt://localhost:7687
MILVUS_URI=http://localhost:19530

# LLM API keys (priority: Google > Anthropic > OpenAI)
OPENAI_API_KEY=sk-xxx

# Query mode
QUERY_MODE=plan  # or fast
```

## Code Style

- Line length: 100 (black, ruff)
- Type annotations required for all functions
- Use `str | None` syntax (not `Optional[str]`)
- Ruff rules: E, F, W, I, N, UP, B, C4
