"""rename assembly field gsheet to gsheet_url

Revision ID: d252dc8f3a62
Revises: d87ee6f88367
Create Date: 2025-09-05 10:07:05.969734

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d252dc8f3a62"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "d87ee6f88367"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("assemblies", "gsheet", nullable=False, new_column_name="gsheet_url")


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("assemblies", "gsheet_url", nullable=False, new_column_name="gsheet")
