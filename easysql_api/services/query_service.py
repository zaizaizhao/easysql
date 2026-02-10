from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from copy import deepcopy
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.types import Command

from easysql.config import get_settings
from easysql.llm import build_graph, get_langfuse_callbacks
from easysql.utils.logger import get_logger
from easysql_api.domain.entities.session import Session
from easysql_api.domain.entities.turn import Clarification, Turn
from easysql_api.domain.repositories.session_repository import SessionRepository
from easysql_api.domain.value_objects.query_status import QueryStatus

logger = get_logger(__name__)


class QueryService:
    def __init__(self, repository: SessionRepository) -> None:
        self._graph: Any = None
        self._repo = repository
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

    def _make_config(self, session_id: str, thread_id: str | None = None) -> dict[str, Any]:
        effective_thread_id = thread_id or session_id
        config: dict[str, Any] = {"configurable": {"thread_id": effective_thread_id}}
        if self.callbacks:
            config["callbacks"] = self.callbacks
            logger.debug(f"LangFuse callbacks attached: {len(self.callbacks)} handler(s)")
        return config

    async def create_session(self, db_name: str | None = None) -> Session:
        if not db_name:
            settings = get_settings()
            databases = settings.databases
            if databases:
                db_name = next(iter(databases.keys()))
                logger.info(f"No db_name provided, defaulting to: {db_name}")
            else:
                logger.warning("No databases configured in settings!")

        session_id = str(uuid.uuid4())
        return await self._repo.create(session_id, db_name)

    async def get_session(self, session_id: str) -> Session | None:
        return await self._repo.get(session_id)

    async def _update_status(self, session_id: str, status: QueryStatus) -> None:
        await self._repo.update_status(session_id, status)

    async def _save_turns(self, session_id: str, turns: list[Turn]) -> None:
        await self._repo.save_turns(session_id, turns)

    async def _update_session_fields(self, session_id: str, **kwargs: Any) -> None:
        if "state" in kwargs:
            kwargs["state"] = self._sanitize_state(kwargs.get("state"))
        await self._repo.update_session_fields(session_id, **kwargs)

    def _estimate_turn_tokens(self, question: str, sql: str | None) -> int:
        text = question + (sql or "")
        return count_tokens_approximately([HumanMessage(content=text)])

    async def _resolve_parent_thread_id(
        self,
        session_id: str,
        parent_message_id: str | None,
        thread_id: str | None,
    ) -> str:
        if thread_id:
            return thread_id
        if parent_message_id:
            message = await self._repo.get_message(parent_message_id)
            if message and message.thread_id:
                return message.thread_id
        return session_id

    async def _build_branch_history(
        self,
        session_id: str,
        parent_thread_id: str,
        parent_message_id: str | None,
    ) -> list[dict[str, Any]]:
        config = self._make_config(session_id, parent_thread_id)
        snapshot = await self.graph.aget_state(config)
        prev_state = snapshot.values if snapshot else {}
        history = list(prev_state.get("conversation_history", []) or [])

        if not parent_message_id:
            return history

        for idx, turn in enumerate(history):
            if turn.get("message_id") == parent_message_id:
                return history[: idx + 1]

        return history

    @staticmethod
    def _derive_turn_counter(turns: list[Turn]) -> int:
        max_counter = 0
        for turn in turns:
            parts = turn.turn_id.split("-")
            if len(parts) != 2:
                continue
            try:
                max_counter = max(max_counter, int(parts[1]))
            except ValueError:
                continue
        return max_counter or len(turns)

    @staticmethod
    def _clone_turn(turn: Turn) -> Turn:
        return Turn(
            turn_id=turn.turn_id,
            question=turn.question,
            status=turn.status,
            clarifications=[
                Clarification(questions=list(item.questions), answer=item.answer)
                for item in turn.clarifications
            ],
            final_sql=turn.final_sql,
            validation_passed=turn.validation_passed,
            error=turn.error,
            chart_plan=deepcopy(turn.chart_plan),
            chart_reasoning=turn.chart_reasoning,
            created_at=turn.created_at,
        )

    def _clone_turns_by_ids(self, source_session: Session, turn_ids: list[str]) -> list[Turn]:
        if not turn_ids:
            return []

        turn_map = {turn.turn_id: turn for turn in source_session.turns}
        ordered_ids = list(dict.fromkeys(turn_ids))

        missing_ids = [turn_id for turn_id in ordered_ids if turn_id not in turn_map]
        if missing_ids:
            raise ValueError(f"Turn IDs not found in source session: {', '.join(missing_ids)}")

        return [self._clone_turn(turn_map[turn_id]) for turn_id in ordered_ids]

    async def fork_session_with_branch_context(
        self,
        source_session: Session,
        *,
        from_message_id: str | None,
        thread_id: str | None,
        turn_ids: list[str],
    ) -> dict[str, Any]:
        target_session = await self.create_session(db_name=source_session.db_name)

        cloned_turns = self._clone_turns_by_ids(source_session, turn_ids)
        parent_thread_id = await self._resolve_parent_thread_id(
            source_session.session_id,
            from_message_id,
            thread_id,
        )

        parent_snapshot = await self.graph.aget_state(
            self._make_config(source_session.session_id, parent_thread_id)
        )
        parent_state = parent_snapshot.values if parent_snapshot else {}

        conversation_history = await self._build_branch_history(
            source_session.session_id,
            parent_thread_id,
            from_message_id,
        )

        if cloned_turns:
            target_session.turns = cloned_turns
            target_session._turn_counter = self._derive_turn_counter(cloned_turns)
            latest_turn = cloned_turns[-1]
            target_session.raw_query = latest_turn.question
            target_session.generated_sql = latest_turn.final_sql
            target_session.validation_passed = latest_turn.validation_passed
        elif conversation_history:
            latest_history_turn = conversation_history[-1]
            target_session.raw_query = latest_history_turn.get("question")
            target_session.generated_sql = latest_history_turn.get("sql")
            target_session.validation_passed = latest_history_turn.get("validation_passed")

        target_session.state = self._sanitize_state(
            {
                "fork_conversation_history": conversation_history,
                "fork_cached_context": parent_state.get("cached_context"),
                "fork_retrieval_result": parent_state.get("retrieval_result"),
            }
        )

        if cloned_turns or conversation_history:
            target_session.status = QueryStatus.COMPLETED
            await self._update_status(target_session.session_id, target_session.status)

        await self._update_session_fields(
            target_session.session_id,
            raw_query=target_session.raw_query,
            generated_sql=target_session.generated_sql,
            validation_passed=target_session.validation_passed,
            state=target_session.state,
        )

        if cloned_turns:
            await self._save_turns(target_session.session_id, target_session.turns)

        return {
            "session_id": target_session.session_id,
            "thread_id": target_session.session_id,
            "status": target_session.status.value,
            "source_session_id": source_session.session_id,
            "cloned_turn_ids": [turn.turn_id for turn in cloned_turns],
        }

    async def _persist_messages(
        self,
        *,
        session_id: str,
        thread_id: str,
        user_message_id: str,
        assistant_message_id: str,
        parent_message_id: str | None,
        question: str,
        sql: str | None,
        tables_used: list[str],
        validation_passed: bool | None,
        error: str | None,
        clarification_questions: list[str] | None,
    ) -> None:
        normalized_parent_id: str | None = None
        if parent_message_id:
            try:
                parent_message = await self._repo.get_message(parent_message_id)
                if parent_message and parent_message.session_id == session_id:
                    normalized_parent_id = parent_message_id
                else:
                    logger.warning(
                        "Parent message not found or session mismatch; dropping parent_id "
                        "session_id={} parent_message_id={}",
                        session_id,
                        parent_message_id,
                    )
            except Exception as exc:  # noqa: BLE001 - invalid UUID or repo error
                logger.warning(
                    "Invalid parent_message_id; dropping parent_id session_id={} "
                    "parent_message_id={} error={}",
                    session_id,
                    parent_message_id,
                    f"{type(exc).__name__}: {exc}",
                )

        await self._repo.add_message(
            session_id=session_id,
            message_id=user_message_id,
            thread_id=thread_id,
            role="user",
            content=question,
            parent_id=normalized_parent_id,
        )

        await self._repo.add_message(
            session_id=session_id,
            message_id=assistant_message_id,
            thread_id=thread_id,
            role="assistant",
            content=sql or error,
            parent_id=user_message_id,
            generated_sql=sql,
            tables_used=tables_used,
            validation_passed=validation_passed,
            clarification_questions=clarification_questions,
        )

    async def execute_query(
        self,
        session: Session,
        question: str,
    ) -> dict[str, Any]:
        session.raw_query = question
        session.status = QueryStatus.PROCESSING
        turn = session.create_turn(question)
        await self._update_status(session.session_id, session.status)
        await self._update_session_fields(
            session.session_id,
            raw_query=session.raw_query,
            state=session.state,
        )
        await self._save_turns(session.session_id, session.turns)

        thread_id = session.session_id
        user_message_id = str(uuid.uuid4())
        assistant_message_id = str(uuid.uuid4())

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
            "current_message_id": assistant_message_id,
            "parent_message_id": None,
        }

        config = self._make_config(session.session_id, thread_id)

        try:
            result = await self.graph.ainvoke(input_state, config)
            return await self._process_result(
                session,
                result,
                config,
                turn,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                parent_message_id=None,
                thread_id=thread_id,
                question=question,
            )
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            await self._update_status(session.session_id, session.status)
            await self._save_turns(session.session_id, session.turns)
            return {
                "status": QueryStatus.FAILED,
                "error": str(e),
                "message_id": assistant_message_id,
                "parent_message_id": None,
                "thread_id": thread_id,
            }

    async def continue_conversation(
        self,
        session: Session,
        answer: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        if session.status != QueryStatus.AWAITING_CLARIFY:
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
        await self._update_status(session.session_id, session.status)

        config = self._make_config(session.session_id, thread_id)

        try:
            result = await self.graph.ainvoke(Command(resume=answer), config)
            return await self._process_result(
                session,
                result,
                config,
                turn,
                user_message_id=None,
                assistant_message_id=None,
                parent_message_id=None,
                thread_id=thread_id or session.session_id,
                question=session.raw_query or "",
            )
        except Exception as e:
            logger.error(f"Continue conversation failed: {e}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            await self._update_status(session.session_id, session.status)
            await self._save_turns(session.session_id, session.turns)
            return {
                "status": QueryStatus.FAILED,
                "error": str(e),
                "thread_id": thread_id or session.session_id,
            }

    async def stream_continue_conversation(
        self,
        session: Session,
        answer: str,
        thread_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if session.status != QueryStatus.AWAITING_CLARIFY:
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
        await self._update_status(session.session_id, session.status)

        config = self._make_config(session.session_id, thread_id)

        try:
            yield {
                "event": "start",
                "data": {
                    "session_id": session.session_id,
                    "thread_id": thread_id or session.session_id,
                    "turn_id": turn.turn_id,
                },
            }

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

            final_result = await self._process_result(
                session,
                dict(final_state),
                config,
                turn,
                user_message_id=None,
                assistant_message_id=None,
                parent_message_id=None,
                thread_id=thread_id or session.session_id,
                question=session.raw_query or "",
            )
            final_result["session_id"] = session.session_id

            yield {"event": "complete", "data": final_result}

        except Exception as e:
            logger.error(f"Stream continue conversation failed: {e}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            await self._update_status(session.session_id, session.status)
            await self._save_turns(session.session_id, session.turns)
            yield {
                "event": "error",
                "data": {
                    "session_id": session.session_id,
                    "thread_id": thread_id or session.session_id,
                    "error": str(e),
                },
            }

    async def _process_result(
        self,
        session: Session,
        result: dict[str, Any],
        config: dict[str, Any],
        turn: Turn,
        *,
        user_message_id: str | None,
        assistant_message_id: str | None,
        parent_message_id: str | None,
        thread_id: str,
        question: str,
    ) -> dict[str, Any]:
        if not isinstance(turn, Turn):
            raise TypeError("turn must be a Turn instance")

        snapshot = await self.graph.aget_state(config)

        if snapshot.next and "clarify" in snapshot.next:
            questions = self._extract_clarification_questions(snapshot, result)
            turn.add_clarification(questions)
            session.status = QueryStatus.AWAITING_CLARIFY
            session.clarification_questions = questions
            session.state = self._sanitize_state(result)
            session.touch()
            await self._update_status(session.session_id, session.status)
            await self._update_session_fields(
                session.session_id,
                raw_query=session.raw_query,
                generated_sql=session.generated_sql,
                validation_passed=session.validation_passed,
                state=session.state,
            )
            await self._save_turns(session.session_id, session.turns)

            clarify_response: dict[str, Any] = {
                "status": QueryStatus.AWAITING_CLARIFY.value,
                "clarification": {"questions": questions},
                "turn_id": turn.turn_id,
                "message_id": assistant_message_id,
                "parent_message_id": parent_message_id,
                "thread_id": thread_id,
            }
            return clarify_response

        sql = result.get("generated_sql")
        validation_passed = result.get("validation_passed", False)
        turn.complete(sql, validation_passed)

        session.generated_sql = sql
        session.validation_passed = validation_passed
        session.status = QueryStatus.COMPLETED
        session.state = self._sanitize_state(result)
        session.touch()
        await self._update_status(session.session_id, session.status)
        await self._update_session_fields(
            session.session_id,
            raw_query=session.raw_query,
            generated_sql=session.generated_sql,
            validation_passed=session.validation_passed,
            state=session.state,
        )
        await self._save_turns(session.session_id, session.turns)

        response: dict[str, Any] = {
            "status": QueryStatus.COMPLETED.value,
            "sql": session.generated_sql,
            "validation_passed": session.validation_passed,
            "turn_id": turn.turn_id,
            "message_id": assistant_message_id,
            "parent_message_id": parent_message_id,
            "thread_id": thread_id,
        }

        # Include chart plan and reasoning if available
        if turn.chart_plan is not None:
            response["chart_plan"] = turn.chart_plan
        if turn.chart_reasoning is not None:
            response["chart_reasoning"] = turn.chart_reasoning

        if not session.validation_passed:
            validation_result = result.get("validation_result", {})
            response["validation_error"] = result.get("error") or validation_result.get("error")

        if user_message_id and assistant_message_id:
            tables_used = result.get("retrieval_result", {}).get("tables", [])
            await self._persist_messages(
                session_id=session.session_id,
                thread_id=thread_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                parent_message_id=parent_message_id,
                question=question,
                sql=session.generated_sql,
                tables_used=tables_used,
                validation_passed=session.validation_passed,
                error=result.get("error"),
                clarification_questions=result.get("clarification_questions"),
            )

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
        await self._update_status(session.session_id, session.status)
        await self._update_session_fields(
            session.session_id,
            raw_query=session.raw_query,
            state=session.state,
        )
        await self._save_turns(session.session_id, session.turns)

        thread_id = session.session_id
        user_message_id = str(uuid.uuid4())
        assistant_message_id = str(uuid.uuid4())

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
            "current_message_id": assistant_message_id,
            "parent_message_id": None,
        }

        config = self._make_config(session.session_id, thread_id)

        try:
            yield {
                "event": "start",
                "data": {
                    "session_id": session.session_id,
                    "thread_id": thread_id,
                    "message_id": assistant_message_id,
                    "parent_message_id": None,
                    "turn_id": turn.turn_id,
                },
            }

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

            final_result = await self._process_result(
                session,
                dict(final_state),
                config,
                turn,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                parent_message_id=None,
                thread_id=thread_id,
                question=question,
            )
            final_result["session_id"] = session.session_id

            yield {"event": "complete", "data": final_result}

        except Exception as e:
            logger.exception(f"Stream query failed: {type(e).__name__}: {e!r}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            await self._update_status(session.session_id, session.status)
            await self._save_turns(session.session_id, session.turns)
            yield {
                "event": "error",
                "data": {
                    "session_id": session.session_id,
                    "thread_id": thread_id,
                    "message_id": assistant_message_id,
                    "parent_message_id": None,
                    "error": f"{type(e).__name__}: {e!r}",
                },
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

    def _summarize_schema_hint(self, schema_hint: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(schema_hint, dict):
            return {}
        tables = schema_hint.get("tables", [])
        table_names: list[str] = []
        if isinstance(tables, list):
            for item in tables:
                if isinstance(item, dict):
                    name = item.get("name")
                    if isinstance(name, str) and name:
                        table_names.append(name)
        semantic_columns = schema_hint.get("semantic_columns", [])
        semantic_count = len(semantic_columns) if isinstance(semantic_columns, list) else 0

        summary = {"tables_count": len(table_names), "tables": table_names[:10]}
        if semantic_count:
            summary["semantic_columns_count"] = semantic_count
        return summary

    def _sanitize_state(self, state: dict[str, Any] | None) -> dict[str, Any] | None:
        if not state or not isinstance(state, dict):
            return None
        sanitized: dict[str, Any] = {}
        safe_keys = {
            "generated_sql",
            "validation_passed",
            "validation_result",
            "clarification_questions",
            "clarified_query",
            "error",
            "fork_conversation_history",
            "fork_cached_context",
            "fork_retrieval_result",
        }
        for key in safe_keys:
            value = state.get(key)
            if value is not None:
                sanitized[key] = value

        if state.get("schema_hint"):
            schema_hint_summary = self._summarize_schema_hint(state["schema_hint"])
            if schema_hint_summary:
                sanitized["schema_hint_summary"] = schema_hint_summary

        if state.get("retrieval_result"):
            rr = state["retrieval_result"]
            if isinstance(rr, dict):
                sanitized["retrieval_summary"] = {
                    "tables_count": len(rr.get("tables", [])),
                    "tables": rr.get("tables", [])[:10],
                }

        if state.get("context_output"):
            co = state["context_output"]
            if isinstance(co, dict):
                sanitized["context_summary"] = {
                    "total_tokens": co.get("total_tokens"),
                    "has_system_prompt": bool(co.get("system_prompt")),
                    "has_user_prompt": bool(co.get("user_prompt")),
                }

        if state.get("history_summary"):
            sanitized["history_summary"] = state["history_summary"]

        if state.get("shift_reason"):
            sanitized["shift_reason"] = state["shift_reason"]

        if state.get("needs_new_retrieval") is not None:
            sanitized["needs_new_retrieval"] = state["needs_new_retrieval"]

        return sanitized or None

    async def follow_up_query(
        self,
        session: Session,
        question: str,
        parent_message_id: str | None = None,
        thread_id: str | None = None,
        create_branch: bool = False,
    ) -> dict[str, Any]:
        if session.status not in (QueryStatus.COMPLETED, QueryStatus.AWAITING_CLARIFY):
            return {
                "status": QueryStatus.FAILED,
                "error": "Session must be completed or awaiting clarification for follow-up",
            }

        session.raw_query = question
        session.status = QueryStatus.PROCESSING
        turn = session.create_turn(question)
        await self._update_status(session.session_id, session.status)
        await self._update_session_fields(
            session.session_id,
            raw_query=session.raw_query,
            state=session.state,
        )
        await self._save_turns(session.session_id, session.turns)

        user_message_id = str(uuid.uuid4())
        assistant_message_id = str(uuid.uuid4())

        if create_branch:
            parent_thread_id = await self._resolve_parent_thread_id(
                session.session_id, parent_message_id, thread_id
            )
            effective_thread_id = f"{session.session_id}:{uuid.uuid4()}"

            parent_snapshot = await self.graph.aget_state(
                self._make_config(session.session_id, parent_thread_id)
            )
            parent_state = parent_snapshot.values if parent_snapshot else {}

            conversation_history = await self._build_branch_history(
                session.session_id, parent_thread_id, parent_message_id
            )
            cached_context = parent_state.get("cached_context")
            retrieval_result = parent_state.get("retrieval_result")
        else:
            effective_thread_id = thread_id or session.session_id
            snapshot = await self.graph.aget_state(
                self._make_config(session.session_id, effective_thread_id)
            )
            session_state = session.state if isinstance(session.state, dict) else {}
            prev_state = snapshot.values if snapshot else session_state

            fallback_history = session_state.get("fork_conversation_history")
            conversation_history = prev_state.get("conversation_history") or (
                fallback_history if isinstance(fallback_history, list) else []
            )
            if not conversation_history and prev_state.get("generated_sql"):
                token_count = self._estimate_turn_tokens(
                    prev_state.get("raw_query", ""), prev_state.get("generated_sql")
                )
                conversation_history = conversation_history + [
                    {
                        "message_id": parent_message_id or str(uuid.uuid4()),
                        "question": prev_state.get("raw_query", ""),
                        "sql": prev_state.get("generated_sql"),
                        "tables_used": prev_state.get("retrieval_result", {}).get("tables", []),
                        "token_count": token_count,
                    }
                ]
            cached_context = prev_state.get("cached_context")
            if cached_context is None:
                cached_context = session_state.get("fork_cached_context")
            retrieval_result = prev_state.get("retrieval_result")
            if retrieval_result is None:
                retrieval_result = session_state.get("fork_retrieval_result")

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
            "cached_context": cached_context,
            "retrieval_result": retrieval_result,
            "current_message_id": assistant_message_id,
        }

        try:
            config = self._make_config(session.session_id, effective_thread_id)
            result = await self.graph.ainvoke(input_state, config)
            return await self._process_result(
                session,
                result,
                config,
                turn,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                parent_message_id=parent_message_id,
                thread_id=effective_thread_id,
                question=question,
            )
        except Exception as e:
            logger.error(f"Follow-up query failed: {e}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            await self._update_status(session.session_id, session.status)
            await self._save_turns(session.session_id, session.turns)
            return {
                "status": QueryStatus.FAILED,
                "error": str(e),
                "message_id": assistant_message_id,
                "parent_message_id": parent_message_id,
                "thread_id": effective_thread_id,
            }

    async def stream_follow_up_query(
        self,
        session: Session,
        question: str,
        parent_message_id: str | None = None,
        thread_id: str | None = None,
        create_branch: bool = False,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if session.status not in (QueryStatus.COMPLETED, QueryStatus.AWAITING_CLARIFY):
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
        await self._update_status(session.session_id, session.status)
        await self._update_session_fields(
            session.session_id,
            raw_query=session.raw_query,
            state=session.state,
        )
        await self._save_turns(session.session_id, session.turns)

        user_message_id = str(uuid.uuid4())
        assistant_message_id = str(uuid.uuid4())

        if create_branch:
            parent_thread_id = await self._resolve_parent_thread_id(
                session.session_id, parent_message_id, thread_id
            )
            effective_thread_id = f"{session.session_id}:{uuid.uuid4()}"

            parent_snapshot = await self.graph.aget_state(
                self._make_config(session.session_id, parent_thread_id)
            )
            parent_state = parent_snapshot.values if parent_snapshot else {}

            conversation_history = await self._build_branch_history(
                session.session_id, parent_thread_id, parent_message_id
            )
            cached_context = parent_state.get("cached_context")
            retrieval_result = parent_state.get("retrieval_result")
        else:
            effective_thread_id = thread_id or session.session_id
            snapshot = await self.graph.aget_state(
                self._make_config(session.session_id, effective_thread_id)
            )
            session_state = session.state if isinstance(session.state, dict) else {}
            prev_state = snapshot.values if snapshot else session_state

            fallback_history = session_state.get("fork_conversation_history")
            conversation_history = prev_state.get("conversation_history") or (
                fallback_history if isinstance(fallback_history, list) else []
            )
            if not conversation_history and prev_state.get("generated_sql"):
                token_count = self._estimate_turn_tokens(
                    prev_state.get("raw_query", ""), prev_state.get("generated_sql")
                )
                conversation_history = conversation_history + [
                    {
                        "message_id": parent_message_id or str(uuid.uuid4()),
                        "question": prev_state.get("raw_query", ""),
                        "sql": prev_state.get("generated_sql"),
                        "tables_used": prev_state.get("retrieval_result", {}).get("tables", []),
                        "token_count": token_count,
                    }
                ]
            cached_context = prev_state.get("cached_context")
            if cached_context is None:
                cached_context = session_state.get("fork_cached_context")
            retrieval_result = prev_state.get("retrieval_result")
            if retrieval_result is None:
                retrieval_result = session_state.get("fork_retrieval_result")

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
            "cached_context": cached_context,
            "retrieval_result": retrieval_result,
            "current_message_id": assistant_message_id,
        }

        try:
            yield {
                "event": "start",
                "data": {
                    "session_id": session.session_id,
                    "thread_id": effective_thread_id,
                    "message_id": assistant_message_id,
                    "parent_message_id": parent_message_id,
                    "turn_id": turn.turn_id,
                },
            }

            last_state: dict[str, Any] = {}
            async for chunk in self.graph.astream(
                input_state,
                self._make_config(session.session_id, effective_thread_id),
                stream_mode=["updates", "custom"],
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

            snapshot = await self.graph.aget_state(
                self._make_config(session.session_id, effective_thread_id)
            )
            final_state = snapshot.values if snapshot else last_state
            final_result = await self._process_result(
                session,
                dict(final_state),
                self._make_config(session.session_id, effective_thread_id),
                turn,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                parent_message_id=parent_message_id,
                thread_id=effective_thread_id,
                question=question,
            )
            final_result["session_id"] = session.session_id

            yield {"event": "complete", "data": final_result}

        except Exception as e:
            logger.error(f"Stream follow-up query failed: {e}")
            turn.fail(str(e))
            session.status = QueryStatus.FAILED
            session.touch()
            await self._update_status(session.session_id, session.status)
            await self._save_turns(session.session_id, session.turns)
            yield {
                "event": "error",
                "data": {
                    "session_id": session.session_id,
                    "thread_id": effective_thread_id,
                    "message_id": assistant_message_id,
                    "parent_message_id": parent_message_id,
                    "error": str(e),
                },
            }


_default_service: QueryService | None = None


def get_query_service(repository: SessionRepository) -> QueryService:
    global _default_service
    if _default_service is None:
        _default_service = QueryService(repository=repository)
    elif _default_service._repo is not repository:  # type: ignore[attr-defined]
        _default_service = QueryService(repository=repository)
    return _default_service
