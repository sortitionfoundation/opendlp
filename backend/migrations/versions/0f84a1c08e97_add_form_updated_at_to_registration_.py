"""add form_updated_at to registration_page_html_sources

Revision ID: 0f84a1c08e97
Revises: 090f8de7f095
Create Date: 2026-10-12 15:05:48.017544

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import opendlp.adapters.orm

# revision identifiers, used by Alembic.
revision: str = "0f84a1c08e97"
down_revision: str | Sequence[str] | None = "090f8de7f095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing rows take updated_at, the closest record of when the form HTML last changed.
    op.add_column(
        "registration_page_html_sources",
        sa.Column("form_updated_at", opendlp.adapters.orm.TZAwareDatetime(timezone=True), nullable=True),
    )
    op.execute("UPDATE registration_page_html_sources SET form_updated_at = updated_at")
    op.alter_column("registration_page_html_sources", "form_updated_at", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("registration_page_html_sources", "form_updated_at")
