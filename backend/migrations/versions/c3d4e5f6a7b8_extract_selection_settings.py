"""ABOUTME: Alembic migration to extract selection settings from assembly_csv and assembly_gsheets
ABOUTME: Creates selection_settings table, copies data, drops columns, renames id_column

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-03-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create selection_settings table
    op.create_table(
        "selection_settings",
        sa.Column("selection_settings_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assembly_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assemblies.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("id_column", sa.String(100), nullable=False, server_default="external_id"),
        sa.Column("check_same_address", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("check_same_address_cols", postgresql.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("columns_to_keep", postgresql.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("selection_algorithm", sa.String(50), nullable=False, server_default="maximin"),
    )

    # 2. Copy from assembly_gsheets (these have the actively-used settings for gsheet assemblies)
    op.execute(
        """
        INSERT INTO selection_settings (selection_settings_id, assembly_id, id_column,
            check_same_address, check_same_address_cols, columns_to_keep, selection_algorithm)
        SELECT gen_random_uuid(), assembly_id, id_column,
            check_same_address, check_same_address_cols, columns_to_keep, selection_algorithm
        FROM assembly_gsheets
        """
    )

    # 3. Copy from assembly_csv where assembly doesn't already have selection_settings
    op.execute(
        """
        INSERT INTO selection_settings (selection_settings_id, assembly_id, id_column,
            check_same_address, check_same_address_cols, columns_to_keep, selection_algorithm)
        SELECT gen_random_uuid(), assembly_id, id_column,
            check_same_address, check_same_address_cols, columns_to_keep, selection_algorithm
        FROM assembly_csv
        WHERE assembly_id NOT IN (SELECT assembly_id FROM selection_settings)
        """
    )

    # 4. Create default selection_settings for assemblies that have neither
    op.execute(
        """
        INSERT INTO selection_settings (selection_settings_id, assembly_id, id_column,
            check_same_address, check_same_address_cols, columns_to_keep, selection_algorithm)
        SELECT gen_random_uuid(), id, 'external_id', true, '[]'::json, '[]'::json, 'maximin'
        FROM assemblies
        WHERE id NOT IN (SELECT assembly_id FROM selection_settings)
        """
    )

    # 5. Drop columns from assembly_gsheets
    op.drop_column("assembly_gsheets", "id_column")
    op.drop_column("assembly_gsheets", "check_same_address")
    op.drop_column("assembly_gsheets", "check_same_address_cols")
    op.drop_column("assembly_gsheets", "columns_to_keep")
    op.drop_column("assembly_gsheets", "selection_algorithm")

    # 6. Drop columns from assembly_csv (4 of the 5 — id_column stays but is renamed)
    op.drop_column("assembly_csv", "check_same_address")
    op.drop_column("assembly_csv", "check_same_address_cols")
    op.drop_column("assembly_csv", "columns_to_keep")
    op.drop_column("assembly_csv", "selection_algorithm")

    # 7. Rename id_column to csv_id_column on assembly_csv
    op.alter_column("assembly_csv", "id_column", new_column_name="csv_id_column")


def downgrade() -> None:
    # 1. Rename csv_id_column back to id_column on assembly_csv
    op.alter_column("assembly_csv", "csv_id_column", new_column_name="id_column")

    # 2. Re-add columns to assembly_csv
    op.add_column(
        "assembly_csv",
        sa.Column("check_same_address", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "assembly_csv",
        sa.Column("check_same_address_cols", postgresql.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column(
        "assembly_csv",
        sa.Column("columns_to_keep", postgresql.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column(
        "assembly_csv",
        sa.Column("selection_algorithm", sa.String(50), nullable=False, server_default="maximin"),
    )

    # 3. Re-add columns to assembly_gsheets
    op.add_column(
        "assembly_gsheets",
        sa.Column("id_column", sa.String(100), nullable=False, server_default="nationbuilder_id"),
    )
    op.add_column(
        "assembly_gsheets",
        sa.Column("check_same_address", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "assembly_gsheets",
        sa.Column("check_same_address_cols", postgresql.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column(
        "assembly_gsheets",
        sa.Column("columns_to_keep", postgresql.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column(
        "assembly_gsheets",
        sa.Column("selection_algorithm", sa.String(50), nullable=False, server_default="maximin"),
    )

    # 4. Copy data back from selection_settings to assembly_gsheets
    op.execute(
        """
        UPDATE assembly_gsheets SET
            id_column = ss.id_column,
            check_same_address = ss.check_same_address,
            check_same_address_cols = ss.check_same_address_cols,
            columns_to_keep = ss.columns_to_keep,
            selection_algorithm = ss.selection_algorithm
        FROM selection_settings ss
        WHERE assembly_gsheets.assembly_id = ss.assembly_id
        """
    )

    # 5. Copy data back from selection_settings to assembly_csv
    op.execute(
        """
        UPDATE assembly_csv SET
            check_same_address = ss.check_same_address,
            check_same_address_cols = ss.check_same_address_cols,
            columns_to_keep = ss.columns_to_keep,
            selection_algorithm = ss.selection_algorithm
        FROM selection_settings ss
        WHERE assembly_csv.assembly_id = ss.assembly_id
        """
    )

    # 6. Drop selection_settings table
    op.drop_table("selection_settings")
