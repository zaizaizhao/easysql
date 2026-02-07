"""split turns into table

Revision ID: 0002_split_turns_table
Revises: 0001_create_session_tables
Create Date: 2026-02-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_split_turns_table"
down_revision = "0001_create_session_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "easysql_turns",
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
        sa.Column("turn_id", sa.String(length=20), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("final_sql", sa.Text(), nullable=True),
        sa.Column("validation_passed", sa.Boolean(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("chart_plan", postgresql.JSONB(), nullable=True),
        sa.Column("chart_reasoning", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("session_id", "turn_id", name="uq_easysql_turns_session_turn_id"),
    )

    op.create_index(
        "idx_easysql_turns_session",
        "easysql_turns",
        ["session_id"],
        unique=False,
    )

    op.create_table(
        "easysql_turn_clarifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "turn_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("easysql_turns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("questions", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "idx_easysql_turn_clarifications_turn",
        "easysql_turn_clarifications",
        ["turn_id"],
        unique=False,
    )

    op.drop_column("easysql_sessions", "turns")


def downgrade() -> None:
    op.add_column("easysql_sessions", sa.Column("turns", postgresql.JSONB(), nullable=True))

    op.drop_index("idx_easysql_turn_clarifications_turn", table_name="easysql_turn_clarifications")
    op.drop_table("easysql_turn_clarifications")

    op.drop_index("idx_easysql_turns_session", table_name="easysql_turns")
    op.drop_table("easysql_turns")
