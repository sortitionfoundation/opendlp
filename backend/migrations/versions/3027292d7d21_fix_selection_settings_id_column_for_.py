"""ABOUTME: Data migration to fix selection_settings.id_column for CSV-based assemblies.
ABOUTME: Sets id_column to 'external_id' where it was incorrectly copied from assembly_csv.

fix selection_settings id_column for csv assemblies

Revision ID: 3027292d7d21
Revises: c3d4e5f6a7b8
Create Date: 2026-04-10 14:05:27.503907

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3027292d7d21"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The previous migration (c3d4e5f6a7b8) copied id_column from assembly_csv
    # into selection_settings. For CSV-based assemblies, id_column should always
    # be "external_id" because the CSV import normalises the user's chosen column
    # into respondent.external_id. Only GSheet assemblies need a different value.
    op.execute(
        """
        UPDATE selection_settings
        SET id_column = 'external_id'
        WHERE assembly_id IN (
            SELECT assembly_id FROM assembly_csv
        )
        AND assembly_id NOT IN (
            SELECT assembly_id FROM assembly_gsheets
        )
        """
    )


def downgrade() -> None:
    # This is a data-only fix — we cannot restore the original incorrect values,
    # but reverting to external_id is harmless since it is the correct default.
    pass
