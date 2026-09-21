"""PostgreSQL wiki records; ADK manages its own session tables on the same engine."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from easysql_api.infrastructure.persistence.models import Base


class WikiDocumentModel(Base):
    __tablename__ = "easysql_wiki_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    db_names: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    index_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    index_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("namespace", "source_key", name="uq_wiki_source"),)


class WikiPageModel(Base):
    __tablename__ = "easysql_wiki_pages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("easysql_wiki_documents.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    domain: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    db_names: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_wiki_document_revision", "document_id", "revision"),)


class WikiRevisionModel(Base):
    __tablename__ = "easysql_wiki_revisions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("easysql_wiki_documents.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    pages: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentLeaseModel(Base):
    __tablename__ = "easysql_agent_leases"

    resource: Mapped[str] = mapped_column(String(255), primary_key=True)
    token: Mapped[str] = mapped_column(String(36), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
