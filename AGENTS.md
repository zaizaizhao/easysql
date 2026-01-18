# AGENTS.md - EasySQL Coding Guidelines

EasySQL: Enterprise Text2SQL pipeline using Neo4j (graph) + Milvus (vectors). Python 3.10+, Pydantic, SQLAlchemy, LangGraph.

## Build / Lint / Test Commands

```bash
# Installation
pip install -r requirements.txt      # Runtime deps
pip install -e ".[dev]"              # Dev deps (pytest, black, ruff, mypy)

# Running
python main.py run                   # Full pipeline
python main.py run --no-neo4j --no-milvus  # Schema extraction only

# Linting & Formatting (run before commits)
ruff check .                         # Lint
ruff check . --fix                   # Auto-fix
black .                              # Format
mypy easysql                         # Type check

# Testing
pytest                               # All tests
pytest tests/test_context_builder.py # Single file
pytest tests/test_context_builder.py::TestContextBuilder::test_build_context  # Single test
pytest -v -x --tb=short              # Verbose, stop on first failure
```

## Code Style

### Formatting
- **Line length**: 100 chars | **Formatter**: Black | **Linter**: Ruff (E, F, W, I, N, UP, B, C4)

### Import Order (Ruff "I")
```python
# 1. stdlib  2. third-party  3. local
from typing import Any, TYPE_CHECKING
from pydantic import Field
from easysql.models.schema import TableMeta
```

### Type Annotations
- **Required** for all function signatures
- Use `list[str]`, `dict[str, Any]`, `str | None` (NOT `Optional[str]`)
- Use `TYPE_CHECKING` guard for circular imports

### Naming
| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `SchemaExtractor` |
| Functions | snake_case | `extract_tables` |
| Constants | UPPER_SNAKE | `BATCH_SIZE` |
| Private | Leading `_` | `_connection` |

### Docstrings
```python
def extract_tables(self) -> list[TableMeta]:
    """Extract all table metadata from the database.
    Returns: List of TableMeta objects
    Raises: ConnectionError if connection fails
    """
```

## Architecture Patterns

### Abstract Base Classes
- Base classes in `base.py` files (e.g., `extractors/base.py`)
- Use `ABC` + `@abstractmethod` for interfaces

### Factory Pattern
```python
class ExtractorFactory:
    _extractors: dict[str, type[BaseSchemaExtractor]] = {}
    @classmethod
    def register(cls, db_type: str, extractor_class: type) -> None: ...
    @classmethod
    def create(cls, config: DatabaseConfig) -> BaseSchemaExtractor: ...
```

### Pydantic Models
- Inherit from `BaseModel` (easysql/models/base.py)
- Use `Field()` for descriptions and defaults

### Context Managers
```python
def __enter__(self) -> "BaseSchemaExtractor":
    self.connect(); return self
def __exit__(self, exc_type, exc_val, exc_tb) -> None:
    self.disconnect()
```

## Error Handling

- Use specific exceptions (`ValueError`, `ConnectionError`)
- Log with `logger.error()` / `logger.warning()`
- **Never** bare `except:` - always specify type
- Context managers for resource cleanup

## Testing

```python
@dataclass
class MockRetrievalResult:
    """Mock for testing without infrastructure."""
    tables: list[str] = field(default_factory=list)
    table_columns: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
```
- Tests in `tests/` | Classes: `TestContextBuilder` | Methods: `test_build_context`

## LangGraph Conventions

```python
class EasySQLState(TypedDict):
    question: str
    clarification_questions: list[str]
    validation_passed: bool
    retry_count: int
```
- Nodes: functions or `__call__` classes returning `dict` with state updates
- Use routing functions for conditional edges

## Configuration

- `.env` file (copy from `.env.example`) | Settings: `easysql/config.py`
- Access: `get_settings()` (cached) | DB pattern: `DB_<NAME>_TYPE`, `DB_<NAME>_HOST`

## Quick Reference

| Task | Command |
|------|---------|
| Format | `black .` |
| Lint | `ruff check .` |
| Type check | `mypy easysql` |
| All tests | `pytest` |
| Single test | `pytest tests/file.py::TestClass::test_method` |

## Common Pitfalls

1. **Type suppressions**: Never `# type: ignore` without justification
2. **Bare except**: Always catch specific exceptions
3. **Missing types**: All public functions need type annotations
4. **Import cycles**: Use `TYPE_CHECKING` guard
5. **Resource leaks**: Always use context managers for connections
