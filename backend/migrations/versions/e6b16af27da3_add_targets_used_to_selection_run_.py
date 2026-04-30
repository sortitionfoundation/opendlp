"""add targets_used to selection_run_records

Revision ID: e6b16af27da3
Revises: f34431334932
Create Date: 2026-04-28 17:31:54.167839

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e6b16af27da3"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "f34431334932"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "selection_run_records",
        sa.Column(
            "targets_used",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("selection_run_records", "targets_used")
