"""Guards against the validate -> repair no-progress loop.

Previously: when generate_sql raised (error set, generated_sql=None),
repair_sql returned {} and route_validate kept routing back to repair_sql
until LangGraph's recursion limit aborted the run.
"""

import asyncio
from unittest.mock import MagicMock, patch

from easysql.llm.agent import route_validate
from easysql.llm.nodes.repair_sql import RepairSQLNode


class TestRouteValidate:
    def test_passed_goes_to_update_history(self):
        assert route_validate({"validation_passed": True}) == "update_history"

    def test_no_sql_terminates_instead_of_repairing(self):
        state = {"validation_passed": False, "generated_sql": None, "error": "boom"}
        assert route_validate(state) == "update_history"

    @patch("easysql.llm.agent.get_settings")
    def test_generated_sql_retries_below_limit(self, mock_get_settings):
        settings = MagicMock()
        settings.llm.max_sql_retries = 3
        mock_get_settings.return_value = settings

        state = {"validation_passed": False, "generated_sql": "SELECT 1", "retry_count": 2}
        assert route_validate(state) == "repair_sql"

    @patch("easysql.llm.agent.get_settings")
    def test_generated_sql_stops_at_limit(self, mock_get_settings):
        settings = MagicMock()
        settings.llm.max_sql_retries = 3
        mock_get_settings.return_value = settings

        state = {"validation_passed": False, "generated_sql": "SELECT 1", "retry_count": 3}
        assert route_validate(state) == "update_history"


class TestRepairNoOpGuard:
    def test_missing_sql_still_consumes_a_retry(self):
        node = RepairSQLNode()
        result = asyncio.run(node({"error": "boom", "generated_sql": None}))

        assert result["retry_count"] == 1
        assert result["validation_passed"] is False
        assert result["error"] == "boom"

    def test_missing_error_still_consumes_a_retry(self):
        node = RepairSQLNode()
        result = asyncio.run(node({"error": None, "generated_sql": "SELECT 1", "retry_count": 2}))

        assert result["retry_count"] == 3
        assert result["validation_passed"] is False
        assert "repair skipped" in result["error"]
