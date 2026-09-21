"""Markdown upload, source management and progressive Wiki browsing endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import PurePath
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from easysql.config import get_settings
from easysql_agentic.dependencies import get_wiki_ingestion_service, get_wiki_service
from easysql_agentic.knowledge.repository import ResourceBusyError
from easysql_agentic.knowledge.service import MAX_MARKDOWN_BYTES, WikiService

router = APIRouter(prefix="/knowledge")
WikiDependency = Annotated[WikiService, Depends(get_wiki_service)]


def selected_databases(db_names: list[str] | None) -> list[str]:
    configured = get_settings().databases
    names = list(
        dict.fromkeys(name.lower() for name in (configured if db_names is None else db_names))
    )
    if not names or any(name not in configured for name in names):
        raise HTTPException(422, "Select configured database aliases")
    return names


@router.post("/documents")
async def upload_markdown(
    service: WikiDependency,
    file: Annotated[UploadFile, File()],
    db_names: Annotated[str, Form()],
    source_key: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    filename = file.filename or ""
    if not filename.lower().endswith((".md", ".markdown")):
        raise HTTPException(422, "Upload a .md or .markdown file")
    content = await file.read(MAX_MARKDOWN_BYTES + 1)
    if len(content) > MAX_MARKDOWN_BYTES:
        raise HTTPException(413, "Markdown must be at most 512 KiB")
    try:
        names = json.loads(db_names)
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
            raise ValueError("db_names must be a JSON array of database aliases")
        names = selected_databases(names)
        markdown = content.decode("utf-8-sig")
        # Keep read endpoints usable before a model key is configured.
        if service.organizer is None:
            service.organizer = get_wiki_ingestion_service().organizer
        settings = get_settings()
        result = await service.ingest(
            source_key=source_key or PurePath(filename).name,
            markdown=markdown,
            db_schemas={name: settings.databases[name].get_default_schema() for name in names},
            timeout_seconds=settings.llm.query_timeout_seconds,
        )
        result.pop("markdown", None)
        return result
    except ResourceBusyError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            504, "Organization timed out; the published version is unchanged"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            502, f"Knowledge organization failed ({type(exc).__name__}); retry safely"
        ) from exc


@router.get("/documents")
async def list_documents(service: WikiDependency) -> dict[str, Any]:
    return {"documents": await service.repository.list_documents()}


@router.get("/documents/{document_id}/revisions")
async def document_revisions(document_id: str, service: WikiDependency) -> dict[str, Any]:
    return {"revisions": await service.repository.revisions(document_id)}


@router.post("/documents/{document_id}/reindex")
async def reindex_document(document_id: str, service: WikiDependency) -> dict[str, Any]:
    document = next(
        (doc for doc in await service.repository.list_documents() if doc["id"] == document_id), None
    )
    if document is None:
        raise HTTPException(404, "Document not found")
    try:
        return await service.retry_index(document["source_key"])
    except ResourceBusyError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, service: WikiDependency) -> dict[str, Any]:
    documents = await service.repository.list_documents()
    document = next((doc for doc in documents if doc["id"] == document_id), None)
    if document is None:
        raise HTTPException(404, "Document not found")
    import hashlib

    try:
        async with service.repository.lease(
            "wiki:" + hashlib.sha256(document["source_key"].encode()).hexdigest()
        ):
            await service.repository.delete_document(document_id)
            cleanup_pending = False
            if service.index is not None:
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(service.index.delete, document_id), timeout=30
                    )
                except Exception:
                    cleanup_pending = True
            return {"deleted": True, "index_cleanup_pending": cleanup_pending}
    except ResourceBusyError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/wiki")
async def wiki_outline(
    service: WikiDependency,
    domain: str = "",
    db_names: Annotated[list[str] | None, Query()] = None,
) -> dict[str, Any]:
    return await service.outline(selected_databases(db_names), domain)


@router.get("/pages")
async def wiki_pages(
    service: WikiDependency,
    domain: str = "",
    offset: int = Query(default=0, ge=0),
    db_names: Annotated[list[str] | None, Query()] = None,
) -> dict[str, Any]:
    return await service.list_pages(selected_databases(db_names), domain, offset)


@router.get("/pages/{page_id}")
async def read_wiki_page(
    page_id: str,
    service: WikiDependency,
    offset: int = Query(default=0, ge=0),
    db_names: Annotated[list[str] | None, Query()] = None,
) -> dict[str, Any]:
    try:
        return await service.read(page_id, selected_databases(db_names), offset)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/search")
async def search_wiki(
    service: WikiDependency,
    q: str = Query(min_length=1, max_length=1000),
    db_names: Annotated[list[str] | None, Query()] = None,
) -> dict[str, Any]:
    return await service.search(q, selected_databases(db_names))
