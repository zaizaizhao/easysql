"""add multi-database session routing fields

Revision ID: 0004_multi_db_sessions
Revises: 0003_add_config_table
Create Date: 2026-08-29 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_multi_db_sessions"
down_revision = "0003_add_config_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "easysql_sessions",
        sa.Column("db_names", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "easysql_sessions",
        sa.Column("primary_db", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "easysql_turns",
        sa.Column("primary_db", sa.String(length=100), nullable=True),
    )

    op.execute(
        "UPDATE easysql_sessions "
        "SET db_names = ARRAY[db_name], primary_db = db_name "
        "WHERE db_name IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("easysql_turns", "primary_db")
    op.drop_column("easysql_sessions", "primary_db")
    op.drop_column("easysql_sessions", "db_names")
