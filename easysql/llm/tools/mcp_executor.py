"""
MCP Executor Implementation.
Executes SQL via DBHub MCP Server.
"""
import asyncio
from typing import Dict, Optional

from easysql.utils.logger import get_logger
from .base import BaseSqlExecutor, ExecutionResult, SchemaInfoDict

logger = get_logger(__name__)

# Apply nest_asyncio once at module level to avoid repeated application
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    logger.warning("nest_asyncio not installed. Async operations in sync context may fail.")


class McpExecutor(BaseSqlExecutor):
    """
    Executes SQL using DBHub MCP Server via langchain-mcp-adapters.
    """
    
    def __init__(self, mcp_url: str):
        self.mcp_url = mcp_url
        self._client: Optional[object] = None
        self._tools: Dict[str, object] = {}
        
    async def _ensure_client(self) -> None:
        """Initialize MCP client and fetch tools."""
        if self._client:
            return

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            
            # Initialize client
            self._client = MultiServerMCPClient({
                "dbhub": {
                    "url": self.mcp_url,
                    "transport": "sse",
                }
            })
            
            # Connect
            await self._client.__aenter__()
            
            # Get tools
            tools = await self._client.get_tools()
            self._tools = {t.name: t for t in tools}
            logger.info(f"Connected to MCP at {self.mcp_url}. Tools: {list(self._tools.keys())}")
            
        except ImportError:
            raise ImportError(
                "langchain-mcp-adapters is required. "
                "Install it with: pip install langchain-mcp-adapters"
            )
        except Exception as e:
            logger.error(f"Failed to connect to MCP DBHub: {e}")
            raise
            
    def _run_async(self, coro) -> object:
        """Helper to run async code in sync context."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(coro)

    async def _execute_sql_async(self, sql: str, db_name: str) -> ExecutionResult:
        await self._ensure_client()
        
        # Look for execute_sql tool
        tool_name = "execute_sql"
        if tool_name not in self._tools:
            # Try finding a relevant tool
            for name in self._tools:
                if "query" in name or "execute" in name:
                    tool_name = name
                    break
            else:
                return ExecutionResult(success=False, error="No SQL execution tool found in MCP")
                
        tool = self._tools[tool_name]
        
        try:
            result_str = await tool.ainvoke({"sql": sql, "database": db_name})
            return ExecutionResult(success=True, data=[{"result": str(result_str)}])
            
        except Exception as e:
            return ExecutionResult(success=False, error=str(e))

    def execute_sql(self, sql: str, db_name: str) -> ExecutionResult:
        return self._run_async(self._execute_sql_async(sql, db_name))

    async def _get_schema_info_async(self, db_name: str) -> SchemaInfoDict:
        await self._ensure_client()
        
        tool_name = "search_objects"
        if tool_name not in self._tools:
            return {"tables": [], "error": "No schema tool found in MCP"}
             
        tool = self._tools[tool_name]
        try:
            res = await tool.ainvoke({"query": "", "database": db_name})
            # Parse results into table list if possible
            tables = []
            if isinstance(res, str):
                # Simple parsing - adjust based on actual DBHub response format
                tables = [res]
            return {"tables": tables, "error": None}
        except Exception as e:
            return {"tables": [], "error": str(e)}

    def get_schema_info(self, db_name: str) -> SchemaInfoDict:
        return self._run_async(self._get_schema_info_async(db_name))

    def check_syntax(self, sql: str, db_name: str) -> ExecutionResult:
        # DBHub might not have explicit explain.
        # We can try to prepend EXPLAIN if it's MySQL/PG
        explain_sql = f"EXPLAIN {sql}"
        return self.execute_sql(explain_sql, db_name)
    
    def check_connection(self) -> None:
        """Verify connection proactively."""
        self._run_async(self._ensure_client())
