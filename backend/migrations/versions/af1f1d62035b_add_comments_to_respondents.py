"""add comments to respondents

Revision ID: af1f1d62035b
Revises: 0dd36337f48e
Create Date: 2026-04-17 14:36:22.066254

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "af1f1d62035b"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "0dd36337f48e"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "respondents",
        sa.Column(
            "comments",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("respondents", "comments")
