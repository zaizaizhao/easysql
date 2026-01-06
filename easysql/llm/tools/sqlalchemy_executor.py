"""
SQLAlchemy Executor Implementation.
Fallback implementation for direct database access.
"""
import sqlalchemy
from sqlalchemy import text, inspect

from easysql.config import get_settings
from easysql.utils.logger import get_logger
from .base import BaseSqlExecutor, ExecutionResult, SchemaInfoDict, DbDialect

logger = get_logger(__name__)


class SqlAlchemyExecutor(BaseSqlExecutor):
    """
    Executes SQL using SQLAlchemy engines defined in project settings.
    """
    
    def __init__(self):
        self.settings = get_settings()
        # Cache engines to avoid recreation
        self._engines: dict[str, sqlalchemy.Engine] = {}
        
    def _get_engine(self, db_name: str) -> sqlalchemy.Engine:
        """Get or create SQLAlchemy engine for the named database."""
        if db_name in self._engines:
            return self._engines[db_name]
            
        db_config = self.settings.databases.get(db_name.lower())
        if not db_config:
            raise ValueError(f"Database '{db_name}' not configured in settings.")
            
        conn_str = db_config.get_connection_string()
        engine = sqlalchemy.create_engine(conn_str)
        self._engines[db_name] = engine
        return engine
    
    def _get_dialect(self, db_name: str) -> DbDialect:
        """Get the database dialect for a given database name."""
        db_config = self.settings.databases.get(db_name.lower())
        if not db_config:
            return "mysql"  # Default fallback
        
        db_type = db_config.db_type.lower()
        if db_type in ("mysql", "postgresql", "oracle", "sqlserver"):
            return db_type  # type: ignore
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
                        success=True,
                        data=rows,
                        columns=columns,
                        row_count=len(rows)
                    )
                else:
                    return ExecutionResult(
                        success=True,
                        row_count=result.rowcount
                    )
                    
        except Exception as e:
            logger.error(f"SQL Execution error on {db_name}: {e}")
            return ExecutionResult(
                success=False,
                error=str(e)
            )

    def get_schema_info(self, db_name: str) -> SchemaInfoDict:
        """Simple schema info using Inspector."""
        try:
            engine = self._get_engine(db_name)
            insp = inspect(engine)
            tables = insp.get_table_names()
            return {"tables": tables, "error": None}
        except Exception as e:
            logger.error(f"Schema fetch error on {db_name}: {e}")
            return {"tables": [], "error": str(e)}

    def check_syntax(self, sql: str, db_name: str) -> ExecutionResult:
        """Use dialect-aware EXPLAIN to check syntax."""
        try:
            dialect = self._get_dialect(db_name)
            explain_prefix = self.get_explain_prefix(dialect)
            
            # SQL Server requires special handling
            if dialect == "sqlserver":
                explain_cmd = f"{explain_prefix} {sql}"
            else:
                explain_cmd = f"{explain_prefix} {sql}"
            
            engine = self._get_engine(db_name)
            with engine.connect() as conn:
                conn.execute(text(explain_cmd))
                return ExecutionResult(success=True)
                
        except Exception as e:
            return ExecutionResult(success=False, error=str(e))
