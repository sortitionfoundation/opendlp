"""add sessions_invalidated_at to users

Revision ID: 1ce9bb5eb31f
Revises: 4b420dba5d65
Create Date: 2026-08-27 13:54:18.640126

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import opendlp.adapters.orm

# revision identifiers, used by Alembic.
revision: str = "1ce9bb5eb31f"
down_revision: str | Sequence[str] | None = "4b420dba5d65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("sessions_invalidated_at", opendlp.adapters.orm.TZAwareDatetime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "sessions_invalidated_at")
