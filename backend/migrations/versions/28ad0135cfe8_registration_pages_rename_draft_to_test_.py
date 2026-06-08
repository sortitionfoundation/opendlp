"""registration pages rename DRAFT to TEST and drop preview_token

Revision ID: 28ad0135cfe8
Revises: 6157c89afb01
Create Date: 2026-05-20 16:54:36.624503

These tables are unreleased (introduced on the 610-registration-page-html
branch), so this migration stacks on top rather than backfilling production
data. The preview token is retired: a TEST page now loads publicly at its slug
with no token. Downgrade restores an empty preview_token column and maps TEST
back to DRAFT (lossy: regenerated tokens cannot be recovered).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "28ad0135cfe8"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "6157c89afb01"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        UPDATE registration_pages
        SET status = 'TEST'
        WHERE status = 'DRAFT'
        """
    )
    op.drop_column("registration_pages", "preview_token")


def downgrade() -> None:
    """Downgrade schema. Lossy: TEST rows become DRAFT; preview tokens are blank."""
    op.add_column(
        "registration_pages",
        sa.Column("preview_token", sa.String(length=64), nullable=False, server_default=sa.text("''")),
    )
    op.alter_column("registration_pages", "preview_token", server_default=None)
    op.execute(
        """
        UPDATE registration_pages
        SET status = 'DRAFT'
        WHERE status = 'TEST'
        """
    )
