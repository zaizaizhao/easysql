"""add runtime config table

Revision ID: 0003_add_config_table
Revises: 0002_split_turns_table
Create Date: 2026-02-11 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_add_config_table"
down_revision = "0002_split_turns_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "easysql_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=20), nullable=False),
        sa.Column("is_secret", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("category", "key", name="uq_easysql_configs_cat_key"),
    )
    op.create_index(
        "idx_easysql_configs_category",
        "easysql_configs",
        ["category"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_easysql_configs_category", table_name="easysql_configs")
    op.drop_table("easysql_configs")
