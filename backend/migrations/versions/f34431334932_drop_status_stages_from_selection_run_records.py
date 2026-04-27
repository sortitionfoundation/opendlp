"""drop unused status_stages column from selection_run_records

Revision ID: f34431334932
Revises: af1f1d62035b
Create Date: 2026-04-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f34431334932"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "af1f1d62035b"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("selection_run_records", "status_stages")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("selection_run_records", sa.Column("status_stages", sa.JSON(), nullable=True))
