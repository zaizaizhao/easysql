"""
API Routers.
"""

from easysql_api.routers.config import router as config_router
from easysql_api.routers.execute import router as execute_router
from easysql_api.routers.health import router as health_router
from easysql_api.routers.pipeline import router as pipeline_router
from easysql_api.routers.query import router as query_router
from easysql_api.routers.sessions import router as sessions_router

__all__ = [
    "query_router",
    "sessions_router",
    "pipeline_router",
    "config_router",
    "health_router",
    "execute_router",
]
