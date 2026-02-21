"""
Chart recommendation router.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from easysql.llm.agents.viz.schemas import VizPlan
from easysql.utils.logger import get_logger
from easysql_api.deps import get_chart_service_dep, get_session_repository_dep
from easysql_api.domain.repositories.session_repository import SessionRepository
from easysql_api.models.chart import ChartRecommendRequest, ChartRecommendResponse
from easysql_api.services.chart_service import ChartService

router = APIRouter()
logger = get_logger(__name__)


def _resolve_turn(session, request: ChartRecommendRequest):
    turn = session.get_turn(request.turn_id) if request.turn_id else None
    if not turn and request.sql:
        for candidate in reversed(session.turns):
            if candidate.final_sql == request.sql:
                turn = candidate
                break
    if not turn and session.turns:
        turn = session.turns[-1]
    return turn


@router.post("/chart/recommend", response_model=ChartRecommendResponse)
async def recommend_chart(
    request: ChartRecommendRequest,
    service: Annotated[ChartService, Depends(get_chart_service_dep)],
    repository: Annotated[SessionRepository, Depends(get_session_repository_dep)],
) -> ChartRecommendResponse:
    session = None
    turn = None
    if request.plan_only and request.session_id:
        session = await repository.get(request.session_id)
        if session:
            turn = _resolve_turn(session, request)
            if turn and turn.chart_plan:
                plan_data = turn.chart_plan
                if isinstance(plan_data, dict):
                    try:
                        plan = VizPlan.model_validate(plan_data)
                    except ValidationError:
                        plan = None

                    if plan is not None:
                        suitable = bool(plan.suitable and plan.charts)
                        reasoning = turn.chart_reasoning or plan.reasoning
                        return ChartRecommendResponse(
                            suitable=suitable,
                            config=None,
                            chartData=None,
                            reasoning=reasoning,
                            intent=None,
                            plan=plan,
                            error=None if suitable else "No suitable chart suggestions",
                        )

    response = await service.recommend(request)

    if request.plan_only and request.session_id and response.plan:
        try:
            if session is None:
                session = await repository.get(request.session_id)
            if session:
                if turn is None:
                    turn = _resolve_turn(session, request)
                if turn:
                    turn.chart_plan = response.plan.model_dump(by_alias=True)
                    turn.chart_reasoning = response.reasoning
                    await repository.save_turns(session.session_id, session.turns)
        except Exception as exc:
            logger.warning("Failed to persist chart plan: %s", exc)

    return response
