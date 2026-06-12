"""add on_registration_page to respondent field definitions

Revision ID: 974f13035459
Revises: 28ad0135cfe8
Create Date: 2026-06-08 21:07:43.147671

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "974f13035459"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "28ad0135cfe8"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "respondent_field_definitions",
        sa.Column("on_registration_page", sa.String(length=32), nullable=False, server_default="yes_required"),
    )

    # Preserve today's "everything required" behaviour: derived fields are
    # never on the form, stay_on_db is an optional checkbox, the rest stay
    # required (the column default).
    op.execute(sa.text("UPDATE respondent_field_definitions SET on_registration_page = 'no' WHERE is_derived = true"))
    op.execute(
        sa.text(
            "UPDATE respondent_field_definitions SET on_registration_page = 'yes_optional' "
            "WHERE field_key = 'stay_on_db'"
        )
    )

    op.alter_column("respondent_field_definitions", "on_registration_page", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("respondent_field_definitions", "on_registration_page")
