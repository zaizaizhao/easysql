"""
Test Multi-Turn Conversation functionality.

Tests for:
- TokenManager: history preparation and compression
- ContextMerger: merging old and new retrieval contexts
- ShiftDetectNode: semantic shift detection
- Conversation state management
"""

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@dataclass
class MockConversationTurn:
    question: str
    sql: str | None = None
    tables_used: list[str] = field(default_factory=list)
    token_count: int | None = None

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class TestTokenManager:
    def test_prepare_history_no_compression_needed(self):
        from easysql.llm.utils.token_manager import TokenManager

        manager = TokenManager(max_tokens=10000)

        history = [
            MockConversationTurn(
                question="查询本月挂号量",
                sql="SELECT COUNT(*) FROM registration WHERE ...",
                token_count=50,
            ),
            MockConversationTurn(
                question="按科室分组",
                sql="SELECT dept, COUNT(*) FROM registration GROUP BY dept",
                token_count=60,
            ),
        ]

        summary, recent = manager.prepare_history(history, schema_context_tokens=1000)

        assert summary is None
        assert len(recent) == 2
        assert recent[0]["question"] == "查询本月挂号量"

    def test_prepare_history_compression_triggered(self):
        from easysql.llm.utils.token_manager import TokenManager

        manager = TokenManager(max_tokens=5000)

        history = [
            MockConversationTurn(
                question=f"问题 {i}" * 50,
                sql=f"SELECT * FROM table_{i} WHERE col > 100" * 10,
                token_count=300,
            )
            for i in range(15)
        ]

        with patch.object(manager, "_summarize_history", return_value="[摘要]"):
            summary, recent = manager.prepare_history(history, schema_context_tokens=1000)

        assert summary == "[摘要]"
        assert len(recent) < len(history)

    def test_prepare_history_empty(self):
        from easysql.llm.utils.token_manager import TokenManager

        manager = TokenManager()
        summary, recent = manager.prepare_history([], schema_context_tokens=1000)

        assert summary is None
        assert recent == []

    def test_prepare_history_no_space(self):
        from easysql.llm.utils.token_manager import TokenManager

        manager = TokenManager(max_tokens=1000)
        history = [MockConversationTurn(question="test", token_count=50)]

        summary, recent = manager.prepare_history(history, schema_context_tokens=9000)

        assert summary is None
        assert recent == []

    def test_build_history_messages_with_summary(self):
        from easysql.llm.utils.token_manager import TokenManager

        manager = TokenManager()
        history = [
            MockConversationTurn(question="问题1", sql="SELECT 1"),
            MockConversationTurn(question="问题2", sql="SELECT 2"),
        ]

        messages = manager.build_history_messages("历史摘要内容", history)

        assert len(messages) == 5
        assert "历史摘要" in messages[0].content
        assert messages[1].content == "问题1"
        assert "SELECT 1" in messages[2].content

    def test_build_history_messages_without_summary(self):
        from easysql.llm.utils.token_manager import TokenManager

        manager = TokenManager()
        history = [MockConversationTurn(question="问题1", sql="SELECT 1")]

        messages = manager.build_history_messages(None, history)

        assert len(messages) == 2
        assert messages[0].content == "问题1"


class TestContextMerger:
    def test_merge_no_old_context(self):
        from easysql.llm.utils.context_merger import ContextMerger

        merger = ContextMerger()
        new_retrieval = {"tables": ["orders", "products"]}

        result = merger.merge(None, new_retrieval)

        assert result == {"orders", "products"}

    def test_merge_with_old_context(self):
        from easysql.llm.utils.context_merger import ContextMerger

        merger = ContextMerger()

        old_context = {
            "system_prompt": "表名: users\n表名: orders\n",
            "user_prompt": "query",
        }
        new_retrieval = {"tables": ["products", "orders"]}

        result = merger.merge(old_context, new_retrieval)

        assert "users" in result
        assert "orders" in result
        assert "products" in result
        assert len(result) == 3

    def test_merge_empty_new_retrieval(self):
        from easysql.llm.utils.context_merger import ContextMerger

        merger = ContextMerger()

        old_context = {"system_prompt": "表名: users\n", "user_prompt": "query"}
        new_retrieval = {"tables": []}

        result = merger.merge(old_context, new_retrieval)

        assert result == {"users"}

    def test_extract_tables_from_context(self):
        from easysql.llm.utils.context_merger import ContextMerger

        merger = ContextMerger()

        context = {
            "system_prompt": """
表名: patient (患者表)
列: patient_id, name, gender

表名: prescription (处方表)
列: prescription_id, patient_id
            """,
            "user_prompt": "test",
        }

        tables = merger._extract_tables_from_context(context)

        assert "patient" in tables
        assert "prescription" in tables


class TestShiftDetectNode:
    @pytest.mark.asyncio
    async def test_no_cached_context_requires_retrieval(self):
        from easysql.llm.nodes.shift_detect import ShiftDetectNode

        node = ShiftDetectNode()
        state = {"raw_query": "查询患者信息", "cached_context": None}

        result = await node(state)

        assert result["needs_new_retrieval"] is True
        assert result["shift_reason"] == "no_cached_context"

    @pytest.mark.asyncio
    async def test_no_tables_requires_retrieval(self):
        from easysql.llm.nodes.shift_detect import ShiftDetectNode

        node = ShiftDetectNode()
        state = {
            "raw_query": "查询患者信息",
            "cached_context": {"system_prompt": "test"},
            "retrieval_result": {"tables": []},
        }

        result = await node(state)

        assert result["needs_new_retrieval"] is True
        assert result["shift_reason"] == "no_tables_in_cache"

    def test_format_history_empty(self):
        from easysql.llm.nodes.shift_detect import ShiftDetectNode

        node = ShiftDetectNode()

        result = node._format_history([])

        assert result == "无历史对话"

    def test_format_history_with_turns(self):
        from easysql.llm.nodes.shift_detect import ShiftDetectNode

        node = ShiftDetectNode()

        history = [
            {"question": "问题1", "sql": "SELECT 1", "tables_used": ["t1"]},
            {"question": "问题2", "sql": "SELECT 2", "tables_used": ["t2"]},
        ]

        result = node._format_history(history)

        assert "问题1" in result
        assert "问题2" in result
        assert "t1" in result


class TestConversationState:
    def test_conversation_turn_structure(self):
        from easysql.llm.state import ConversationTurn

        turn: ConversationTurn = {
            "question": "查询本月挂号量",
            "sql": "SELECT COUNT(*) FROM registration",
            "tables_used": ["registration"],
            "message_id": "msg_001",
            "token_count": 150,
        }

        assert turn["question"] == "查询本月挂号量"
        assert turn["sql"] == "SELECT COUNT(*) FROM registration"
        assert "registration" in turn["tables_used"]

    def test_state_multi_turn_fields(self):
        from easysql.llm.state import EasySQLState

        state: EasySQLState = {
            "raw_query": "追问内容",
            "clarified_query": None,
            "clarification_questions": [],
            "messages": [],
            "schema_hint": None,
            "retrieval_result": None,
            "context_output": None,
            "code_context": None,
            "generated_sql": "",
            "validation_result": None,
            "validation_passed": False,
            "retry_count": 0,
            "error": None,
            "db_name": None,
            "conversation_history": [
                {
                    "question": "原始问题",
                    "sql": "SELECT 1",
                    "tables_used": [],
                    "message_id": "m1",
                    "token_count": 100,
                }
            ],
            "cached_context": {"system_prompt": "cached", "user_prompt": "cached"},
            "current_message_id": "m2",
            "parent_message_id": "m1",
            "needs_new_retrieval": False,
            "shift_reason": None,
            "history_summary": None,
            "few_shot_examples": None,
        }

        assert state["current_message_id"] == "m2"
        assert state["parent_message_id"] == "m1"
        assert len(state["conversation_history"]) == 1
        assert state["needs_new_retrieval"] is False


class TestEdgeCases:
    def test_token_manager_max_history_limit(self):
        from easysql.llm.utils.token_manager import TokenManager

        manager = TokenManager(max_tokens=50000)

        history = [
            MockConversationTurn(
                question=f"问题 {i}",
                sql=f"SELECT {i}",
                token_count=10,
            )
            for i in range(20)
        ]

        summary, recent = manager.prepare_history(history, schema_context_tokens=1000)

        assert len(recent) <= TokenManager.MAX_HISTORY_TURNS

    def test_context_merger_malformed_context(self):
        from easysql.llm.utils.context_merger import ContextMerger

        merger = ContextMerger()

        old_context = {"system_prompt": "random content without table markers"}

        result = merger.merge(old_context, {"tables": ["new_table"]})

        assert "new_table" in result

    @pytest.mark.asyncio
    async def test_shift_detect_graceful_failure(self):
        from easysql.llm.nodes.shift_detect import ShiftDetectNode

        node = ShiftDetectNode()

        state = {
            "raw_query": "test",
            "cached_context": {"system_prompt": "test"},
            "retrieval_result": {"tables": ["t1"]},
            "conversation_history": [],
        }

        with patch("easysql.llm.nodes.shift_detect.get_llm") as mock_llm:
            mock_llm.side_effect = Exception("LLM unavailable")
            result = await node(state)

        assert result["needs_new_retrieval"] is True
        assert "detection_error" in result["shift_reason"]


class TestIntegration:
    def test_full_conversation_flow_mock(self):
        from easysql.llm.utils.token_manager import TokenManager
        from easysql.llm.utils.context_merger import ContextMerger

        manager = TokenManager()
        merger = ContextMerger()

        history = []
        cached_context = None

        turn1 = MockConversationTurn(
            question="查询所有患者",
            sql="SELECT * FROM patient",
            tables_used=["patient"],
            token_count=50,
        )
        history.append(turn1)

        retrieval1 = {"tables": ["patient"]}
        cached_context = {
            "system_prompt": "表名: patient\n列: id, name",
            "user_prompt": "查询所有患者",
        }

        turn2 = MockConversationTurn(
            question="按性别分组统计",
            sql="SELECT gender, COUNT(*) FROM patient GROUP BY gender",
            tables_used=["patient"],
            token_count=60,
        )
        history.append(turn2)

        summary, recent = manager.prepare_history(history, schema_context_tokens=500)
        assert len(recent) == 2
        assert summary is None

        turn3_question = "查询每个患者的处方"
        retrieval2 = {"tables": ["prescription"]}
        merged_tables = merger.merge(cached_context, retrieval2)
        assert "patient" in merged_tables
        assert "prescription" in merged_tables


class TestUpdateHistoryNode:
    def test_update_history_appends_turn(self):
        from easysql.llm.nodes.update_history import UpdateHistoryNode

        node = UpdateHistoryNode()
        state = {
            "raw_query": "查询所有患者",
            "generated_sql": "SELECT * FROM patient",
            "validation_passed": True,
            "retrieval_result": {"tables": ["patient"]},
            "conversation_history": [],
        }

        result = node(state)

        history = result.get("conversation_history", [])
        assert len(history) == 1
        assert history[0]["question"] == "查询所有患者"
        assert history[0]["sql"] == "SELECT * FROM patient"
        assert history[0]["tables_used"] == ["patient"]
        assert history[0]["token_count"] > 0

    def test_update_history_skips_empty(self):
        from easysql.llm.nodes.update_history import UpdateHistoryNode

        node = UpdateHistoryNode()
        state = {
            "raw_query": "查询所有患者",
            "generated_sql": None,
            "error": None,
            "conversation_history": [],
        }

        result = node(state)

        assert result == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
