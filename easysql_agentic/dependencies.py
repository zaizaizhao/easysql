"""Small factories reusing existing settings, connection pools and persistence."""

from __future__ import annotations

from easysql.config import get_settings
from easysql_agentic.knowledge.index import WikiIndex
from easysql_agentic.knowledge.organizer import MarkdownOrganizer
from easysql_agentic.knowledge.repository import WikiRepository
from easysql_agentic.knowledge.service import WikiService
from easysql_agentic.models import create_model
from easysql_api.infrastructure.db_manager import get_control_plane_db_manager


def get_wiki_service() -> WikiService:
    settings = get_settings()
    return WikiService(
        WikiRepository(get_control_plane_db_manager(), settings.project_namespace),
        index=WikiIndex(),
    )


def get_wiki_ingestion_service() -> WikiService:
    service = get_wiki_service()
    service.organizer = MarkdownOrganizer(create_model(get_settings().llm))
    return service
