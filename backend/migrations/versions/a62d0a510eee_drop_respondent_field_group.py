"""drop respondent field group

Revision ID: a62d0a510eee
Revises: 4a7c0b3d443b
Create Date: 2026-10-29 12:40:00.000000

Registration questions are one ordered list now, with headings and text placed
among them (4a7c0b3d443b turned the old sections into headings), so nothing
reads field_group. This drops it, and swaps the index that ordered by it for
one on the order the list uses.

A downgrade puts the column back with every question in "other" and every
derived field in "derived": the sections the questions were in are not
recorded anywhere once the column has gone. The code that downgrade returns to
orders by sort_order alone, so nothing it shows changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a62d0a510eee"
down_revision: str | Sequence[str] | None = "4a7c0b3d443b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop field_group and its index; index the list order instead."""
    op.drop_index(
        op.f("ix_respondent_field_definitions_assembly_group_order"), table_name="respondent_field_definitions"
    )
    op.drop_column("respondent_field_definitions", "field_group")
    op.create_index(
        "ix_respondent_field_definitions_assembly_order",
        "respondent_field_definitions",
        ["assembly_id", "sort_order"],
        unique=False,
    )


def downgrade() -> None:
    """Put field_group back, filled with "other" or "derived"."""
    op.drop_index("ix_respondent_field_definitions_assembly_order", table_name="respondent_field_definitions")
    op.add_column(
        "respondent_field_definitions",
        sa.Column("field_group", sa.String(length=50), nullable=False, server_default="other"),
    )
    op.execute("UPDATE respondent_field_definitions SET field_group = 'derived' WHERE is_derived")
    op.alter_column("respondent_field_definitions", "field_group", server_default=None)
    op.create_index(
        op.f("ix_respondent_field_definitions_assembly_group_order"),
        "respondent_field_definitions",
        ["assembly_id", "field_group", "sort_order"],
        unique=False,
    )
