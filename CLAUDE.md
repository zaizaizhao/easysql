# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EasySQL is an enterprise Text2SQL solution that handles databases with hundreds of tables. It uses:
- **Neo4j** to store table relationships/foreign keys as a knowledge graph
- **Milvus** for semantic vector search to find relevant tables
- **LangGraph** to orchestrate SQL generation with validation and self-repair

## System Requirements

### Required Infrastructure

- **PostgreSQL 13+**: Control plane (session storage, configuration, LangGraph checkpoints)
  - Must enable `pgcrypto` extension
  - Recommended: 2GB+ memory, 10+ concurrent connections
- **Neo4j 4.0+**: Table relationship graph storage
- **Milvus 2.0+**: Vector search for semantic table retrieval

### Supported Target Databases (Data Plane)

EasySQL can analyze the following database types:
- MySQL 5.7+
- PostgreSQL 9.6+
- Oracle 11g+
- SQL Server 2012+

## Architecture

### Two-Tier Database Design

**IMPORTANT**: EasySQL uses a dual-database architecture:

1. **Control Plane (PostgreSQL-only)**
   - Purpose: Session persistence, configuration, LangGraph state
   - Database: PostgreSQL 13+ (required)
   - Tables: `easysql_sessions`, `easysql_messages`, `easysql_turns`, `easysql_configs`
   - Why PostgreSQL: JSONB for flexible state, ARRAY types, native UPSERT

2. **Data Plane (Multi-database)**
   - Purpose: Schema extraction, SQL generation, query execution
   - Databases: MySQL, PostgreSQL, Oracle, SQL Server
   - Components: `SQLAlchemySchemaExtractor`, `SqlAlchemyExecutor`

### Data Flow

```
User Query → Milvus (semantic search) → Neo4j (FK expansion) → Filter Chain → LLM → SQL → Validation → [Repair if needed]
```

### Connection Flow

```
User Request → FastAPI → SessionRepository (PostgreSQL async)
                      ↓
                LangGraph Agent → SqlAlchemyExecutor (Target DB sync)
                      ↓
            Schema Extraction → SQLAlchemySchemaExtractor (Target DB sync)
```

## Directory Structure

```
easysql/
├── easysql/                    # Core library
│   ├── llm/                    # LangGraph agent
│   │   ├── agent.py            # Graph assembly and routing
│   │   ├── state.py            # EasySQLState TypedDict
│   │   ├── nodes/              # Processing nodes (retrieve, generate_sql, validate_sql)
│   │   └── tools/              # SQL execution tools
│   ├── retrieval/              # Schema retrieval with filter chain
│   ├── extractors/             # Database schema extraction
│   │   └── metadata_providers/ # DB-specific extractors (MySQL, PostgreSQL, Oracle, MSSQL)
│   ├── context/                # Prompt construction
│   ├── embeddings/             # Embedding service
│   ├── readers/                # Neo4j/Milvus readers
│   ├── writers/                # Neo4j/Milvus writers
│   ├── repositories/           # Neo4j/Milvus repositories
│   └── utils/                  # Utilities (logger, etc.)
│
├── easysql_api/                # FastAPI REST API
│   ├── domain/                 # Domain layer (DDD)
│   │   ├── entities/           # Domain entities
│   │   ├── repositories/       # Repository interfaces
│   │   └── value_objects/      # Value objects
│   ├── infrastructure/         # Infrastructure layer
│   │   ├── db.py               # Database connection management
│   │   └── persistence/        # Data persistence
│   │       ├── models.py       # SQLAlchemy ORM models
│   │       ├── session_repository.py
│   │       └── config_repository.py
│   ├── services/               # Application services
│   ├── routers/                # FastAPI route handlers
│   ├── deps.py                 # Dependency injection
│   └── app.py                  # FastAPI application
│
├── easysql_web/                # React frontend
│   └── src/
│       ├── components/         # React components
│       ├── pages/              # Page components
│       ├── stores/             # Zustand state management
│       └── hooks/              # Custom React hooks
│
├── alembic/                    # Database migrations
│   └── versions/               # Migration scripts
│
├── tests/                      # Test suite
├── examples/                   # Example databases
├── docs/                       # Documentation
└── .env.example                # Environment configuration template
```

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

# Database migrations
alembic upgrade head           # Apply all migrations
alembic revision --autogenerate -m "description"  # Create new migration

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

## Code Style and Standards

### Python Code Style

**Formatting**:
- Line length: 100 characters (black, ruff)
- Use `black` for automatic formatting
- Use `ruff` for linting

**Type Annotations**:
- Type annotations **required** for all function signatures
- Use modern syntax: `str | None` (not `Optional[str]`)
- Use `list[str]` (not `List[str]`)
- Use `dict[str, Any]` (not `Dict[str, Any]`)

**Imports**:
- Use absolute imports
- Group imports: stdlib → third-party → local
- Sort imports alphabetically within groups

**Naming Conventions**:
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private members: `_leading_underscore`

**Ruff Rules**: E, F, W, I, N, UP, B, C4

### Database Code Standards

#### ORM Usage

**CRITICAL**: Follow these database access patterns:

1. **Control Plane (PostgreSQL)**:
   - Use **async SQLAlchemy** for all API persistence
   - Use `AsyncSession` with context managers
   - PostgreSQL-specific types are acceptable (JSONB, ARRAY, UUID)

2. **Data Plane (Target Databases)**:
   - Use **sync SQLAlchemy** for schema extraction and SQL execution
   - Use cross-database compatible types
   - Avoid database-specific syntax

#### Connection Management

**DO**:
```python
# ✅ Use DatabaseManager for all connections
from easysql_api.infrastructure.db_manager import get_db_manager

db_manager = get_db_manager()
async with db_manager.session() as session:
    # Work with session
    # Automatic commit/rollback
```

**DON'T**:
```python
# ❌ Don't create engines directly
engine = create_engine(connection_string)

# ❌ Don't manually manage transactions
await session.commit()  # Use context manager instead
```

#### Repository Pattern

**DO**:
```python
# ✅ Use dependency injection
class ConfigRepository:
    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def load_all(self) -> list[ConfigModel]:
        async with self._db_manager.session() as session:
            result = await session.execute(select(ConfigModel))
            return list(result.scalars().all())
            # Auto-commit on success, auto-rollback on exception
```

**DON'T**:
```python
# ❌ Don't use global sessionmaker
async with self._sessionmaker() as db:
    await db.execute(stmt)
    await db.commit()  # Manual transaction management
```

#### Database-Specific Code

**Control Plane (PostgreSQL-only)**:
```python
# ✅ PostgreSQL-specific features are OK for control plane
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, UUID

class SessionModel(Base):
    state: Mapped[dict | None] = mapped_column(JSONB)  # OK
    tables_used: Mapped[list[str] | None] = mapped_column(ARRAY(Text))  # OK
```

**Data Plane (Multi-database)**:
```python
# ✅ Use cross-database compatible types
from sqlalchemy import JSON, Text

# Use Inspector for schema reflection (works across all databases)
inspector = inspect(engine)
tables = inspector.get_table_names()
```

**NEVER**:
```python
# ❌ Don't use database-specific syntax in data plane
stmt = stmt.on_conflict_do_update(...)  # PostgreSQL-only!
```

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
# Control Plane (Session Storage) - PostgreSQL Required
SESSION_BACKEND=postgres
SESSION_POSTGRES_URI=postgresql://user:pass@localhost:5432/easysql

# Target Database to Analyze (Data Plane)
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

# Checkpointer (LangGraph state)
CHECKPOINTER_BACKEND=postgres  # or memory
```

## Testing Guidelines

### Unit Tests

- Place tests in `tests/` directory
- Mirror source structure: `tests/test_<module>.py`
- Use pytest fixtures for common setup
- Mock external dependencies (Neo4j, Milvus, LLM APIs)

### Integration Tests

- Test database interactions with real PostgreSQL (use test database)
- Test LangGraph workflows end-to-end
- Use `pytest-asyncio` for async tests

### Test Naming

```python
def test_<function_name>_<scenario>_<expected_result>():
    # Example: test_upsert_config_when_exists_updates_value
    pass
```

## Common Patterns

### Async Context Managers

```python
# ✅ Always use async context managers for database sessions
async with db_manager.session() as session:
    # Work with session
    pass  # Auto-commit/rollback
```

### Error Handling

```python
# ✅ Let exceptions propagate, context manager handles rollback
async with db_manager.session() as session:
    result = await session.execute(stmt)
    # If exception occurs, automatic rollback
```

### Logging

```python
from easysql.utils.logger import get_logger

logger = get_logger(__name__)
logger.info("Message")
logger.error("Error", exc_info=True)
```

## Migration Guidelines

### Creating Migrations

```bash
# 1. Modify models in easysql_api/infrastructure/persistence/models.py
# 2. Generate migration
alembic revision --autogenerate -m "add new column"
# 3. Review generated migration in alembic/versions/
# 4. Apply migration
alembic upgrade head
```

### Migration Best Practices

- **Always review** auto-generated migrations
- **Test migrations** on a copy of production data
- **Write downgrade** functions for rollback capability
- **Use PostgreSQL-specific types** (control plane is PostgreSQL-only)
- **Document breaking changes** in migration docstring

## Performance Considerations

### Connection Pooling

- Control plane: `pool_size=20`, `max_overflow=40` (adjust based on load)
- Data plane: `pool_size=5`, `max_overflow=10` per target database
- Use `pool_recycle=3600` to avoid stale connections

### Query Optimization

- Use `selectinload()` for eager loading relationships
- Avoid N+1 queries with proper joins
- Index frequently queried columns
- Use `EXPLAIN ANALYZE` for slow queries

### Caching

- Cache embedding results in Milvus
- Cache schema metadata in Neo4j
- Use LangGraph checkpointer for conversation state

## Troubleshooting

### Common Issues

**Issue**: `RuntimeError: Control plane not initialized`
- **Solution**: Ensure `db_manager.init_control_plane()` is called in app startup

**Issue**: `alembic upgrade head` fails with UUID error
- **Solution**: Verify PostgreSQL 13+ and `pgcrypto` extension is enabled

**Issue**: Connection pool exhausted
- **Solution**: Increase `pool_size` and `max_overflow` in DatabaseManager

**Issue**: Slow SQL generation
- **Solution**: Check Milvus/Neo4j connectivity, verify embedding service is running

## Documentation

- Architecture decisions: `docs/database-refactoring-guide.md`
- API documentation: Auto-generated at `/docs` endpoint
- Frontend components: See `easysql_web/README.md`

## Contributing

1. Follow code style guidelines (black, ruff, mypy)
2. Write tests for new features
3. Update CLAUDE.md if adding new patterns
4. Run full test suite before committing
5. Create migrations for schema changes

## References

- SQLAlchemy Async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- LangGraph: https://langchain-ai.github.io/langgraph/
- FastAPI: https://fastapi.tiangolo.com/
- Neo4j Python Driver: https://neo4j.com/docs/python-manual/current/
- Milvus Python SDK: https://milvus.io/docs/install-pymilvus.md
