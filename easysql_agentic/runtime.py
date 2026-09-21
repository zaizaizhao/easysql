"""ADK Runner adapter with persistent sessions and application-compatible progress."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.agents.run_config import RunConfig
from google.adk.apps import App
from google.adk.apps.app import EventsCompactionConfig
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, DatabaseSessionService
from google.genai import types

from easysql.config import get_settings
from easysql_agentic.agent import build_agent
from easysql_agentic.models import create_model
from easysql_agentic.tools.context import ContextTools
from easysql_api.infrastructure.db_manager import get_control_plane_db_manager

ProgressSink = Callable[[dict[str, Any]], Awaitable[None]]
_sessions: DatabaseSessionService | None = None


def get_adk_sessions() -> DatabaseSessionService:
    global _sessions
    if _sessions is None:
        _sessions = DatabaseSessionService(db_engine=get_control_plane_db_manager().get_engine())
    return _sessions


async def close_adk_sessions() -> None:
    global _sessions
    if _sessions is not None:
        await _sessions.close()
        _sessions = None


class AgentRuntime:
    def __init__(self, sessions: BaseSessionService | None = None, model: Any = None) -> None:
        self._sessions = sessions
        self._model = model

    @property
    def sessions(self) -> BaseSessionService:
        return self._sessions if self._sessions is not None else get_adk_sessions()

    @property
    def app_name(self) -> str:
        return "easysql_agentic_" + get_settings().project_namespace.replace("-", "_")

    async def ensure_session(self, user_id: str, thread_id: str) -> Any:
        session = await self.sessions.get_session(
            app_name=self.app_name, user_id=user_id, session_id=thread_id
        )
        if session is None:
            session = await self.sessions.create_session(
                app_name=self.app_name, user_id=user_id, session_id=thread_id
            )
        return session

    async def run(
        self,
        *,
        user_id: str,
        thread_id: str,
        question: str,
        tools: ContextTools,
        emit: ProgressSink,
    ) -> dict[str, Any]:
        settings = get_settings()
        await self.ensure_session(user_id, thread_id)
        agent = build_agent(self._model or create_model(settings.llm), tools)
        app = App(
            name=self.app_name,
            root_agent=agent,
            events_compaction_config=EventsCompactionConfig(compaction_interval=5, overlap_size=1),
        )
        runner = Runner(app=app, session_service=self.sessions)
        last_event_id = None
        tool_invocations = 0

        async def consume() -> None:
            nonlocal last_event_id, tool_invocations
            async for event in runner.run_async(
                user_id=user_id,
                session_id=thread_id,
                new_message=types.Content(role="user", parts=[types.Part(text=question)]),
                run_config=RunConfig(max_llm_calls=settings.llm.agent_max_iterations),
            ):
                last_event_id = event.id
                for call in event.get_function_calls() or []:
                    tool_invocations += 1
                    await emit(
                        {
                            "event": "agent_progress",
                            "data": {
                                "type": "tool_start",
                                "iteration": tools.model_calls,
                                "action": "tool_start",
                                "tool": call.name,
                                "input_preview": json.dumps(call.args, ensure_ascii=False)[:1500],
                            },
                        }
                    )
                for response in event.get_function_responses() or []:
                    data = response.response or {}
                    await emit(
                        {
                            "event": "agent_progress",
                            "data": {
                                "type": "tool_end",
                                "iteration": tools.model_calls,
                                "action": "tool_end",
                                "tool": response.name,
                                "success": not bool(data.get("error")),
                                "output_preview": json.dumps(data, ensure_ascii=False, default=str)[
                                    :2000
                                ],
                            },
                        }
                    )
            # Consume the iterator completely so ADK can persist tool actions and clean up.

        try:
            await asyncio.wait_for(consume(), timeout=settings.llm.agent_timeout_seconds)
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "error": "ADK agent exceeded its time budget",
                "validation_passed": False,
                "checkpoint_event_id": last_event_id,
            }
        except LlmCallsLimitExceededError:
            return {
                "status": "failed",
                "error": "ADK model-call budget exhausted before a validated answer",
                "validation_passed": False,
                "checkpoint_event_id": last_event_id,
            }
        outcome = tools.outcome or {
            "status": "failed",
            "validation_passed": False,
            "error": "The agent ended without validated SQL or a clarification request",
        }
        return {
            **outcome,
            "checkpoint_event_id": last_event_id,
            "stats": {
                "backend": "adk",
                "tool_calls": tool_invocations,
                "context_calls": tools.calls,
                "model_calls": tools.model_calls,
                "evidence_count": len(tools.evidence),
            },
        }

    async def clone_session(
        self,
        *,
        user_id: str,
        source_thread: str,
        target_user: str,
        target_thread: str,
        through_event: str | None,
    ) -> None:
        source = await self.sessions.get_session(
            app_name=self.app_name, user_id=user_id, session_id=source_thread
        )
        target = await self.ensure_session(target_user, target_thread)
        if source is None:
            return
        if through_event and not any(event.id == through_event for event in source.events):
            raise ValueError("The selected message has no ADK checkpoint in this branch")
        for event in source.events:
            cloned = event.model_copy(deep=True)
            await self.sessions.append_event(target, cloned)
            if through_event and event.id == through_event:
                break
