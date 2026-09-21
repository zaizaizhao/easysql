"""Add versioned Markdown wiki and short-lived agent invocation leases.

Revision ID: 0005_agentic_wiki
Revises: 0004_multi_db_sessions

ADK's DatabaseSessionService creates and manages its own framework tables.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0005_agentic_wiki"
down_revision = "0004_multi_db_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "easysql_wiki_documents",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("namespace", sa.String(128), nullable=False),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("db_names", pg.ARRAY(sa.Text()), nullable=False),
        sa.Column("index_status", sa.String(20), nullable=False),
        sa.Column("index_error", sa.Text()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("namespace", "source_key", name="uq_wiki_source"),
    )
    op.create_table(
        "easysql_wiki_pages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("easysql_wiki_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("db_names", pg.ARRAY(sa.Text()), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
    )
    op.create_index("ix_wiki_document_revision", "easysql_wiki_pages", ["document_id", "revision"])
    op.create_table(
        "easysql_wiki_revisions",
        sa.Column(
            "document_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("easysql_wiki_documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("pages", pg.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "easysql_agent_leases",
        sa.Column("resource", sa.String(255), primary_key=True),
        sa.Column("token", sa.String(36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("easysql_agent_leases")
    op.drop_table("easysql_wiki_revisions")
    op.drop_table("easysql_wiki_pages")
    op.drop_table("easysql_wiki_documents")
