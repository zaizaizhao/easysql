"""SQLAlchemy executor that runs SQL via the data-plane engine registry."""

from sqlalchemy import inspect, text

from easysql.config import get_settings
from easysql.infrastructure import get_data_plane_engine_registry
from easysql.llm.tools.executors.base import (
    BaseSqlExecutor,
    DbDialect,
    ExecutionResult,
    SchemaInfoDict,
)
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class SqlAlchemyExecutor(BaseSqlExecutor):
    """Executes SQL using SQLAlchemy engines defined in project settings."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._registry = get_data_plane_engine_registry()

    def _get_engine(self, db_name: str):
        db_config = self.settings.databases.get(db_name.lower())
        if not db_config:
            raise ValueError(f"Database '{db_name}' not configured in settings.")
        return self._registry.get_engine(db_config)

    def _get_dialect(self, db_name: str) -> DbDialect:
        db_config = self.settings.databases.get(db_name.lower())
        if not db_config:
            return "mysql"

        db_type = db_config.db_type.lower()
        if db_type in ("mysql", "postgresql", "oracle", "sqlserver"):
            return db_type  # type: ignore[return-value]
        return "mysql"

    def execute_sql(self, sql: str, db_name: str) -> ExecutionResult:
        try:
            engine = self._get_engine(db_name)
            with engine.connect() as conn:
                result = conn.execute(text(sql))

                if result.returns_rows:
                    rows = [dict(row._mapping) for row in result]
                    columns = list(result.keys())
                    return ExecutionResult(
                        success=True, data=rows, columns=columns, row_count=len(rows)
                    )
                return ExecutionResult(success=True, row_count=result.rowcount)

        except Exception as e:
            logger.error(f"SQL Execution error on {db_name}: {e}")
            return ExecutionResult(success=False, error=str(e))

    def get_schema_info(self, db_name: str) -> SchemaInfoDict:
        try:
            engine = self._get_engine(db_name)
            insp = inspect(engine)
            tables = insp.get_table_names()
            return {"tables": tables, "error": None}
        except Exception as e:
            logger.error(f"Schema fetch error on {db_name}: {e}")
            return {"tables": [], "error": str(e)}

    def check_syntax(self, sql: str, db_name: str) -> ExecutionResult:
        try:
            dialect = self._get_dialect(db_name)
            explain_prefix = self.get_explain_prefix(dialect)
            explain_cmd = f"{explain_prefix} {sql}"

            engine = self._get_engine(db_name)
            with engine.connect() as conn:
                conn.execute(text(explain_cmd))
                return ExecutionResult(success=True)

        except Exception as e:
            return ExecutionResult(success=False, error=str(e))
