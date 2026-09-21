"""Transactional source replacement and scoped wiki reads on the existing control plane."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from easysql_agentic.knowledge.models import WikiPage, WikiPageDraft
from easysql_agentic.knowledge.tables import (
    AgentLeaseModel,
    WikiDocumentModel,
    WikiPageModel,
    WikiRevisionModel,
)
from easysql_api.infrastructure.db_manager import ControlPlaneSessionProvider


class ResourceBusyError(ValueError):
    """The same session or document is already being changed by another request."""


class WikiRepository:
    def __init__(self, provider: ControlPlaneSessionProvider, namespace: str) -> None:
        self.provider = provider
        self.namespace = namespace

    @asynccontextmanager
    async def lease(self, resource: str, seconds: int = 360) -> AsyncIterator[None]:
        resource = f"{self.namespace}:{resource}"
        token = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        async with self.provider.session() as db:
            statement = insert(AgentLeaseModel).values(
                resource=resource, token=token, expires_at=now + timedelta(seconds=seconds)
            )
            statement = statement.on_conflict_do_update(
                index_elements=[AgentLeaseModel.resource],
                set_={"token": token, "expires_at": statement.excluded.expires_at},
                where=AgentLeaseModel.expires_at < func.now(),
            ).returning(AgentLeaseModel.token)
            if (await db.execute(statement)).scalar_one_or_none() != token:
                raise ResourceBusyError("This session or source is already being processed")
        try:
            yield
        finally:
            async with self.provider.session() as db:
                await db.execute(
                    delete(AgentLeaseModel).where(
                        AgentLeaseModel.resource == resource, AgentLeaseModel.token == token
                    )
                )

    async def get_document(self, source_key: str) -> dict[str, Any] | None:
        async with self.provider.session() as db:
            model = (
                await db.execute(
                    select(WikiDocumentModel).where(
                        WikiDocumentModel.namespace == self.namespace,
                        WikiDocumentModel.source_key == source_key,
                    )
                )
            ).scalar_one_or_none()
            return self._document(model, include_source=True) if model else None

    async def list_documents(self) -> list[dict[str, Any]]:
        async with self.provider.session() as db:
            models = (
                (
                    await db.execute(
                        select(WikiDocumentModel)
                        .where(WikiDocumentModel.namespace == self.namespace)
                        .order_by(WikiDocumentModel.updated_at.desc())
                        .limit(1000)
                    )
                )
                .scalars()
                .all()
            )
            return [self._document(model) for model in models]

    @staticmethod
    def _document(model: WikiDocumentModel, include_source: bool = False) -> dict[str, Any]:
        result = {
            "id": str(model.id),
            "source_key": model.source_key,
            "revision": model.revision,
            "content_hash": model.content_hash,
            "db_names": model.db_names,
            "index_status": model.index_status,
            "index_error": model.index_error,
            "updated_at": model.updated_at.isoformat(),
        }
        if include_source:
            result["markdown"] = model.markdown
        return result

    async def publish(
        self,
        *,
        source_key: str,
        markdown: str,
        content_hash: str,
        db_names: list[str],
        drafts: list[WikiPageDraft],
        expected_revision: int,
    ) -> dict[str, Any]:
        # Re-creating a deleted source starts a new identity; stale index jobs
        # must not collide with a new document's revision 1.
        document_id = uuid.uuid4()
        async with self.provider.session() as db:
            await db.execute(
                insert(WikiDocumentModel)
                .values(
                    id=document_id,
                    namespace=self.namespace,
                    source_key=source_key,
                    revision=0,
                    content_hash="",
                    markdown="",
                    db_names=db_names,
                    index_status="pending",
                )
                .on_conflict_do_nothing()
            )
            document = (
                await db.execute(
                    select(WikiDocumentModel)
                    .where(
                        WikiDocumentModel.namespace == self.namespace,
                        WikiDocumentModel.source_key == source_key,
                    )
                    .with_for_update()
                )
            ).scalar_one()
            document_id = document.id
            if document.content_hash == content_hash:
                return {**self._document(document), "unchanged": True}
            if document.revision != expected_revision:
                raise ResourceBusyError("Source changed while being organized; retry the upload")

            revision = document.revision + 1
            pages = []
            for draft in drafts:
                used_databases = sorted({item.split(".", 1)[0] for item in draft.table_ids})
                page = WikiPage(
                    **draft.model_dump(),
                    id=str(uuid.uuid5(document_id, draft.key)),
                    document_id=str(document_id),
                    revision=revision,
                    source_key=source_key,
                    source_line=markdown[: markdown.index(draft.source_quote)].count("\n") + 1,
                    db_names=used_databases or db_names,
                )
                pages.append(page)

            await db.execute(delete(WikiPageModel).where(WikiPageModel.document_id == document_id))
            for page in pages:
                db.add(
                    WikiPageModel(
                        id=uuid.UUID(page.id),
                        document_id=document_id,
                        revision=revision,
                        domain=page.domain,
                        kind=page.kind,
                        db_names=page.db_names,
                        payload=page.model_dump(mode="json"),
                        search_text="\n".join(
                            [
                                page.title,
                                page.summary,
                                page.domain,
                                " ".join(page.table_ids),
                                page.body_md,
                            ]
                        ),
                    )
                )
            db.add(
                WikiRevisionModel(
                    document_id=document_id,
                    revision=revision,
                    content_hash=content_hash,
                    markdown=markdown,
                    pages=[page.model_dump(mode="json") for page in pages],
                )
            )
            document.revision = revision
            document.content_hash = content_hash
            document.markdown = markdown
            document.db_names = db_names
            document.index_status = "pending"
            document.index_error = None
            document.updated_at = datetime.now(timezone.utc)
            await db.flush()
            return {**self._document(document), "unchanged": False, "page_count": len(pages)}

    def _pages_query(self, db_names: list[str] | None = None) -> Any:
        statement = (
            select(WikiPageModel)
            .join(WikiDocumentModel)
            .where(
                WikiDocumentModel.namespace == self.namespace,
                WikiPageModel.revision == WikiDocumentModel.revision,
            )
        )
        if db_names is not None:
            statement = statement.where(WikiPageModel.db_names.contained_by(db_names))
        return statement

    async def pages(
        self,
        *,
        db_names: list[str] | None = None,
        domain: str | None = None,
        ids: list[str] | None = None,
        document_id: str | None = None,
        kind: str | None = None,
        terms: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WikiPage]:
        statement = self._pages_query(db_names)
        if domain:
            statement = statement.where(
                or_(
                    WikiPageModel.domain == domain,
                    WikiPageModel.domain.startswith(domain + "/", autoescape=True),
                )
            )
        if ids is not None:
            statement = statement.where(WikiPageModel.id.in_([uuid.UUID(item) for item in ids]))
        if document_id:
            statement = statement.where(WikiPageModel.document_id == uuid.UUID(document_id))
        if kind:
            statement = statement.where(WikiPageModel.kind == kind)
        if terms:
            statement = statement.where(
                or_(
                    *[
                        WikiPageModel.search_text.icontains(term, autoescape=True)
                        for term in terms[:24]
                    ]
                )
            )
        async with self.provider.session() as db:
            models = (
                (
                    await db.execute(
                        statement.order_by(WikiPageModel.domain, WikiPageModel.id)
                        .limit(min(limit, 5000))
                        .offset(offset)
                    )
                )
                .scalars()
                .all()
            )
            return [WikiPage.model_validate(model.payload) for model in models]

    async def domains(self, db_names: list[str]) -> list[dict[str, Any]]:
        statement = (
            self._pages_query(db_names)
            .with_only_columns(WikiPageModel.domain, func.count().label("page_count"))
            .group_by(WikiPageModel.domain)
            .order_by(WikiPageModel.domain)
        )
        async with self.provider.session() as db:
            return [dict(row._mapping) for row in await db.execute(statement)]

    async def mark_index(
        self,
        document_id: str,
        revision: int,
        status: str,
        error: str | None = None,
    ) -> None:
        async with self.provider.session() as db:
            await db.execute(
                update(WikiDocumentModel)
                .where(
                    WikiDocumentModel.id == uuid.UUID(document_id),
                    WikiDocumentModel.namespace == self.namespace,
                    WikiDocumentModel.revision == revision,
                )
                .values(index_status=status, index_error=error)
            )

    async def revisions(self, document_id: str) -> list[dict[str, Any]]:
        async with self.provider.session() as db:
            result = await db.execute(
                select(
                    WikiRevisionModel.revision,
                    WikiRevisionModel.content_hash,
                    WikiRevisionModel.created_at,
                )
                .join(WikiDocumentModel)
                .where(
                    WikiDocumentModel.id == uuid.UUID(document_id),
                    WikiDocumentModel.namespace == self.namespace,
                )
                .order_by(WikiRevisionModel.revision.desc())
            )
            return [dict(row._mapping) for row in result]

    async def delete_document(self, document_id: str) -> bool:
        async with self.provider.session() as db:
            result = await db.execute(
                delete(WikiDocumentModel).where(
                    WikiDocumentModel.id == uuid.UUID(document_id),
                    WikiDocumentModel.namespace == self.namespace,
                )
            )
            return bool(result.rowcount)
