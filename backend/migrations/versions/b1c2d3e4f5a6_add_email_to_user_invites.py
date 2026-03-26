"""add email to user_invites

Revision ID: b1c2d3e4f5a6
Revises: ae1e11ac18e2
Create Date: 2026-03-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "ae1e11ac18e2"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add email column to user_invites table."""
    op.add_column(
        "user_invites",
        sa.Column("email", sa.String(length=255), nullable=True, server_default=""),
    )

    # Set existing rows to empty string
    op.execute(
        """
        UPDATE user_invites
        SET email = ''
        WHERE email IS NULL
        """
    )


def downgrade() -> None:
    """Remove email column from user_invites table."""
    op.drop_column("user_invites", "email")
