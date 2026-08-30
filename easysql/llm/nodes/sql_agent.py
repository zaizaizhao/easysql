"""
SQL Agent Node.

Uses LLM with tool-calling for iterative SQL generation and validation.
SQL is validated inside the agent loop before returning to frontend.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from time import perf_counter
from typing import TYPE_CHECKING, Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    convert_to_openai_messages,
)
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.types import StreamWriter

from easysql.config import get_settings
from easysql.context.db_specific_rules import get_db_specific_rules, get_db_type_from_config
from easysql.federation import DatabaseScope
from easysql.llm.models import get_llm
from easysql.llm.nodes.base import BaseNode
from easysql.llm.state import ContextOutputDict, EasySQLState
from easysql.llm.tools.agent_tools import get_agent_tools
from easysql.llm.utils.token_manager import get_token_manager
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

logger = get_logger(__name__)


def _get_langfuse_client():
    settings = get_settings()
    if not settings.langfuse.is_configured():
        return None

    try:
        from langfuse import get_client

        return get_client()
    except ImportError:
        logger.debug("Langfuse not installed, skipping tracing")
        return None
    except Exception as e:
        logger.debug(f"Failed to get Langfuse client: {e}")
        return None


@contextmanager
def _langfuse_span(name: str, **kwargs):
    langfuse = _get_langfuse_client()
    if langfuse is None:
        yield None
        return

    try:
        with langfuse.start_as_current_observation(
            as_type="span",
            name=name,
            **kwargs,
        ) as span:
            yield span
    except Exception as e:
        logger.debug(f"Langfuse span creation failed: {e}")
        yield None


AGENT_SYSTEM_PROMPT_BASE = """你是一个SQL专家。根据用户问题和提供的数据库Schema，生成正确的SQL查询。

## 可用工具
1. submit_final_sql - 提交并验证回答用户完整需求的最终SQL；SUCCESS 后任务立即结束
2. search_objects - 搜索数据库对象（表、列、索引），仅用于发现缺失的schema信息

## 工作流程（必须严格遵循）
1. 分析用户问题和已提供的Schema上下文
2. 生成一条回答用户完整需求的SQL语句
3. **【强制】调用 submit_final_sql 提交最终SQL** - 禁止跳过此步骤或只输出文本！
4. 如果 submit_final_sql 返回 ERROR：
   - 仔细分析错误信息（如列不存在、表名错误等）
   - 如果是列/表名错误，使用 search_objects 查找正确的名称
   - 修正完整SQL后，再次调用 submit_final_sql
5. 重复步骤4直到验证返回 SUCCESS
6. submit_final_sql 返回 SUCCESS 后立即结束，不要再次调用任何工具

## 重要规则
- **最终提交是唯一成功条件**：只有 submit_final_sql 返回 SUCCESS，任务才算完成
- 一次 submit_final_sql 只能提交一条完整SQL，禁止把多个数据库的局部探测SQL当作最终答案
- 多库问题必须提交一条完整的跨库SQL，不能分别提交多条单库SQL
- 禁止使用参数占位符如 %(name)s、%s、:name、? 等
- 如果多次尝试仍失败，保留错误信息并停止；禁止把未验证SQL当作最终答案
- **WHERE条件处理**:
  - 包含具体值（如"患者123"、"2024年1月"）→ 直接写入WHERE
  - 包含"全部"、"所有"、"不限制"、"历史"→ 不添加WHERE
  - "查询患者的XXX"但未指定ID → 不要自行添加示例值
  - 只有明确要求"某个/特定/指定"实体时才需WHERE
{db_specific_rules}
## 输出格式
验证通过后，输出最终SQL：
```sql
你的最终SQL语句
```
"""

# Legacy constant for backward compatibility
AGENT_SYSTEM_PROMPT = AGENT_SYSTEM_PROMPT_BASE.format(db_specific_rules="")


class SqlAgentNode(BaseNode):
    """SQL Agent Node using tool-calling for iterative SQL generation."""

    def __init__(self) -> None:
        self._settings = None

    @property
    def settings(self):
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def __call__(
        self,
        state: EasySQLState,
        config: RunnableConfig | None = None,
        *,
        writer: StreamWriter | None = None,
    ) -> dict[str, Any]:
        logger.info("[SqlAgent] START - Initializing SQL Agent node")

        scope = DatabaseScope.resolve(
            self.settings,
            db_names=state.get("db_names"),
            db_name=state.get("db_name"),
        )
        raw_query = state.get("raw_query", "")
        context = state.get("cached_context") or state.get("context_output")

        if not context:
            logger.error("[SqlAgent] No context available")
            return self._error_result("No context available for SQL generation")

        logger.debug(f"[SqlAgent] db_names={scope.names}, context_keys={list(context.keys())}")

        with _langfuse_span(
            "sql-agent-execution",
            input={"query": raw_query, "db_names": scope.names},
        ) as span:
            tools = get_agent_tools(db_names=scope.names)
            tools_dict = {t.name: t for t in tools}

            logger.info(f"[SqlAgent] Tools loaded: {list(tools_dict.keys())}")

            llm = get_llm(self.settings.llm, "generation")
            llm_with_tools = llm.bind_tools(tools)

            messages: list[BaseMessage | dict[str, Any]] = list(
                self._build_messages(state, context)
            )
            system_prompt = self._build_system_prompt(context, scope)

            max_iterations = self.settings.llm.agent_max_iterations
            timeout_seconds = float(getattr(self.settings.llm, "agent_timeout_seconds", 240))
            iteration = 0
            validation_passed = False
            final_sql: str | None = None
            last_candidate_sql: str | None = None
            last_error: str | None = None
            last_primary_db: str | None = state.get("primary_db")
            seen_tool_calls: set[str] = set()
            agent_started = perf_counter()
            deadline = agent_started + timeout_seconds

            try:
                while iteration < max_iterations:
                    remaining_seconds = deadline - perf_counter()
                    if remaining_seconds <= 0:
                        last_error = (
                            f"SQL Agent time budget exceeded after {timeout_seconds:g} seconds"
                        )
                        logger.warning(f"[SqlAgent] TIMEOUT - {last_error}")
                        break

                    iteration += 1
                    logger.info(f"[SqlAgent] Iteration {iteration}/{max_iterations}")

                    if writer:
                        writer(
                            {
                                "type": "agent_progress",
                                "iteration": iteration,
                                "action": "thinking",
                                "message": f"Generating SQL (iteration {iteration})",
                            }
                        )

                    full_messages = [{"role": "system", "content": system_prompt}] + messages
                    prompt_chars = sum(len(str(message)) for message in full_messages)
                    llm_started = perf_counter()
                    logger.info(
                        f"[SqlAgent] LLM START - iteration={iteration}, "
                        f"messages={len(full_messages)}, prompt_chars={prompt_chars}, "
                        f"remaining_seconds={remaining_seconds:.2f}"
                    )

                    try:
                        ai_response = await asyncio.wait_for(
                            self._stream_llm_response(
                                llm_with_tools,
                                full_messages,
                                writer,
                                iteration,
                                base_llm=llm,
                                tools=tools,
                            ),
                            timeout=remaining_seconds,
                        )
                    except asyncio.TimeoutError:
                        last_error = (
                            f"SQL Agent time budget exceeded after {timeout_seconds:g} seconds"
                        )
                        logger.warning(f"[SqlAgent] TIMEOUT - {last_error}")
                        break

                    logger.info(
                        f"[SqlAgent] LLM END - iteration={iteration}, "
                        f"elapsed_seconds={perf_counter() - llm_started:.3f}, "
                        f"tool_calls={len(ai_response.tool_calls)}, "
                        f"content_chars={len(self._normalize_message_content(ai_response.content))}"
                    )
                    replay_message = self._get_replay_message(ai_response)

                    if not ai_response.tool_calls:
                        content = ai_response.content
                        if isinstance(content, list):
                            content = "".join(
                                part if isinstance(part, str) else str(part.get("text", ""))
                                for part in content
                            )
                        sql = self.extract_sql(content or "")
                        if sql:
                            last_candidate_sql = sql
                            logger.warning(
                                "[SqlAgent] SQL returned without submit_final_sql; "
                                "forcing final validation"
                            )
                            validation_result = await self._force_validate(
                                sql,
                                tools_dict.get("submit_final_sql"),
                                writer,
                                iteration,
                                primary_db=last_primary_db or scope.default_primary,
                                timeout_seconds=max(0.001, deadline - perf_counter()),
                            )
                            if validation_result["success"]:
                                final_sql = sql
                                validation_passed = True
                                last_primary_db = validation_result.get("primary_db")
                                last_error = None
                                logger.info("[SqlAgent] SUCCESS - Final SQL validated")
                                break
                            last_error = validation_result["error"]
                            messages.append(replay_message)
                            messages.append(
                                HumanMessage(
                                    content=(
                                        f"最终SQL提交失败: {last_error}\n"
                                        "请修复完整SQL，并调用 submit_final_sql 再次提交。"
                                    )
                                )
                            )
                            continue
                        else:
                            last_error = (
                                "Model returned neither a tool call nor a SQL statement; "
                                "a validated final SQL was not submitted"
                            )
                            logger.warning(f"[SqlAgent] {last_error}")
                            break

                    messages.append(replay_message)
                    final_submission_succeeded = False
                    candidate_checked = False

                    for tool_call in ai_response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        tool_id = tool_call.get("id") or f"call_{iteration}_{tool_name}"

                        logger.info(f"[SqlAgent] Tool call: {tool_name}")
                        if writer:
                            writer(
                                {
                                    "type": "agent_progress",
                                    "iteration": iteration,
                                    "action": "tool_start",
                                    "tool": tool_name,
                                    "input_preview": self._truncate(str(tool_args), 200),
                                }
                            )

                        tool_signature = json.dumps(
                            {"name": tool_name, "args": tool_args},
                            ensure_ascii=False,
                            sort_keys=True,
                            default=str,
                        )
                        is_duplicate = tool_signature in seen_tool_calls
                        seen_tool_calls.add(tool_signature)

                        tool = tools_dict.get(tool_name)
                        resolved_primary: str | None = None
                        sql_to_validate: Any = None
                        if is_duplicate:
                            tool_result = (
                                "ERROR: Identical tool call already executed; revise the SQL "
                                "instead of repeating the same call"
                            )
                        elif not tool:
                            tool_result = f"ERROR: Unknown tool {tool_name}"
                        else:
                            try:
                                tool_remaining = deadline - perf_counter()
                                if tool_remaining <= 0:
                                    raise asyncio.TimeoutError

                                if tool_name in {"validate_sql", "submit_final_sql"}:
                                    primary_to_validate = (
                                        tool_args.get("primary_db")
                                        if isinstance(tool_args, dict)
                                        else None
                                    )
                                    sql_to_validate = (
                                        tool_args.get("sql", tool_args)
                                        if isinstance(tool_args, dict)
                                        else tool_args
                                    )
                                    if isinstance(sql_to_validate, dict):
                                        sql_to_validate = sql_to_validate.get("sql", "")
                                    tool_result = await asyncio.wait_for(
                                        tool.ainvoke(
                                            {
                                                "sql": sql_to_validate,
                                                "primary_db": primary_to_validate,
                                            }
                                        ),
                                        timeout=tool_remaining,
                                    )
                                    last_candidate_sql = str(sql_to_validate or "")
                                    try:
                                        if scope.is_federated and not primary_to_validate:
                                            raise ValueError("primary_db is required")
                                        resolved_primary = scope.require_primary(
                                            primary_to_validate
                                        ).name
                                    except ValueError:
                                        resolved_primary = None
                                else:
                                    tool_result = await asyncio.wait_for(
                                        tool.ainvoke(tool_args),
                                        timeout=tool_remaining,
                                    )
                            except asyncio.TimeoutError:
                                tool_result = (
                                    f"ERROR: SQL Agent time budget exceeded after "
                                    f"{timeout_seconds:g} seconds"
                                )
                            except Exception as e:
                                tool_result = f"ERROR: {e}"

                        if tool_name in {"validate_sql", "submit_final_sql"}:
                            is_success = self._is_tool_success(str(tool_result))
                        else:
                            is_success = not str(tool_result).lower().startswith("error")

                        if tool_name == "submit_final_sql":
                            if is_success and last_candidate_sql:
                                final_sql = last_candidate_sql
                                last_primary_db = resolved_primary
                                validation_passed = True
                                last_error = None
                                final_submission_succeeded = True
                            else:
                                validation_passed = False
                                last_error = str(tool_result)
                        elif tool_name == "validate_sql":
                            candidate_checked = True
                            last_error = None if is_success else str(tool_result)
                        elif not is_success:
                            last_error = str(tool_result)

                        logger.info(f"[SqlAgent] Tool result: success={is_success}")
                        if writer:
                            writer(
                                {
                                    "type": "agent_progress",
                                    "iteration": iteration,
                                    "action": "tool_end",
                                    "tool": tool_name,
                                    "success": is_success,
                                    "output_preview": self._truncate(str(tool_result), 300),
                                }
                            )

                        messages.append(
                            self._build_tool_result_message(
                                tool_result=tool_result,
                                tool_call_id=tool_id,
                                replay_message=replay_message,
                            )
                        )

                        if final_submission_succeeded:
                            logger.info(
                                "[SqlAgent] SUCCESS - submit_final_sql validated; "
                                "stopping without another LLM round"
                            )
                            break

                    if final_submission_succeeded:
                        break

                    if last_error:
                        logger.info("[SqlAgent] Final submission failed, adding repair instruction")
                        messages.append(
                            HumanMessage(
                                content=(
                                    f"SQL处理失败，错误信息: {last_error}\n\n"
                                    "请根据错误修正一条完整SQL，然后调用 submit_final_sql 提交。"
                                )
                            )
                        )
                    elif candidate_checked:
                        messages.append(
                            HumanMessage(
                                content=(
                                    "候选SQL检查已完成，但尚未提交最终答案。"
                                    "请生成回答完整用户需求的一条SQL，并调用 submit_final_sql。"
                                )
                            )
                        )

                elapsed_seconds = perf_counter() - agent_started
                logger.info(
                    f"[SqlAgent] Completed - iterations={iteration}, "
                    f"validated={validation_passed}, elapsed_seconds={elapsed_seconds:.3f}"
                )

                if span:
                    span.update(
                        output={
                            "sql": final_sql,
                            "last_candidate_sql": last_candidate_sql,
                            "primary_db": last_primary_db,
                            "success": validation_passed,
                            "iterations": iteration,
                            "elapsed_seconds": elapsed_seconds,
                            "error": last_error,
                        }
                    )

                if final_sql and validation_passed:
                    last_primary_db = scope.require_primary(last_primary_db).name
                    return {
                        "generated_sql": final_sql,
                        "primary_db": last_primary_db,
                        "validation_passed": True,
                        "validation_result": {
                            "valid": True,
                            "details": (
                                f"Completed in {iteration} iterations "
                                f"({elapsed_seconds:.3f} seconds)"
                            ),
                            "error": None,
                        },
                        "error": None,
                        "retry_count": iteration - 1,
                    }

                failure_error = last_error or (
                    f"SQL Agent exhausted {iteration} iteration(s) without a validated "
                    "final SQL submission"
                )
                return {
                    "generated_sql": None,
                    "primary_db": None,
                    "validation_passed": False,
                    "validation_result": {
                        "valid": False,
                        "details": (
                            f"Stopped after {iteration} iterations "
                            f"({elapsed_seconds:.3f} seconds)"
                        ),
                        "error": failure_error,
                        "last_candidate_sql": last_candidate_sql,
                    },
                    "error": failure_error,
                    "retry_count": max(0, iteration - 1),
                }

            except Exception as e:
                import traceback

                logger.error(f"[SqlAgent] FAILED: {type(e).__name__}: {e}")
                logger.debug(f"[SqlAgent] Traceback:\n{traceback.format_exc()}")
                if span:
                    span.update(output={"error": str(e)}, level="ERROR")
                return self._error_result(f"{type(e).__name__}: {e}")

    async def _stream_llm_response(
        self,
        llm: Any,
        messages: list,
        writer: StreamWriter | None,
        iteration: int,
        *,
        base_llm: Any | None = None,
        tools: list[Any] | None = None,
    ) -> AIMessage:
        """Stream LLM response and collect full message."""
        if (
            base_llm is not None
            and tools is not None
            and self._should_use_openai_reasoning_roundtrip(base_llm)
        ):
            return await self._stream_llm_response_openai(
                base_llm=base_llm,
                tools=tools,
                messages=messages,
                writer=writer,
                iteration=iteration,
            )
        content_parts: list[str] = []
        tool_calls: list[dict] = []
        tool_call_chunks: dict[int, dict[str, str]] = {}

        async for chunk in llm.astream(messages):
            if chunk.content:
                chunk_text = self._normalize_message_content(chunk.content)
                if chunk_text:
                    content_parts.append(chunk_text)
                if writer and chunk_text:
                    writer(
                        {
                            "type": "token",
                            "iteration": iteration,
                            "content": chunk_text,
                        }
                    )

            if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                for tc_chunk in chunk.tool_call_chunks:
                    idx = tc_chunk.get("index", 0)
                    if idx not in tool_call_chunks:
                        tool_call_chunks[idx] = {"name": "", "args": "", "id": ""}

                    if tc_chunk.get("name"):
                        tool_call_chunks[idx]["name"] = tc_chunk["name"]
                    if tc_chunk.get("id"):
                        tool_call_chunks[idx]["id"] = tc_chunk["id"]
                    if tc_chunk.get("args"):
                        tool_call_chunks[idx]["args"] += self._normalize_tool_args_chunk(
                            tc_chunk["args"]
                        )

        for idx in sorted(tool_call_chunks.keys()):
            tc = tool_call_chunks[idx]
            if tc["name"]:
                try:
                    args = json.loads(tc["args"]) if tc["args"] else {}
                except json.JSONDecodeError:
                    args = {"sql": tc["args"]} if tc["args"] else {}

                tool_calls.append(
                    {
                        "name": tc["name"],
                        "args": args,
                        "id": tc["id"] or f"call_{idx}",
                    }
                )

        full_content = "".join(content_parts)

        if content_parts and writer:
            writer(
                {
                    "type": "agent_progress",
                    "iteration": iteration,
                    "action": "thought_complete",
                    "content": full_content,
                }
            )

        return AIMessage(content=full_content, tool_calls=tool_calls)

    async def _stream_llm_response_openai(
        self,
        *,
        base_llm: Any,
        tools: list[Any],
        messages: list,
        writer: StreamWriter | None,
        iteration: int,
    ) -> AIMessage:
        """Use OpenAI-compatible streaming and preserve reasoning_content for replay."""
        async_client = getattr(base_llm, "async_client", None)
        if async_client is None:
            raise ValueError("OpenAI async_client is required for reasoning roundtrip")

        payload: dict[str, Any] = {
            "model": base_llm.model_name,
            "messages": self._serialize_messages_for_openai(messages),
            "tools": [convert_to_openai_tool(tool) for tool in tools],
            "tool_choice": "auto",
            "stream": True,
        }
        temperature = getattr(base_llm, "temperature", None)
        if temperature is not None:
            payload["temperature"] = temperature
        timeout = getattr(base_llm, "request_timeout", None)
        if timeout is not None:
            payload["timeout"] = timeout

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        openai_tool_calls: list[dict[str, Any]] = []
        tool_call_chunks: dict[int, dict[str, str]] = {}

        stream_result = async_client.create(**payload)
        if hasattr(stream_result, "__aiter__"):
            stream = stream_result
        else:
            stream = await stream_result

        async for chunk in stream:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue

            choice = choices[0]
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue

            chunk_content = self._get_field(delta, "content")
            if chunk_content:
                chunk_text = self._normalize_message_content(chunk_content)
                if chunk_text:
                    content_parts.append(chunk_text)
                    if writer:
                        writer(
                            {
                                "type": "token",
                                "iteration": iteration,
                                "content": chunk_text,
                            }
                        )

            chunk_reasoning = self._get_field(delta, "reasoning_content")
            if chunk_reasoning:
                reasoning_parts.append(str(chunk_reasoning))

            delta_tool_calls = self._get_field(delta, "tool_calls")
            if not delta_tool_calls:
                continue

            for tc_chunk in delta_tool_calls:
                idx_raw = self._get_field(tc_chunk, "index")
                idx = idx_raw if isinstance(idx_raw, int) else 0

                if idx not in tool_call_chunks:
                    tool_call_chunks[idx] = {"name": "", "args": "", "id": ""}

                tc_id = self._get_field(tc_chunk, "id")
                if tc_id:
                    tool_call_chunks[idx]["id"] = str(tc_id)

                function_chunk = self._get_field(tc_chunk, "function")
                if not function_chunk:
                    continue

                fn_name = self._get_field(function_chunk, "name")
                if fn_name:
                    tool_call_chunks[idx]["name"] = str(fn_name)

                fn_args = self._get_field(function_chunk, "arguments")
                if fn_args:
                    tool_call_chunks[idx]["args"] += str(fn_args)

        for idx in sorted(tool_call_chunks.keys()):
            tc = tool_call_chunks[idx]
            if not tc["name"]:
                continue

            call_id = tc["id"] or f"call_{idx}"
            args_text = tc["args"] if tc["args"] else "{}"
            try:
                parsed_args = json.loads(args_text) if args_text else {}
            except json.JSONDecodeError:
                parsed_args = {"sql": args_text} if args_text else {}

            tool_calls.append({"name": tc["name"], "args": parsed_args, "id": call_id})
            openai_tool_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": args_text},
                }
            )

        full_content = "".join(content_parts)
        reasoning_content = "".join(reasoning_parts)

        if content_parts and writer:
            writer(
                {
                    "type": "agent_progress",
                    "iteration": iteration,
                    "action": "thought_complete",
                    "content": full_content,
                }
            )

        replay_message: dict[str, Any] = {
            "role": "assistant",
            "content": full_content or None,
        }
        if reasoning_content:
            replay_message["reasoning_content"] = reasoning_content
        if openai_tool_calls:
            replay_message["tool_calls"] = openai_tool_calls

        additional_kwargs: dict[str, Any] = {"_replay_message": replay_message}
        if reasoning_content:
            additional_kwargs["reasoning_content"] = reasoning_content

        return AIMessage(
            content=full_content,
            tool_calls=tool_calls,
            additional_kwargs=additional_kwargs,
        )

    @staticmethod
    def _get_field(obj: Any, key: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    @staticmethod
    def _should_use_openai_reasoning_roundtrip(base_llm: Any) -> bool:
        """Enable raw OpenAI replay path for Kimi/thinking models."""
        async_client = getattr(base_llm, "async_client", None)
        if async_client is None:
            return False

        model_name = str(getattr(base_llm, "model_name", "")).lower()
        api_base = str(getattr(base_llm, "openai_api_base", "") or "").lower()

        return "kimi" in model_name or "thinking" in model_name or "moonshot" in api_base

    @staticmethod
    def _serialize_messages_for_openai(
        messages: list[BaseMessage | dict[str, Any] | Any],
    ) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message, dict):
                serialized.append(dict(message))
                continue
            if isinstance(message, BaseMessage):
                serialized.extend(convert_to_openai_messages([message]))
                continue
            raise TypeError(f"Unsupported message type: {type(message).__name__}")
        return serialized

    @staticmethod
    def _get_replay_message(ai_message: AIMessage) -> BaseMessage | dict[str, Any]:
        replay_message = ai_message.additional_kwargs.get("_replay_message")
        if isinstance(replay_message, dict):
            return replay_message
        return ai_message

    @staticmethod
    def _build_tool_result_message(
        *,
        tool_result: Any,
        tool_call_id: str,
        replay_message: BaseMessage | dict[str, Any],
    ) -> ToolMessage | dict[str, Any]:
        if isinstance(replay_message, dict):
            return {"role": "tool", "tool_call_id": tool_call_id, "content": str(tool_result)}
        return ToolMessage(content=str(tool_result), tool_call_id=tool_call_id)

    def _normalize_message_content(self, content: Any) -> str:
        """Normalize provider-specific message content into plain text."""
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            return "".join(self._normalize_message_content(part) for part in content)

        if isinstance(content, dict):
            text_fragments = []
            for key in ("text", "content", "output_text"):
                value = content.get(key)
                if value:
                    text_fragments.append(self._normalize_message_content(value))
            if text_fragments:
                return "".join(text_fragments)
            return ""

        return str(content)

    def _normalize_tool_args_chunk(self, args_chunk: Any) -> str:
        """Normalize tool-call argument chunks to JSON/string segments."""
        if isinstance(args_chunk, str):
            return args_chunk

        try:
            return json.dumps(args_chunk, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(args_chunk)

    async def _force_validate(
        self,
        sql: str,
        validate_tool: Any,
        writer: StreamWriter | None,
        iteration: int,
        primary_db: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Force final validation when the model returned bare SQL."""
        if not validate_tool:
            return {"success": False, "error": "No final submission tool available"}

        logger.info("[SqlAgent] Force validation - agent skipped submit_final_sql")
        if writer:
            writer(
                {
                    "type": "agent_progress",
                    "iteration": iteration,
                    "action": "force_validation",
                    "message": "Forcing SQL validation",
                }
            )

        try:
            invocation = validate_tool.ainvoke({"sql": sql, "primary_db": primary_db})
            result = (
                await asyncio.wait_for(invocation, timeout=timeout_seconds)
                if timeout_seconds is not None
                else await invocation
            )
            is_success = self._is_tool_success(str(result))
            return {
                "success": is_success,
                "error": None if is_success else str(result),
                "primary_db": primary_db,
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": "SQL Agent time budget exceeded"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _build_system_prompt(
        self,
        context: ContextOutputDict,
        scope: DatabaseScope,
    ) -> str:
        """Build system prompt with database-specific rules."""
        base_prompt = context.get("system_prompt", "")

        # Get database type and inject specific rules
        db_type = get_db_type_from_config(scope.default_primary)
        db_rules = get_db_specific_rules(db_type)

        if db_rules:
            agent_prompt = AGENT_SYSTEM_PROMPT_BASE.format(db_specific_rules=f"\n{db_rules}\n")
            logger.debug(f"[SqlAgent] Injected {db_type} specific rules into system prompt")
        else:
            agent_prompt = AGENT_SYSTEM_PROMPT

        routing_rule = (
            "多库模式：调用 submit_final_sql 时必须同时传 sql 和 primary_db；primary_db 必须由你根据用户问题从 "
            + ", ".join(scope.names)
            + " 中选择。最终 SQL 必须是一条完整跨库查询，执行主库就是提交时的 primary_db。"
            if scope.is_federated
            else (
                f"单库模式：调用 submit_final_sql 时 primary_db 固定为 "
                f"{scope.default_primary}。"
            )
        )
        return f"{base_prompt}\n\n{agent_prompt}\n\n## 主库选择\n{routing_rule}"

    def _build_messages(self, state: EasySQLState, context: ContextOutputDict) -> list[BaseMessage]:
        messages: list[BaseMessage] = []

        history = state.get("conversation_history") or []
        if history:
            token_manager = get_token_manager()
            schema_tokens = context.get("total_tokens", 0)
            summary, recent = token_manager.prepare_history(history, schema_tokens)
            history_messages = token_manager.build_history_messages(summary, recent)
            messages.extend(history_messages)

        current_query = state["raw_query"]
        user_prompt = context["user_prompt"]

        if history and "**用户问题**:" in user_prompt:
            parts = user_prompt.split("**用户问题**:")
            if len(parts) == 2:
                schema_part = parts[0]
                user_prompt = (
                    f"{schema_part}**用户问题**: {current_query}\n\n请生成正确的SQL查询语句："
                )

        messages.append(HumanMessage(content=user_prompt))
        return messages

    def _error_result(self, error: str) -> dict[str, Any]:
        return {
            "generated_sql": None,
            "validation_passed": False,
            "validation_result": {"valid": False, "details": None, "error": error},
            "error": error,
        }

    def _is_tool_success(self, output: str) -> bool:
        output_lower = output.lower()
        return (
            ("success" in output_lower and "error" not in output_lower)
            or '"success": true' in output_lower
            or '"success":true' in output_lower
        )

    def _truncate(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."


async def sql_agent_node(
    state: EasySQLState,
    config: RunnableConfig | None = None,
    *,
    writer: StreamWriter | None = None,
) -> dict[str, Any]:
    node = SqlAgentNode()
    return await node(state, config, writer=writer)
