from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

from langgraph.types import Command

from easysql.config import get_settings
from easysql.llm import build_graph, get_langfuse_callbacks
from easysql.utils.logger import get_logger
from easysql_api.models.query import QueryStatus
from easysql_api.services.session_store import Session, SessionStore, get_session_store

logger = get_logger(__name__)


class QueryService:
    def __init__(self) -> None:
        self._graph: Any = None
        self._store: SessionStore = get_session_store()
        self._callbacks: list[Any] | None = None

    @property
    def graph(self) -> Any:
        if self._graph is None:
            self._graph = build_graph()
        return self._graph

    @property
    def callbacks(self) -> list[Any]:
        if self._callbacks is None:
            self._callbacks = get_langfuse_callbacks()
        return self._callbacks

    def _make_config(self, session_id: str) -> dict[str, Any]:
        config: dict[str, Any] = {"configurable": {"thread_id": session_id}}
        if self.callbacks:
            config["callbacks"] = self.callbacks
            logger.debug(f"LangFuse callbacks attached: {len(self.callbacks)} handler(s)")
        return config

    def create_session(self, db_name: str | None = None) -> Session:
        if not db_name:
            settings = get_settings()
            databases = settings.databases
            if databases:
                db_name = next(iter(databases.keys()))
                logger.info(f"No db_name provided, defaulting to: {db_name}")
            else:
                logger.warning("No databases configured in settings!")

        session_id = str(uuid.uuid4())
        session = self._store.create(session_id, db_name)
        assert session is not None
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._store.get(session_id)

    async def execute_query(
        self,
        session: Session,
        question: str,
    ) -> dict[str, Any]:
        session.raw_query = question
        session.status = QueryStatus.PROCESSING
        turn = session.create_turn(question)

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

        config = self._make_config(session.session_id)

        try:
            result = await self.graph.ainvoke(input_state, config)
            return await self._process_result(session, result, config, turn)
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            return {
                "status": QueryStatus.FAILED,
                "error": str(e),
            }

    async def continue_conversation(
        self,
        session: Session,
        answer: str,
    ) -> dict[str, Any]:
        if session.status != QueryStatus.AWAITING_CLARIFICATION:
            return {
                "status": QueryStatus.FAILED,
                "error": "Session is not awaiting clarification",
            }

        turn = session.get_current_turn()
        if not turn:
            return {
                "status": QueryStatus.FAILED,
                "error": "No active turn found",
            }

        turn.answer_clarification(answer)
        session.status = QueryStatus.PROCESSING

        config = self._make_config(session.session_id)

        try:
            result = await self.graph.ainvoke(Command(resume=answer), config)
            return await self._process_result(session, result, config, turn)
        except Exception as e:
            logger.error(f"Continue conversation failed: {e}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            return {
                "status": QueryStatus.FAILED,
                "error": str(e),
            }

    async def stream_continue_conversation(
        self,
        session: Session,
        answer: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if session.status != QueryStatus.AWAITING_CLARIFICATION:
            yield {
                "event": "error",
                "data": {
                    "session_id": session.session_id,
                    "error": "Session is not awaiting clarification",
                },
            }
            return

        turn = session.get_current_turn()
        if not turn:
            yield {
                "event": "error",
                "data": {
                    "session_id": session.session_id,
                    "error": "No active turn found",
                },
            }
            return

        turn.answer_clarification(answer)
        session.status = QueryStatus.PROCESSING

        config = self._make_config(session.session_id)

        try:
            yield {"event": "start", "data": {"session_id": session.session_id}}

            last_state: dict[str, Any] = {}
            async for chunk in self.graph.astream(
                Command(resume=answer), config, stream_mode=["updates", "custom"]
            ):
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    mode, data = chunk
                    if mode == "custom" and isinstance(data, dict):
                        yield {
                            "event": "agent_progress",
                            "data": {"session_id": session.session_id, **data},
                        }
                    elif mode == "updates" and isinstance(data, dict):
                        for node_name, updates in data.items():
                            if not isinstance(updates, dict):
                                continue
                            last_state.update(updates)
                            sanitized_updates = self._sanitize_output(updates)
                            yield {
                                "event": "state_update",
                                "data": {
                                    "session_id": session.session_id,
                                    "node": node_name,
                                    **sanitized_updates,
                                },
                            }
                elif isinstance(chunk, dict):
                    for node_name, updates in chunk.items():
                        if not isinstance(updates, dict):
                            continue
                        last_state.update(updates)
                        sanitized_updates = self._sanitize_output(updates)
                        yield {
                            "event": "state_update",
                            "data": {
                                "session_id": session.session_id,
                                "node": node_name,
                                **sanitized_updates,
                            },
                        }

            snapshot = await self.graph.aget_state(config)
            final_state = snapshot.values if snapshot else last_state

            final_result = await self._process_result(session, dict(final_state), config, turn)
            final_result["session_id"] = session.session_id

            yield {"event": "complete", "data": final_result}

        except Exception as e:
            logger.error(f"Stream continue conversation failed: {e}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            yield {"event": "error", "data": {"session_id": session.session_id, "error": str(e)}}

    async def _process_result(
        self,
        session: Session,
        result: dict[str, Any],
        config: dict[str, Any],
        turn: Any,
    ) -> dict[str, Any]:
        from easysql_api.models.turn import Turn

        if not isinstance(turn, Turn):
            raise TypeError("turn must be a Turn instance")

        snapshot = await self.graph.aget_state(config)

        if snapshot.next and "clarify" in snapshot.next:
            questions = self._extract_clarification_questions(snapshot, result)
            turn.add_clarification(questions)
            session.status = QueryStatus.AWAITING_CLARIFICATION
            session.clarification_questions = questions
            session.state = dict(result) if result else None
            session.touch()

            return {
                "status": QueryStatus.AWAITING_CLARIFICATION.value,
                "clarification": {"questions": questions},
                "turn_id": turn.turn_id,
            }

        sql = result.get("generated_sql")
        validation_passed = result.get("validation_passed", False)
        turn.complete(sql, validation_passed)

        session.generated_sql = sql
        session.validation_passed = validation_passed
        session.status = QueryStatus.COMPLETED
        session.state = dict(result) if result else None
        session.touch()

        response: dict[str, Any] = {
            "status": QueryStatus.COMPLETED.value,
            "sql": session.generated_sql,
            "validation_passed": session.validation_passed,
            "turn_id": turn.turn_id,
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

    async def stream_query(
        self,
        session: Session,
        question: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        session.raw_query = question
        session.status = QueryStatus.PROCESSING
        turn = session.create_turn(question)

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

        config = self._make_config(session.session_id)

        try:
            yield {"event": "start", "data": {"session_id": session.session_id}}

            last_state: dict[str, Any] = {}
            async for chunk in self.graph.astream(
                input_state, config, stream_mode=["updates", "custom"]
            ):
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    mode, data = chunk
                    if mode == "custom" and isinstance(data, dict):
                        yield {
                            "event": "agent_progress",
                            "data": {"session_id": session.session_id, **data},
                        }
                    elif mode == "updates" and isinstance(data, dict):
                        for node_name, updates in data.items():
                            if not isinstance(updates, dict):
                                continue
                            last_state.update(updates)
                            sanitized_updates = self._sanitize_output(updates)
                            yield {
                                "event": "state_update",
                                "data": {
                                    "session_id": session.session_id,
                                    "node": node_name,
                                    **sanitized_updates,
                                },
                            }
                elif isinstance(chunk, dict):
                    for node_name, updates in chunk.items():
                        if not isinstance(updates, dict):
                            continue
                        last_state.update(updates)
                        sanitized_updates = self._sanitize_output(updates)
                        yield {
                            "event": "state_update",
                            "data": {
                                "session_id": session.session_id,
                                "node": node_name,
                                **sanitized_updates,
                            },
                        }

            snapshot = await self.graph.aget_state(config)
            final_state = snapshot.values if snapshot else last_state

            final_result = await self._process_result(session, dict(final_state), config, turn)
            final_result["session_id"] = session.session_id

            yield {"event": "complete", "data": final_result}

        except Exception as e:
            logger.exception(f"Stream query failed: {type(e).__name__}: {e!r}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            yield {
                "event": "error",
                "data": {"session_id": session.session_id, "error": f"{type(e).__name__}: {e!r}"},
            }

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

    async def follow_up_query(
        self,
        session: Session,
        question: str,
        parent_message_id: str | None = None,
    ) -> dict[str, Any]:
        if session.status not in (QueryStatus.COMPLETED, QueryStatus.AWAITING_CLARIFICATION):
            return {
                "status": QueryStatus.FAILED,
                "error": "Session must be completed or awaiting clarification for follow-up",
            }

        session.raw_query = question
        session.status = QueryStatus.PROCESSING
        turn = session.create_turn(question)

        config = self._make_config(session.session_id)

        snapshot = await self.graph.aget_state(config)
        prev_state = snapshot.values if snapshot else {}

        conversation_history = prev_state.get("conversation_history", [])
        if prev_state.get("generated_sql"):
            conversation_history = conversation_history + [
                {
                    "message_id": parent_message_id or str(uuid.uuid4()),
                    "question": prev_state.get("raw_query", ""),
                    "sql": prev_state.get("generated_sql"),
                    "tables_used": prev_state.get("retrieval_result", {}).get("tables", []),
                    "token_count": prev_state.get("context_output", {}).get("total_tokens", 0),
                }
            ]

        input_state: dict[str, Any] = {
            "raw_query": question,
            "parent_message_id": parent_message_id,
            "conversation_history": conversation_history,
            "generated_sql": None,
            "validation_passed": False,
            "validation_result": None,
            "retry_count": 0,
            "error": None,
            "needs_new_retrieval": False,
            "db_name": session.db_name,
        }

        try:
            result = await self.graph.ainvoke(input_state, config)
            return await self._process_result(session, result, config, turn)
        except Exception as e:
            logger.error(f"Follow-up query failed: {e}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            return {"status": QueryStatus.FAILED, "error": str(e)}

    async def stream_follow_up_query(
        self,
        session: Session,
        question: str,
        parent_message_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if session.status not in (QueryStatus.COMPLETED, QueryStatus.AWAITING_CLARIFICATION):
            yield {
                "event": "error",
                "data": {
                    "session_id": session.session_id,
                    "error": "Invalid session status for follow-up",
                },
            }
            return

        session.raw_query = question
        session.status = QueryStatus.PROCESSING
        turn = session.create_turn(question)

        config = self._make_config(session.session_id)

        snapshot = await self.graph.aget_state(config)
        prev_state = snapshot.values if snapshot else {}

        conversation_history = prev_state.get("conversation_history", [])
        if prev_state.get("generated_sql"):
            conversation_history = conversation_history + [
                {
                    "message_id": parent_message_id or str(uuid.uuid4()),
                    "question": prev_state.get("raw_query", ""),
                    "sql": prev_state.get("generated_sql"),
                    "tables_used": prev_state.get("retrieval_result", {}).get("tables", []),
                    "token_count": prev_state.get("context_output", {}).get("total_tokens", 0),
                }
            ]

        input_state: dict[str, Any] = {
            "raw_query": question,
            "parent_message_id": parent_message_id,
            "conversation_history": conversation_history,
            "generated_sql": None,
            "validation_passed": False,
            "validation_result": None,
            "retry_count": 0,
            "error": None,
            "needs_new_retrieval": False,
            "db_name": session.db_name,
        }

        try:
            yield {"event": "start", "data": {"session_id": session.session_id}}

            last_state: dict[str, Any] = {}
            async for chunk in self.graph.astream(
                input_state, config, stream_mode=["updates", "custom"]
            ):
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    mode, data = chunk
                    if mode == "custom" and isinstance(data, dict):
                        yield {
                            "event": "agent_progress",
                            "data": {"session_id": session.session_id, **data},
                        }
                    elif mode == "updates" and isinstance(data, dict):
                        for node_name, updates in data.items():
                            if not isinstance(updates, dict):
                                continue
                            last_state.update(updates)
                            sanitized_updates = self._sanitize_output(updates)
                            yield {
                                "event": "state_update",
                                "data": {
                                    "session_id": session.session_id,
                                    "node": node_name,
                                    **sanitized_updates,
                                },
                            }
                elif isinstance(chunk, dict):
                    for node_name, updates in chunk.items():
                        if not isinstance(updates, dict):
                            continue
                        last_state.update(updates)
                        sanitized_updates = self._sanitize_output(updates)
                        yield {
                            "event": "state_update",
                            "data": {
                                "session_id": session.session_id,
                                "node": node_name,
                                **sanitized_updates,
                            },
                        }

            snapshot = await self.graph.aget_state(config)
            final_state = snapshot.values if snapshot else last_state
            final_result = await self._process_result(session, dict(final_state), config, turn)
            final_result["session_id"] = session.session_id

            yield {"event": "complete", "data": final_result}

        except Exception as e:
            logger.error(f"Stream follow-up query failed: {e}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            yield {"event": "error", "data": {"session_id": session.session_id, "error": str(e)}}


_default_service: QueryService | None = None


def get_query_service() -> QueryService:
    global _default_service
    if _default_service is None:
        _default_service = QueryService()
    return _default_service
