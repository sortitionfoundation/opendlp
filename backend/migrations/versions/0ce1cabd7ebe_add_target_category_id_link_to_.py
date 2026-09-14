"""add target_category_id link to respondent field definitions

Revision ID: 0ce1cabd7ebe
Revises: 35e8f845a79f
Create Date: 2026-09-14 12:53:01.686568

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0ce1cabd7ebe"
down_revision: str | Sequence[str] | None = "35e8f845a79f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "respondent_field_definitions_target_category_id_fkey"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("respondent_field_definitions", sa.Column("target_category_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_respondent_field_definitions_target_category_id"),
        "respondent_field_definitions",
        ["target_category_id"],
        unique=False,
    )
    op.create_foreign_key(
        FK_NAME,
        "respondent_field_definitions",
        "target_categories",
        ["target_category_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(FK_NAME, "respondent_field_definitions", type_="foreignkey")
    op.drop_index(op.f("ix_respondent_field_definitions_target_category_id"), table_name="respondent_field_definitions")
    op.drop_column("respondent_field_definitions", "target_category_id")
