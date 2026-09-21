"""Current chat API implementation backed exclusively by the independent ADK agent."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress
from copy import deepcopy
from typing import Any

from easysql.config import get_settings
from easysql.federation import DatabaseScope
from easysql_agentic.dependencies import get_wiki_service
from easysql_agentic.knowledge.service import WikiService
from easysql_agentic.runtime import AgentRuntime
from easysql_agentic.tools.context import ContextTools
from easysql_api.domain.entities.session import Session
from easysql_api.domain.entities.turn import Turn
from easysql_api.domain.repositories.session_repository import SessionRepository
from easysql_api.domain.value_objects.query_status import QueryStatus


class AdkQueryService:
    def __init__(
        self,
        repository: SessionRepository,
        *,
        wiki: WikiService | None = None,
        runtime: AgentRuntime | None = None,
        tools_factory: Any = ContextTools,
    ) -> None:
        self.repository = repository
        self.wiki = wiki if wiki is not None else get_wiki_service()
        self.runtime = runtime or AgentRuntime()
        self.tools_factory = tools_factory

    async def create_session(
        self,
        db_name: str | None = None,
        db_names: list[str] | None = None,
    ) -> Session:
        scope = DatabaseScope.resolve(get_settings(), db_names=db_names, db_name=db_name)
        return await self.repository.create(
            str(uuid.uuid4()),
            db_name=scope.default_primary,
            db_names=scope.names,
            primary_db=scope.default_primary,
        )

    async def get_session(self, session_id: str) -> Session | None:
        return await self.repository.get(session_id)

    async def execute_query(self, session: Session, question: str) -> dict[str, Any]:
        return await self._collect(self.stream_query(session, question))

    async def continue_conversation(
        self,
        session: Session,
        answer: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._collect(self.stream_continue_conversation(session, answer, thread_id))

    async def follow_up_query(
        self,
        session: Session,
        question: str,
        parent_message_id: str | None = None,
        thread_id: str | None = None,
        create_branch: bool = False,
    ) -> dict[str, Any]:
        return await self._collect(
            self.stream_follow_up_query(
                session, question, parent_message_id, thread_id, create_branch
            )
        )

    @staticmethod
    async def _collect(stream: AsyncGenerator[dict[str, Any], None]) -> dict[str, Any]:
        result: dict[str, Any] = {"status": "failed", "error": "No agent result"}
        async for event in stream:
            if event["event"] in {"complete", "error"}:
                result = event["data"]
        return result

    def stream_query(self, session: Session, question: str) -> AsyncGenerator[dict[str, Any], None]:
        return self._stream(session, question)

    def stream_continue_conversation(
        self,
        session: Session,
        answer: str,
        thread_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        return self._stream(session, answer, thread_id=thread_id, continuation=True)

    def stream_follow_up_query(
        self,
        session: Session,
        question: str,
        parent_message_id: str | None = None,
        thread_id: str | None = None,
        create_branch: bool = False,
    ) -> AsyncGenerator[dict[str, Any], None]:
        return self._stream(
            session,
            question,
            parent_message_id=parent_message_id,
            thread_id=thread_id,
            create_branch=create_branch,
        )

    async def _stream(
        self,
        session: Session,
        question: str,
        *,
        thread_id: str | None = None,
        parent_message_id: str | None = None,
        create_branch: bool = False,
        continuation: bool = False,
    ) -> AsyncGenerator[dict[str, Any], None]:
        timeout = get_settings().llm.query_timeout_seconds
        task: asyncio.Task | None = None
        try:
            async with self.wiki.repository.lease("session:" + session.session_id, timeout + 60):
                # Re-read after acquiring the cross-process lease to avoid stale turn counters.
                session = await self.repository.get(session.session_id) or session
                parent = None
                if parent_message_id:
                    parent = await self.repository.get_message(parent_message_id)
                    if parent is None or parent.session_id != session.session_id:
                        raise ValueError("Parent message does not belong to this session")
                    if thread_id and thread_id != parent.thread_id:
                        raise ValueError("Parent message and thread do not match")
                source_thread = thread_id or (parent.thread_id if parent else session.session_id)
                state = deepcopy(session.state or {})
                checkpoints = state.setdefault("adk_checkpoints", {})
                if create_branch:
                    if parent is None:
                        raise ValueError("A branch requires a parent message")
                    checkpoint = checkpoints.get(parent_message_id)
                    if not checkpoint:
                        raise ValueError("This historical message has no ADK branch checkpoint")
                    effective_thread = str(uuid.uuid4())
                    await self.runtime.clone_session(
                        user_id=session.session_id,
                        source_thread=source_thread,
                        target_user=session.session_id,
                        target_thread=effective_thread,
                        through_event=checkpoint["event_id"],
                    )
                else:
                    effective_thread = source_thread
                    known_threads = {session.session_id, *state.get("adk_threads", [])}
                    if effective_thread not in known_threads:
                        raise ValueError("Unknown thread for this session")

                pending = state.setdefault("adk_pending", {})
                if continuation:
                    pending_turn = pending.get(effective_thread)
                    turn = session.get_turn(pending_turn) if pending_turn else None
                    if turn is None:
                        raise ValueError("No clarification is pending on this branch")
                    turn.answer_clarification(question)
                    agent_question = "用户对上一轮澄清问题的回答：" + question
                else:
                    turn = session.create_turn(question)
                    agent_question = question
                session.raw_query = turn.question
                await self.repository.update_status(session.session_id, QueryStatus.PROCESSING)
                await self.repository.save_turns(session.session_id, session.turns)
                user_message_id, assistant_message_id = str(uuid.uuid4()), str(uuid.uuid4())
                meta = {
                    "session_id": session.session_id,
                    "thread_id": effective_thread,
                    "message_id": assistant_message_id,
                    "parent_message_id": parent_message_id,
                    "turn_id": turn.turn_id,
                    "db_names": session.db_names,
                }
                yield {"event": "start", "data": meta}

                scope = DatabaseScope.resolve(
                    get_settings(), db_names=session.db_names, db_name=session.db_name
                )
                tools = self.tools_factory(scope, self.wiki)
                queue: asyncio.Queue = asyncio.Queue()

                async def run() -> dict[str, Any]:
                    try:
                        return await asyncio.wait_for(
                            self.runtime.run(
                                user_id=session.session_id,
                                thread_id=effective_thread,
                                question=agent_question,
                                tools=tools,
                                emit=queue.put,
                            ),
                            timeout=timeout,
                        )
                    finally:
                        await queue.put(None)

                task = asyncio.create_task(run())
                try:
                    while True:
                        try:
                            event = await asyncio.wait_for(queue.get(), timeout=15)
                        except asyncio.TimeoutError:
                            yield {
                                "event": "agent_progress",
                                "data": {"type": "thinking", "action": "thinking"},
                            }
                            continue
                        if event is None:
                            break
                        yield event
                    outcome = await task
                except asyncio.CancelledError:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                    turn.fail("Query cancelled")
                    await asyncio.shield(
                        self._save_outcome(
                            session, turn, {"status": "failed", "error": "Query cancelled"}, state
                        )
                    )
                    raise
                except Exception as exc:
                    outcome = {
                        "status": "failed",
                        "validation_passed": False,
                        "error": f"ADK query failed ({type(exc).__name__})",
                    }

                if outcome["status"] == "awaiting_clarify":
                    turn.add_clarification(outcome["clarification"]["questions"])
                    pending[effective_thread] = turn.turn_id
                else:
                    pending.pop(effective_thread, None)
                if outcome.get("checkpoint_event_id"):
                    checkpoints[assistant_message_id] = {
                        "event_id": outcome["checkpoint_event_id"],
                        "thread_id": effective_thread,
                        "turn_id": turn.turn_id,
                    }
                state["adk_threads"] = list(
                    dict.fromkeys([*state.get("adk_threads", []), effective_thread])
                )
                state["backend"] = "adk"
                state["last_evidence_ids"] = outcome.get("evidence_ids", [])
                state["last_knowledge_revisions"] = outcome.get("knowledge_revisions", {})
                await self._save_outcome(session, turn, outcome, state)
                await self.repository.add_message(
                    session.session_id,
                    message_id=user_message_id,
                    thread_id=effective_thread,
                    role="user",
                    content=question,
                    parent_id=parent_message_id,
                )
                await self.repository.add_message(
                    session.session_id,
                    message_id=assistant_message_id,
                    thread_id=effective_thread,
                    role="assistant",
                    content=outcome.get("sql") or outcome.get("error") or "需要澄清业务口径",
                    parent_id=user_message_id,
                    generated_sql=outcome.get("sql"),
                    tables_used=outcome.get("tables_used", []),
                    validation_passed=outcome.get("validation_passed"),
                    clarification_questions=outcome.get("clarification", {}).get("questions"),
                )
                yield {"event": "complete", "data": {**meta, **outcome}}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            message = (
                str(exc)
                if isinstance(exc, ValueError)
                else f"Request failed ({type(exc).__name__})"
            )
            yield {
                "event": "error",
                "data": {
                    "session_id": session.session_id,
                    "status": "failed",
                    "error": message,
                },
            }
        finally:
            if task is not None and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    async def _save_outcome(
        self,
        session: Session,
        turn: Turn,
        outcome: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        status = QueryStatus(outcome["status"])
        if status == QueryStatus.COMPLETED:
            turn.complete(outcome["sql"], True, outcome.get("primary_db"))
        elif status == QueryStatus.FAILED:
            turn.fail(outcome.get("error", "Agent could not complete the query"))
        session.status = status
        session.generated_sql = outcome.get("sql")
        session.validation_passed = outcome.get("validation_passed", False)
        session.primary_db = outcome.get("primary_db", session.primary_db)
        session.state = state
        await self.repository.update_session_fields(
            session.session_id,
            raw_query=session.raw_query,
            generated_sql=session.generated_sql,
            validation_passed=session.validation_passed,
            primary_db=session.primary_db,
            state=state,
        )
        await self.repository.save_turns(session.session_id, session.turns)
        await self.repository.update_status(session.session_id, status)

    async def fork_session_with_branch_context(
        self,
        source_session: Session,
        *,
        from_message_id: str | None,
        thread_id: str | None,
        turn_ids: list[str],
    ) -> dict[str, Any]:
        source_session = await self.repository.get(source_session.session_id) or source_session
        checkpoints = (source_session.state or {}).get("adk_checkpoints", {})
        if not from_message_id:
            from_message_id = next(reversed(checkpoints), None)
        checkpoint = checkpoints.get(from_message_id)
        if not checkpoint:
            raise ValueError("Select an ADK response to fork")
        message = await self.repository.get_message(from_message_id)
        if not message or message.session_id != source_session.session_id:
            raise ValueError("Source message does not belong to this session")
        if thread_id and thread_id != checkpoint["thread_id"]:
            raise ValueError("Source message and thread do not match")
        turn_map = {turn.turn_id: turn for turn in source_session.turns}
        if any(turn_id not in turn_map for turn_id in turn_ids):
            raise ValueError("Unknown turn selected for fork")
        target = await self.create_session(db_names=source_session.db_names)
        await self.runtime.clone_session(
            user_id=source_session.session_id,
            source_thread=checkpoint["thread_id"],
            target_user=target.session_id,
            target_thread=target.session_id,
            through_event=checkpoint["event_id"],
        )
        target.turns = [deepcopy(turn_map[turn_id]) for turn_id in dict.fromkeys(turn_ids)]
        await self.repository.save_turns(target.session_id, target.turns)
        await self.repository.update_session_fields(target.session_id, state={"backend": "adk"})
        return {
            "session_id": target.session_id,
            "source_session_id": source_session.session_id,
            "thread_id": target.session_id,
            "status": "pending",
            "cloned_turn_ids": turn_ids,
        }
