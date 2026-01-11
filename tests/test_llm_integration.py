"""
Integration test for LLM Agent.

Uses mocks to verify graph structure and routing logic.
"""

from unittest.mock import MagicMock, patch

from easysql.llm.agent import build_graph, route_start, route_analyze, route_validate
from easysql.llm.tools.factory import create_sql_executor


@patch("easysql.llm.agent.get_settings")
def test_route_start_fast_mode(mock_get_settings):
    """Fast mode should skip retrieve_hint and go directly to retrieve."""
    mock_settings = MagicMock()
    mock_settings.llm.query_mode = "fast"
    mock_get_settings.return_value = mock_settings

    assert route_start({}) == "retrieve"


@patch("easysql.llm.agent.get_settings")
def test_route_start_plan_mode(mock_get_settings):
    """Plan mode should go to retrieve_hint for schema-aware analysis."""
    mock_settings = MagicMock()
    mock_settings.llm.query_mode = "plan"
    mock_get_settings.return_value = mock_settings

    assert route_start({}) == "retrieve_hint"


def test_route_analyze():
    """Test routing based on clarification_questions field."""
    assert route_analyze({"clarification_questions": None}) == "retrieve"
    assert route_analyze({"clarification_questions": []}) == "retrieve"

    assert route_analyze({"clarification_questions": ["Question 1"]}) == "clarify"


@patch("easysql.llm.agent.get_settings")
def test_route_validate(mock_get_settings):
    """Test validation routing with config-based retry limit."""
    mock_settings = MagicMock()
    mock_settings.llm.max_sql_retries = 3
    mock_get_settings.return_value = mock_settings

    assert route_validate({"validation_passed": True}) == "__end__"

    assert route_validate({"validation_passed": False, "retry_count": 0}) == "repair_sql"
    assert route_validate({"validation_passed": False, "retry_count": 2}) == "repair_sql"

    assert route_validate({"validation_passed": False, "retry_count": 3}) == "__end__"
    assert route_validate({"validation_passed": False, "retry_count": 5}) == "__end__"


@patch("easysql.llm.tools.factory.get_settings")
def test_create_sql_executor_fallback(mock_get_settings):
    """Test SQLAlchemy executor fallback when MCP is not configured."""
    mock_settings = MagicMock()
    mock_settings.llm.mcp_dbhub_url = None
    mock_get_settings.return_value = mock_settings

    executor = create_sql_executor()
    from easysql.llm.tools.sqlalchemy_executor import SqlAlchemyExecutor

    assert isinstance(executor, SqlAlchemyExecutor)


@patch("easysql.llm.tools.factory.get_settings")
@patch("easysql.llm.tools.factory.McpExecutor")
def test_create_sql_executor_mcp(mock_mcp_cls, mock_get_settings):
    """Test MCP executor creation when configured."""
    mock_settings = MagicMock()
    mock_settings.llm.mcp_dbhub_url = "http://fake:8080"
    mock_get_settings.return_value = mock_settings

    mock_executor = MagicMock()
    mock_mcp_cls.return_value = mock_executor

    executor = create_sql_executor()

    mock_mcp_cls.assert_called_with("http://fake:8080")
    mock_executor.check_connection.assert_called_once()
    assert executor == mock_executor


def test_graph_build():
    """Verify graph can be built without error and contains all nodes."""
    graph = build_graph()
    assert graph is not None
