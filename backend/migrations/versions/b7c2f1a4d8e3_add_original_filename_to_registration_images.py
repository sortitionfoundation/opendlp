"""add original_filename to registration_images

Revision ID: b7c2f1a4d8e3
Revises: a644849bb5d2
Create Date: 2026-06-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c2f1a4d8e3"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "a644849bb5d2"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "registration_images",
        sa.Column("original_filename", sa.String(length=255), nullable=False, server_default=""),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("registration_images", "original_filename")
