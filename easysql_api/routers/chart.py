"""
Chart recommendation router.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from easysql_api.deps import get_chart_service_dep
from easysql_api.models.chart import ChartRecommendRequest, ChartRecommendResponse
from easysql_api.services.chart_service import ChartService

router = APIRouter()


@router.post("/chart/recommend", response_model=ChartRecommendResponse)
async def recommend_chart(
    request: ChartRecommendRequest,
    service: Annotated[ChartService, Depends(get_chart_service_dep)],
) -> ChartRecommendResponse:
    return await service.recommend(request)
