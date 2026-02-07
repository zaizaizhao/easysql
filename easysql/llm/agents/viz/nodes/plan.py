"""
LLM planning node for visualization intent with error correction retry.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, TYPE_CHECKING

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from easysql.config import LLMConfig, get_settings
from easysql.llm.agents.viz.prompts import (
    VIZ_SYSTEM_PROMPT,
    build_error_correction_prompt,
    build_viz_user_prompt,
)
from easysql.llm.agents.viz.schemas import VizPlan
from easysql.llm.agents.viz.state import VizState
from easysql.llm.models import get_llm
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter

logger = get_logger(__name__)

MAX_RETRIES = 2
LLM_TIMEOUT_SECONDS = 120


class VizPlanNode:
    def __init__(
        self,
        llm: BaseChatModel | None = None,
        config: LLMConfig | None = None,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self._llm = llm
        self._config = config
        self._max_retries = max_retries

    @property
    def config(self) -> LLMConfig:
        return self._config or get_settings().llm

    def _get_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = get_llm(self.config, purpose="planning")
        return self._llm

    def _pre_validate_plan(self, plan: VizPlan, columns: set[str]) -> list[str]:
        """Validate plan before passing to validate node. Returns list of errors."""
        errors: list[str] = []

        if not plan.charts:
            errors.append("No charts in plan")
            return errors

        for i, intent in enumerate(plan.charts):
            prefix = f"Chart {i + 1}"
            chart_type = str(intent.chart_type)

            if not intent.title:
                errors.append(f"{prefix}: title is required but empty")

            if chart_type in {
                "bar",
                "line",
                "area",
                "horizontal_bar",
                "grouped_bar",
                "stacked_bar",
                "stacked_area",
                "scatter",
            }:
                if not intent.x_axis_label:
                    errors.append(f"{prefix}: xAxisLabel is required for axis charts")
                if not intent.y_axis_label:
                    errors.append(f"{prefix}: yAxisLabel is required for axis charts")

            if intent.group_by and intent.group_by not in columns:
                errors.append(
                    f"{prefix}: groupBy '{intent.group_by}' not in columns {list(columns)}"
                )

            if intent.value_field and intent.value_field not in columns:
                errors.append(
                    f"{prefix}: valueField '{intent.value_field}' not in columns {list(columns)}"
                )

            if intent.series_field and intent.series_field not in columns:
                errors.append(
                    f"{prefix}: seriesField '{intent.series_field}' not in columns {list(columns)}"
                )

            if intent.top_n is not None and intent.top_n <= 0:
                errors.append(f"{prefix}: topN must be positive, got {intent.top_n}")

        return errors

    async def _invoke_llm(
        self,
        messages: list[BaseMessage],
        config: "RunnableConfig | None",
    ) -> VizPlan | str:
        """Invoke LLM and return VizPlan or error string."""
        structured_llm = self._get_llm().with_structured_output(VizPlan)

        try:
            result = await asyncio.wait_for(
                structured_llm.ainvoke(messages, config=config),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return f"TimeoutError: request timed out after {LLM_TIMEOUT_SECONDS}s"
        except ValidationError as exc:
            return f"ValidationError: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"{type(exc).__name__}: {exc}"

        if not isinstance(result, VizPlan):
            return "Invalid response structure: expected VizPlan"

        return result

    async def __call__(
        self,
        state: VizState,
        config: "RunnableConfig | None" = None,
        *,
        writer: "StreamWriter | None" = None,
    ) -> dict[str, Any]:
        profile = state.get("profile") or []
        sample_data = (state.get("sample_data") or [])[:10]
        previous_plan = state.get("previous_plan")
        columns = set(state.get("columns") or [])

        profile_json = json.dumps(profile, ensure_ascii=False)
        sample_json = json.dumps(sample_data, ensure_ascii=False)
        previous_plan_json = (
            json.dumps(previous_plan.model_dump(by_alias=True), ensure_ascii=False)
            if previous_plan
            else None
        )

        user_prompt = build_viz_user_prompt(
            question=state.get("question"),
            sql=state.get("sql"),
            profile_json=profile_json,
            sample_json=sample_json,
            row_count=state.get("row_count", 0),
            previous_plan_json=previous_plan_json,
        )

        messages: list[BaseMessage] = [
            SystemMessage(content=VIZ_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        last_error: str | None = None
        all_errors: list[str] = []

        for attempt in range(self._max_retries + 1):
            if attempt > 0 and last_error:
                logger.info(f"Viz plan retry {attempt}/{self._max_retries}: {last_error}")
                correction_prompt = build_error_correction_prompt(last_error)
                messages.append(AIMessage(content="(previous attempt failed)"))
                messages.append(HumanMessage(content=correction_prompt))

            result = await self._invoke_llm(messages, config)

            if isinstance(result, str):
                last_error = result
                all_errors.append(f"Attempt {attempt + 1}: {result}")
                continue

            validation_errors = self._pre_validate_plan(result, columns)
            if validation_errors:
                last_error = "; ".join(validation_errors)
                all_errors.append(f"Attempt {attempt + 1} validation: {last_error}")
                continue

            return {"plan": result}

        logger.warning(f"Viz plan failed after {self._max_retries + 1} attempts: {all_errors}")
        return {
            "plan": None,
            "errors": [f"Viz plan failed after {self._max_retries + 1} attempts"] + all_errors,
        }


async def plan_viz_node(
    state: VizState,
    config: "RunnableConfig | None" = None,
    *,
    writer: "StreamWriter | None" = None,
) -> dict[str, Any]:
    node = VizPlanNode()
    return await node(state, config, writer=writer)
