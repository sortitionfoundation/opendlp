"""add beta disclaimer agreed at to users

Revision ID: 50903a521008
Revises: a62d0a510eee
Create Date: 2026-11-18 22:00:28.418672

Records when a user ticked the beta disclaimer on the sign-up page, as
user_data_agreement_agreed_at records the data agreement. The column is
nullable and nothing is backfilled: accounts made before the disclaimer never
agreed to it, so they stay null.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import opendlp.adapters.orm

# revision identifiers, used by Alembic.
revision: str = "50903a521008"
down_revision: str | Sequence[str] | None = "a62d0a510eee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("beta_disclaimer_agreed_at", opendlp.adapters.orm.TZAwareDatetime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "beta_disclaimer_agreed_at")
