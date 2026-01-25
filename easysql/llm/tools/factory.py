"""
SQL Executor Factory.
"""

from easysql.llm.tools.executors.base import BaseSqlExecutor
from easysql.llm.tools.executors.sqlalchemy_executor import SqlAlchemyExecutor
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


def create_sql_executor() -> BaseSqlExecutor:
    """Create a SQLAlchemy-based SQL executor."""
    logger.info("Using SQLAlchemy Executor.")
    return SqlAlchemyExecutor()
