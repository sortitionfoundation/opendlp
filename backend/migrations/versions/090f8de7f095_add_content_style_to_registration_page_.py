"""add content_style to registration_page_html_sources

Revision ID: 090f8de7f095
Revises: d4cb2346b066
Create Date: 2026-10-08 17:07:34.385543

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "090f8de7f095"
down_revision: str | Sequence[str] | None = "d4cb2346b066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # EnumAsString stores plain strings; autogenerate cannot name the custom type.
    # Existing pages get "plain", so none of them renders differently.
    op.add_column(
        "registration_page_html_sources",
        sa.Column("content_style", sa.String(length=16), server_default="plain", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("registration_page_html_sources", "content_style")
