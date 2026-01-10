# AGENTS.md - EasySQL Coding Guidelines

## Project Overview

EasySQL is an enterprise Text2SQL metadata pipeline using Neo4j and Milvus for database schema graph relationships and semantic vectors. Built with Python 3.10+, Pydantic, SQLAlchemy, and LangGraph.

---

## Build / Lint / Test Commands

### Installation
```bash
pip install -r requirements.txt      # Install runtime dependencies
pip install -e ".[dev]"              # Install with dev dependencies (pytest, black, ruff, mypy)
```

### Running the Application
```bash
python main.py run                   # Run full pipeline
python main.py run --no-neo4j --no-milvus  # Schema extraction only
python main.py config                # Show current config
```

### Linting & Formatting
```bash
ruff check .                         # Lint with ruff
ruff check . --fix                   # Auto-fix lint issues
black .                              # Format with black
mypy easysql                         # Type check
```

### Testing
```bash
pytest                               # Run all tests
pytest tests/test_context_builder.py # Run single test file
pytest tests/test_context_builder.py::TestContextBuilder::test_build_context  # Run single test
pytest -v                            # Verbose output
pytest -x                            # Stop on first failure
pytest --tb=short                    # Shorter traceback
python tests/test_e2e_pipeline.py    # Run E2E test directly (requires infra)
```

---

## Code Style Guidelines

### Formatting
- **Line length**: 100 characters (configured in pyproject.toml)
- **Formatter**: Black with Python 3.10-3.12 target
- **Linter**: Ruff with rules: E, F, W, I, N, UP, B, C4 (ignores E501)

### Import Order (Ruff "I" rules)
```python
# 1. Standard library
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

# 2. Third-party
from pydantic import Field
from loguru import logger

# 3. Local application
from easysql.models.schema import TableMeta
from easysql.utils.logger import get_logger
```

### Type Annotations
- **Required** for all function signatures (params and return types)
- Use Python 3.10+ syntax: `list[str]`, `dict[str, Any]`, `str | None` (not `Optional[str]`)
- Use `TYPE_CHECKING` for circular import prevention:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from easysql.config import DatabaseConfig
```

### Naming Conventions
| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `SchemaExtractor`, `TableMeta` |
| Functions/Methods | snake_case | `extract_tables`, `get_logger` |
| Constants | UPPER_SNAKE | `BATCH_SIZE`, `DEFAULT_PORT` |
| Private | Leading underscore | `_connection`, `_mark_fk_columns` |
| Modules | snake_case | `schema_pipeline.py` |

### Docstrings
- Use triple-quoted docstrings for all public classes and functions
- Include Args, Returns, Raises sections where applicable:
```python
def extract_tables(self) -> list[TableMeta]:
    """
    Extract all table metadata from the database.

    Returns:
        List of TableMeta objects with columns and indexes

    Raises:
        ConnectionError: If database connection fails
    """
```

---

## Architecture Patterns

### Abstract Base Classes
- Base classes in `base.py` files (e.g., `extractors/base.py`, `retrieval/base.py`)
- Use `ABC` and `@abstractmethod` for interface definitions
- Concrete implementations in separate modules

### Factory Pattern
```python
class ExtractorFactory:
    _extractors: dict[str, type[BaseSchemaExtractor]] = {}

    @classmethod
    def register(cls, db_type: str, extractor_class: type[BaseSchemaExtractor]) -> None: ...

    @classmethod
    def create(cls, config: DatabaseConfig) -> BaseSchemaExtractor: ...
```

### Pydantic Models
- All data models inherit from `BaseModel` (easysql/models/base.py)
- Use `Field()` for descriptions and defaults
- Configuration via `model_config = SettingsConfigDict(...)`

### Context Manager Pattern
```python
def __enter__(self) -> "BaseSchemaExtractor":
    self.connect()
    return self

def __exit__(self, exc_type, exc_val, exc_tb) -> None:
    self.disconnect()
```

---

## Project Structure

```
easysql/
├── config.py              # Settings with pydantic-settings
├── models/                # Pydantic data models
│   ├── base.py           # BaseModel config
│   └── schema.py         # TableMeta, ColumnMeta, etc.
├── extractors/           # Database schema extractors
│   ├── base.py           # ABC + Factory
│   └── sqlalchemy_extractor.py
├── writers/              # Neo4j and Milvus writers
├── embeddings/           # Embedding service
├── retrieval/            # Schema retrieval with filters
│   ├── base.py           # TableFilter ABC
│   ├── semantic_filter.py
│   └── bridge_filter.py
├── context/              # LLM prompt building
│   ├── builder.py        # ContextBuilder
│   └── sections/         # SchemaSection, JoinPathSection
├── llm/                  # LangGraph agent
│   ├── agent.py          # Graph builder
│   ├── state.py          # TypedDict state
│   └── nodes/            # LangGraph nodes
└── utils/
    └── logger.py         # Loguru config
```

---

## Configuration

- Environment variables via `.env` file (copy from `.env.example`)
- Pydantic Settings for validation: `easysql/config.py`
- Dynamic database config parsing: `DB_<NAME>_*` pattern
- Access settings via `get_settings()` (cached)

---

## Error Handling

- Use specific exception types (ValueError, ConnectionError)
- Log errors with `logger.error()` or `logger.warning()`
- Never use bare `except:` - always specify exception type
- Context managers for resource cleanup (connections)

---

## Testing Patterns

### Test Structure
- Tests in `tests/` directory mirroring source structure
- Test classes prefixed with `Test` (e.g., `TestContextBuilder`)
- Test methods prefixed with `test_`
- Use `@dataclass` for mock objects

### Fixtures and Mocks
```python
@dataclass
class MockRetrievalResult:
    """Mock for testing without database connections."""
    tables: List[str] = field(default_factory=list)
    table_columns: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
```

### Running Tests Without Infrastructure
```python
# Create mock data
result = create_test_retrieval_result()

# Test components in isolation
builder = ContextBuilder.default()
output = builder.build(context_input)
```

---

## LLM/LangGraph Conventions

### State Definition (TypedDict)
```python
class EasySQLState(TypedDict):
    question: str
    clarification_questions: list[str]
    validation_passed: bool
    retry_count: int
```

### Node Functions
- Nodes are either classes with `__call__` or plain functions
- Return `dict` with state updates
- Use routing functions for conditional edges

### SQL Extraction
```python
@staticmethod
def extract_sql(content: str) -> str:
    """Extract SQL from markdown code blocks (```sql ... ```)."""
```

---

## Dependencies

### Core
- pydantic >= 2.0.0, pydantic-settings
- neo4j >= 5.0.0
- pymilvus >= 2.3.0
- sentence-transformers >= 2.2.0
- sqlalchemy (via pymysql, psycopg2-binary)
- langgraph, langchain-core

### Dev
- pytest >= 7.0.0
- black >= 23.0.0
- ruff >= 0.1.0
- mypy >= 1.0.0

---

## Quick Reference

| Task | Command |
|------|---------|
| Format code | `black .` |
| Lint code | `ruff check .` |
| Type check | `mypy easysql` |
| Run all tests | `pytest` |
| Run single test | `pytest tests/file.py::TestClass::test_method` |
| Run E2E | `python tests/test_e2e_pipeline.py` |
