from __future__ import annotations

import uuid
from typing import Any, Generator

from langgraph.types import Command

from easysql_api.models.query import QueryStatus, ClarificationInfo
from easysql_api.services.session_store import Session, SessionStore, get_session_store
from easysql.config import get_settings
from easysql.llm import build_graph
from easysql.llm.state import EasySQLState
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class QueryService:
    def __init__(self) -> None:
        self._graph: Any = None
        self._store: SessionStore = get_session_store()

    @property
    def graph(self) -> Any:
        if self._graph is None:
            self._graph = build_graph()
        return self._graph

    def create_session(self, db_name: str | None = None) -> Session:
        session_id = str(uuid.uuid4())
        session = self._store.create(session_id, db_name)
        assert session is not None
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._store.get(session_id)

    def execute_query(
        self,
        session: Session,
        question: str,
    ) -> dict[str, Any]:
        session.raw_query = question
        session.status = QueryStatus.PROCESSING
        session.touch()

        input_state: dict[str, Any] = {
            "raw_query": question,
            "clarified_query": None,
            "clarification_questions": None,
            "messages": [],
            "schema_hint": None,
            "retrieval_result": None,
            "context_output": None,
            "code_context": None,
            "generated_sql": None,
            "validation_result": None,
            "validation_passed": False,
            "retry_count": 0,
            "error": None,
            "db_name": session.db_name,
        }

        config = {"configurable": {"thread_id": session.session_id}}

        try:
            result = self.graph.invoke(input_state, config)
            return self._process_result(session, result, config)
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            session.status = QueryStatus.FAILED
            session.touch()
            return {
                "status": QueryStatus.FAILED,
                "error": str(e),
            }

    def continue_conversation(
        self,
        session: Session,
        answer: str,
    ) -> dict[str, Any]:
        if session.status != QueryStatus.AWAITING_CLARIFICATION:
            return {
                "status": QueryStatus.FAILED,
                "error": "Session is not awaiting clarification",
            }

        session.status = QueryStatus.PROCESSING
        session.messages.append({"role": "user", "content": answer})
        session.touch()

        config = {"configurable": {"thread_id": session.session_id}}

        try:
            result = self.graph.invoke(Command(resume=answer), config)
            return self._process_result(session, result, config)
        except Exception as e:
            logger.error(f"Continue conversation failed: {e}")
            session.status = QueryStatus.FAILED
            session.touch()
            return {
                "status": QueryStatus.FAILED,
                "error": str(e),
            }

    def _process_result(
        self,
        session: Session,
        result: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = self.graph.get_state(config)

        if snapshot.next and "clarify" in snapshot.next:
            questions = self._extract_clarification_questions(snapshot, result)
            session.status = QueryStatus.AWAITING_CLARIFICATION
            session.clarification_questions = questions
            session.state = dict(result) if result else None
            session.touch()

            return {
                "status": QueryStatus.AWAITING_CLARIFICATION.value,
                "clarification": {"questions": questions},
            }

        session.generated_sql = result.get("generated_sql")
        session.validation_passed = result.get("validation_passed", False)
        session.status = QueryStatus.COMPLETED
        session.state = dict(result) if result else None
        session.touch()

        response: dict[str, Any] = {
            "status": QueryStatus.COMPLETED.value,
            "sql": session.generated_sql,
            "validation_passed": session.validation_passed,
        }

        if not session.validation_passed:
            validation_result = result.get("validation_result", {})
            response["validation_error"] = result.get("error") or validation_result.get("error")

        return response

    def _extract_clarification_questions(
        self,
        snapshot: Any,
        result: dict[str, Any],
    ) -> list[str]:
        try:
            if hasattr(snapshot, "tasks") and snapshot.tasks:
                for task in snapshot.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        for interrupt in task.interrupts:
                            if hasattr(interrupt, "value"):
                                value = interrupt.value
                                if isinstance(value, dict):
                                    questions = value.get("questions", [])
                                    return list(questions) if questions else []
                                if isinstance(value, list):
                                    return list(value)
        except Exception:
            pass

        questions = result.get("clarification_questions", [])
        return list(questions) if questions else []

    def stream_query(
        self,
        session: Session,
        question: str,
    ) -> Generator[dict[str, Any], None, None]:
        session.raw_query = question
        session.status = QueryStatus.PROCESSING
        session.touch()

        input_state: dict[str, Any] = {
            "raw_query": question,
            "clarified_query": None,
            "clarification_questions": None,
            "messages": [],
            "schema_hint": None,
            "retrieval_result": None,
            "context_output": None,
            "code_context": None,
            "generated_sql": None,
            "validation_result": None,
            "validation_passed": False,
            "retry_count": 0,
            "error": None,
            "db_name": session.db_name,
        }

        config = {"configurable": {"thread_id": session.session_id}}

        try:
            yield {"event": "start", "data": {"session_id": session.session_id}}

            last_state: dict[str, Any] = {}
            for state_snapshot in self.graph.stream(input_state, config):
                last_state = state_snapshot
                yield {
                    "event": "state_update",
                    "data": self._sanitize_output(state_snapshot),
                }

            snapshot = self.graph.get_state(config)
            final_state = snapshot.values if snapshot else last_state

            final_result = self._process_result(session, dict(final_state), config)
            yield {"event": "complete", "data": final_result}

        except Exception as e:
            logger.error(f"Stream query failed: {e}")
            session.status = QueryStatus.FAILED
            session.touch()
            yield {"event": "error", "data": {"error": str(e)}}

    def _sanitize_output(self, output: dict[str, Any] | None) -> dict[str, Any]:
        if output is None:
            return {}
        if not isinstance(output, dict):
            return {}
        safe_keys = {
            "generated_sql",
            "validation_passed",
            "validation_result",
            "clarification_questions",
            "clarified_query",
            "schema_hint",
            "error",
        }
        result = {k: v for k, v in output.items() if k in safe_keys and v is not None}

        if "retrieval_result" in output and output["retrieval_result"]:
            rr = output["retrieval_result"]
            result["retrieval_summary"] = {
                "tables_count": len(rr.get("tables", [])),
                "tables": rr.get("tables", [])[:10],
            }

        if "context_output" in output and output["context_output"]:
            co = output["context_output"]
            result["context_summary"] = {
                "total_tokens": co.get("total_tokens"),
                "has_system_prompt": bool(co.get("system_prompt")),
                "has_user_prompt": bool(co.get("user_prompt")),
            }

        return result


_default_service: QueryService | None = None


def get_query_service() -> QueryService:
    global _default_service
    if _default_service is None:
        _default_service = QueryService()
    return _default_service
