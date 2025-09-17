"""Add assembly_gsheets table

Revision ID: 1d7768eabf9a
Revises: d252dc8f3a62
Create Date: 2025-09-17 12:09:27.861829

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1d7768eabf9a"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "d252dc8f3a62"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "assembly_gsheets",
        sa.Column("assembly_gsheet_id", sa.UUID(), nullable=False),
        sa.Column("assembly_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("select_registrants_tab", sa.String(length=100), nullable=False),
        sa.Column("select_targets_tab", sa.String(length=100), nullable=False),
        sa.Column("replace_registrants_tab", sa.String(length=100), nullable=False),
        sa.Column("replace_targets_tab", sa.String(length=100), nullable=False),
        sa.Column("generate_remaining_tab", sa.Boolean(), nullable=False),
        sa.Column("id_column", sa.String(length=100), nullable=False),
        sa.Column("check_same_address", sa.Boolean(), nullable=False),
        sa.Column("check_same_address_cols", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("columns_to_keep", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("selection_algorithm", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["assembly_id"], ["assemblies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("assembly_gsheet_id"),
        sa.UniqueConstraint("assembly_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("assembly_gsheets")
