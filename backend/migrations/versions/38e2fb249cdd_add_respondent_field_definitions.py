"""add respondent field definitions

Revision ID: 38e2fb249cdd
Revises: 0dd36337f48e
Create Date: 2026-04-17 13:56:32.676722

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID

from opendlp.adapters import orm
from opendlp.domain.respondent_field_schema import RespondentFieldGroup

# revision identifiers, used by Alembic.
revision: str = "38e2fb249cdd"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "0dd36337f48e"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the respondent_field_definitions table. No data backfill here —
    # the service layer auto-populates a schema on first access for assemblies
    # that have respondents but no schema yet (keeps population logic in one place).
    op.create_table(
        "respondent_field_definitions",
        sa.Column("id", PostgresUUID(as_uuid=True), nullable=False),
        sa.Column("assembly_id", PostgresUUID(as_uuid=True), nullable=False),
        sa.Column("field_key", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("field_group", orm.EnumAsString(RespondentFieldGroup, 50), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_fixed", sa.Boolean(), nullable=False),
        sa.Column("is_derived", sa.Boolean(), nullable=False),
        sa.Column("derived_from", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("derivation_kind", sa.String(length=100), nullable=False),
        sa.Column("created_at", orm.TZAwareDatetime(timezone=True), nullable=False),
        sa.Column("updated_at", orm.TZAwareDatetime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assembly_id"], ["assemblies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_respondent_field_definitions_assembly_group_order",
        "respondent_field_definitions",
        ["assembly_id", "field_group", "sort_order"],
        unique=False,
    )
    op.create_index(
        op.f("ix_respondent_field_definitions_assembly_id"),
        "respondent_field_definitions",
        ["assembly_id"],
        unique=False,
    )
    op.create_index(
        "ix_respondent_field_definitions_assembly_key",
        "respondent_field_definitions",
        ["assembly_id", "field_key"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_respondent_field_definitions_assembly_key",
        table_name="respondent_field_definitions",
    )
    op.drop_index(
        op.f("ix_respondent_field_definitions_assembly_id"),
        table_name="respondent_field_definitions",
    )
    op.drop_index(
        "ix_respondent_field_definitions_assembly_group_order",
        table_name="respondent_field_definitions",
    )
    op.drop_table("respondent_field_definitions")
