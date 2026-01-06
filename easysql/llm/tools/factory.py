"""
SQL Executor Factory.

Creates the appropriate BaseSqlExecutor implementation based on configuration
and availability (MCP first, then SQLAlchemy).
"""
from easysql.config import get_settings
from easysql.utils.logger import get_logger
from .base import BaseSqlExecutor
from .sqlalchemy_executor import SqlAlchemyExecutor
from .mcp_executor import McpExecutor

logger = get_logger(__name__)

def create_sql_executor() -> BaseSqlExecutor:
    """
    Factory function to create a SQL executor.
    
    Strategy:
    1. Check if MCP_DBHUB_URL is configured.
    2. If yes, try to initialize McpExecutor and verify connection.
    3. If MCP succeeds, return it.
    4. If MCP fails or is not configured, fallback to SqlAlchemyExecutor.
    """
    settings = get_settings()
    llm_config = settings.llm
    
    if llm_config.mcp_dbhub_url:
        logger.info(f"Attempting to initialize MCP Executor at {llm_config.mcp_dbhub_url}")
        try:
            executor = McpExecutor(llm_config.mcp_dbhub_url)
            # Proactively check connection
            # If this fails, we catch it and fallback
            executor.check_connection()
            logger.info("MCP Executor initialized successfully.")
            return executor
        except Exception as e:
            logger.warning(f"Failed to initialize MCP Executor: {e}. Falling back to SQLAlchemy.")
    
    logger.info("Using SQLAlchemy Executor (Fallback/Default).")
    return SqlAlchemyExecutor()
