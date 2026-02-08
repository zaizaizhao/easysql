"""
SQL Agent Node.

Uses LLM with tool-calling for iterative SQL generation and validation.
SQL is validated inside the agent loop before returning to frontend.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.types import StreamWriter

from easysql.config import get_settings
from easysql.context.db_specific_rules import get_db_specific_rules, get_db_type_from_config
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
1. validate_sql - 验证SQL语句是否正确（执行 LIMIT 1 检查语法和可执行性）
2. search_objects - 搜索数据库对象（表、列、索引），用于发现缺失的schema信息

## 工作流程（必须严格遵循）
1. 分析用户问题和已提供的Schema上下文
2. 生成SQL语句
3. **【强制】调用 validate_sql 工具验证SQL** - 禁止跳过此步骤！
4. 如果验证返回 ERROR：
   - 仔细分析错误信息（如列不存在、表名错误等）
   - 如果是列/表名错误，使用 search_objects 查找正确的名称
   - 修正SQL后，**必须再次调用 validate_sql 验证**
5. 重复步骤4直到验证返回 SUCCESS
6. 只有在 validate_sql 返回 SUCCESS 后，才能输出最终SQL

## 重要规则
- **禁止跳过验证**：必须至少调用一次 validate_sql 且返回 SUCCESS 才能输出最终SQL
- 禁止使用参数占位符如 %(name)s、%s、:name、? 等
- 如果多次尝试失败（超过3次），说明遇到的问题并返回最后尝试的SQL
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
        config: "RunnableConfig | None" = None,
        *,
        writer: "StreamWriter | None" = None,
    ) -> dict[str, Any]:
        logger.info("[SqlAgent] START - Initializing SQL Agent node")

        db_name = state.get("db_name") or "default"
        raw_query = state.get("raw_query", "")
        context = state.get("cached_context") or state.get("context_output")

        if not context:
            logger.error("[SqlAgent] No context available")
            return self._error_result("No context available for SQL generation")

        logger.debug(f"[SqlAgent] db_name={db_name}, context_keys={list(context.keys())}")

        with _langfuse_span(
            "sql-agent-execution",
            input={"query": raw_query, "db_name": db_name},
        ) as span:
            tools = get_agent_tools(db_name=db_name)
            tools_dict = {t.name: t for t in tools}

            logger.info(f"[SqlAgent] Tools loaded: {list(tools_dict.keys())}")

            llm = get_llm(self.settings.llm, "generation")
            llm_with_tools = llm.bind_tools(tools)

            messages = self._build_messages(state, context)
            system_prompt = self._build_system_prompt(context, db_name)

            max_iterations = self.settings.llm.agent_max_iterations
            iteration = 0
            validation_passed = False
            last_sql: str | None = None
            last_error: str | None = None

            try:
                while iteration < max_iterations:
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

                    ai_response = await self._stream_llm_response(
                        llm_with_tools, full_messages, writer, iteration
                    )

                    if not ai_response.tool_calls:
                        content = ai_response.content
                        if isinstance(content, list):
                            content = "".join(
                                part if isinstance(part, str) else str(part.get("text", ""))
                                for part in content
                            )
                        sql = self.extract_sql(content or "")
                        if sql:
                            last_sql = sql
                            if validation_passed:
                                logger.info("[SqlAgent] SUCCESS - Validated SQL returned")
                                break
                            else:
                                logger.warning("[SqlAgent] SQL returned without validation")
                                validation_result = await self._force_validate(
                                    sql, tools_dict.get("validate_sql"), writer, iteration
                                )
                                if validation_result["success"]:
                                    validation_passed = True
                                    break
                                else:
                                    last_error = validation_result["error"]
                                    messages.append(ai_response)
                                    messages.append(
                                        HumanMessage(
                                            content=f"验证失败: {last_error}\n请修复SQL并再次验证。"
                                        )
                                    )
                                    continue
                        else:
                            logger.warning("[SqlAgent] No SQL or tool calls in response")
                            break

                    messages.append(ai_response)

                    for tool_call in ai_response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        tool_id = tool_call["id"]

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

                        tool = tools_dict.get(tool_name)
                        if not tool:
                            tool_result = f"ERROR: Unknown tool {tool_name}"
                        else:
                            try:
                                if tool_name == "validate_sql":
                                    sql_to_validate = tool_args.get("sql", tool_args)
                                    if isinstance(sql_to_validate, dict):
                                        sql_to_validate = sql_to_validate.get("sql", "")
                                    tool_result = await tool.ainvoke(sql_to_validate)
                                    last_sql = sql_to_validate
                                else:
                                    tool_result = await tool.ainvoke(tool_args)
                            except Exception as e:
                                tool_result = f"ERROR: {e}"

                        is_success = self._is_tool_success(str(tool_result))
                        if tool_name == "validate_sql":
                            validation_passed = is_success
                            if not is_success:
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

                        messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))

                    # If validation failed during tool calls, add explicit retry instruction
                    if not validation_passed and last_error:
                        logger.info(f"[SqlAgent] Validation failed, adding retry instruction")
                        messages.append(
                            HumanMessage(
                                content=f"SQL验证失败，错误信息: {last_error}\n\n请根据错误信息修正SQL语句，然后再次调用 validate_sql 工具验证。"
                            )
                        )

                logger.info(
                    f"[SqlAgent] Completed - iterations={iteration}, validated={validation_passed}"
                )

                if span:
                    span.update(
                        output={
                            "sql": last_sql,
                            "success": validation_passed,
                            "iterations": iteration,
                        }
                    )

                if last_sql:
                    return {
                        "generated_sql": last_sql,
                        "validation_passed": validation_passed,
                        "validation_result": {
                            "valid": validation_passed,
                            "details": f"Completed in {iteration} iterations",
                            "error": None if validation_passed else last_error,
                        },
                        "error": None if validation_passed else last_error,
                        "retry_count": iteration - 1,
                    }
                else:
                    return self._error_result("Failed to generate SQL")

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
        writer: "StreamWriter | None",
        iteration: int,
    ) -> AIMessage:
        """Stream LLM response and collect full message."""
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
        writer: "StreamWriter | None",
        iteration: int,
    ) -> dict[str, Any]:
        """Force validation when agent skipped it."""
        if not validate_tool:
            return {"success": False, "error": "No validation tool available"}

        logger.info("[SqlAgent] Force validation - agent skipped validate_sql")
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
            result = await validate_tool.ainvoke(sql)
            is_success = self._is_tool_success(str(result))
            return {"success": is_success, "error": None if is_success else str(result)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _build_system_prompt(self, context: ContextOutputDict, db_name: str | None = None) -> str:
        """Build system prompt with database-specific rules."""
        base_prompt = context.get("system_prompt", "")

        # Get database type and inject specific rules
        db_type = get_db_type_from_config(db_name)
        db_rules = get_db_specific_rules(db_type)

        if db_rules:
            agent_prompt = AGENT_SYSTEM_PROMPT_BASE.format(db_specific_rules=f"\n{db_rules}\n")
            logger.debug(f"[SqlAgent] Injected {db_type} specific rules into system prompt")
        else:
            agent_prompt = AGENT_SYSTEM_PROMPT

        return f"{base_prompt}\n\n{agent_prompt}"

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
    config: "RunnableConfig | None" = None,
    *,
    writer: "StreamWriter | None" = None,
) -> dict[str, Any]:
    node = SqlAgentNode()
    return await node(state, config, writer=writer)
