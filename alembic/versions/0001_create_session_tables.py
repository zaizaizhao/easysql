"""create session tables

Revision ID: 0001_create_session_tables
Revises: 
Create Date: 2026-01-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_create_session_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "easysql_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("db_name", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("raw_query", sa.Text(), nullable=True),
        sa.Column("generated_sql", sa.Text(), nullable=True),
        sa.Column("validation_passed", sa.Boolean(), nullable=True),
        sa.Column("state", postgresql.JSONB(), nullable=True),
        sa.Column("turns", postgresql.JSONB(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
    )

    op.create_index(
        "idx_easysql_sessions_status",
        "easysql_sessions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_easysql_sessions_updated_at",
        "easysql_sessions",
        ["updated_at"],
        unique=False,
    )

    op.create_table(
        "easysql_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("easysql_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("easysql_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("generated_sql", sa.Text(), nullable=True),
        sa.Column("tables_used", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("validation_passed", sa.Boolean(), nullable=True),
        sa.Column("is_branch_point", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("checkpoint_id", sa.String(length=100), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("is_few_shot", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("user_answer", sa.Text(), nullable=True),
        sa.Column("clarification_questions", postgresql.JSONB(), nullable=True),
        sa.Column("thread_id", sa.Text(), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("root_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_easysql_messages_role"),
    )

    op.create_index(
        "idx_easysql_messages_session",
        "easysql_messages",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "idx_easysql_messages_parent",
        "easysql_messages",
        ["parent_id"],
        unique=False,
    )
    op.create_index(
        "idx_easysql_messages_thread",
        "easysql_messages",
        ["thread_id"],
        unique=False,
    )
    op.create_index(
        "idx_easysql_messages_root",
        "easysql_messages",
        ["root_message_id"],
        unique=False,
    )
    op.create_index(
        "idx_easysql_messages_few_shot",
        "easysql_messages",
        ["is_few_shot"],
        unique=False,
        postgresql_where=sa.text("is_few_shot = TRUE"),
    )

    op.create_table(
        "easysql_few_shot_meta",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("easysql_messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("db_name", sa.String(length=100), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("sql", sa.Text(), nullable=False),
        sa.Column("tables_used", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("milvus_id", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_index(
        "idx_easysql_few_shot_db",
        "easysql_few_shot_meta",
        ["db_name"],
        unique=False,
    )
    op.create_index(
        "idx_easysql_few_shot_milvus",
        "easysql_few_shot_meta",
        ["milvus_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_easysql_few_shot_milvus", table_name="easysql_few_shot_meta")
    op.drop_index("idx_easysql_few_shot_db", table_name="easysql_few_shot_meta")
    op.drop_table("easysql_few_shot_meta")

    op.drop_index("idx_easysql_messages_few_shot", table_name="easysql_messages")
    op.drop_index("idx_easysql_messages_root", table_name="easysql_messages")
    op.drop_index("idx_easysql_messages_thread", table_name="easysql_messages")
    op.drop_index("idx_easysql_messages_parent", table_name="easysql_messages")
    op.drop_index("idx_easysql_messages_session", table_name="easysql_messages")
    op.drop_table("easysql_messages")

    op.drop_index("idx_easysql_sessions_updated_at", table_name="easysql_sessions")
    op.drop_index("idx_easysql_sessions_status", table_name="easysql_sessions")
    op.drop_table("easysql_sessions")
