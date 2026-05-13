"""Add field_type and options to respondent_field_definitions

Revision ID: bc31250a8ad0
Revises: 38e2fb249cdd
Create Date: 2026-04-23 16:14:34.454976

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "bc31250a8ad0"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "38e2fb249cdd"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FIXED_FIELD_TYPE_MAP = {
    "email": "email",
    "eligible": "bool_or_none",
    "can_attend": "bool_or_none",
    "consent": "bool_or_none",
    "stay_on_db": "bool_or_none",
}


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "respondent_field_definitions",
        sa.Column("field_type", sa.String(length=32), nullable=False, server_default="text"),
    )
    op.add_column(
        "respondent_field_definitions",
        sa.Column("options", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )

    for field_key, field_type in FIXED_FIELD_TYPE_MAP.items():
        op.execute(
            sa.text(
                "UPDATE respondent_field_definitions SET field_type = :field_type WHERE field_key = :field_key"
            ).bindparams(field_type=field_type, field_key=field_key)
        )

    op.alter_column("respondent_field_definitions", "field_type", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("respondent_field_definitions", "options")
    op.drop_column("respondent_field_definitions", "field_type")
