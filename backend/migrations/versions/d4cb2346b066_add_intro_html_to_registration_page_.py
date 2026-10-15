"""add intro_html to registration_page_html_sources

Revision ID: d4cb2346b066
Revises: 1eacb37ea6a2
Create Date: 2026-10-07 16:05:17.767137

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4cb2346b066"
down_revision: str | Sequence[str] | None = "1eacb37ea6a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing pages keep their heading inside form_html; an empty intro renders
    # nothing, so no live page changes.
    op.add_column(
        "registration_page_html_sources",
        sa.Column("intro_html", sa.Text(), server_default="", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("registration_page_html_sources", "intro_html")
