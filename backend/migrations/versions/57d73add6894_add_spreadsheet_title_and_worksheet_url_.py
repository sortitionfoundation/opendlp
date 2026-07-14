"""add spreadsheet_title and worksheet_url to assembly_respondent_gsheets

Revision ID: 57d73add6894
Revises: 97bd06e3418a
Create Date: 2026-07-14 14:34:17.188227

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "57d73add6894"
down_revision: str | Sequence[str] | None = "97bd06e3418a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "assembly_respondent_gsheets",
        sa.Column("spreadsheet_title", sa.String(length=500), nullable=False, server_default=""),
    )
    op.add_column(
        "assembly_respondent_gsheets",
        sa.Column("worksheet_url", sa.String(length=500), nullable=False, server_default=""),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("assembly_respondent_gsheets", "worksheet_url")
    op.drop_column("assembly_respondent_gsheets", "spreadsheet_title")
