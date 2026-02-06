"""
Chart recommendation router.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from easysql.utils.logger import get_logger
from easysql_api.deps import get_chart_service_dep, get_session_repository_dep
from easysql_api.domain.repositories.session_repository import SessionRepository
from easysql_api.models.chart import ChartRecommendRequest, ChartRecommendResponse
from easysql_api.services.chart_service import ChartService

router = APIRouter()
logger = get_logger(__name__)


@router.post("/chart/recommend", response_model=ChartRecommendResponse)
async def recommend_chart(
    request: ChartRecommendRequest,
    service: Annotated[ChartService, Depends(get_chart_service_dep)],
    repository: Annotated[SessionRepository, Depends(get_session_repository_dep)],
) -> ChartRecommendResponse:
    response = await service.recommend(request)

    if request.plan_only and request.session_id and response.plan:
        try:
            session = await repository.get(request.session_id)
            if session:
                turn = session.get_turn(request.turn_id) if request.turn_id else None
                if not turn and request.sql:
                    for candidate in reversed(session.turns):
                        if candidate.final_sql == request.sql:
                            turn = candidate
                            break
                if not turn and session.turns:
                    turn = session.turns[-1]
                if turn:
                    turn.chart_plan = response.plan.model_dump(by_alias=True)
                    turn.chart_reasoning = response.reasoning
                    await repository.save_turns(session.session_id, session.turns)
        except Exception as exc:
            logger.warning("Failed to persist chart plan: %s", exc)

    return response
