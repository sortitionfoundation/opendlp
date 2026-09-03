"""generalise assembly_respondent_gsheets into assembly_export_gsheets

Renames the table rather than dropping and recreating it, so every saved
export config survives. Autogenerate renders a rename as drop + create, which
would discard them all, so this revision is written by hand.

Revision ID: a1f4c7d20b93
Revises: bb9ef5dce9be
Create Date: 2026-09-03 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f4c7d20b93"
down_revision: str | Sequence[str] | None = "bb9ef5dce9be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TABLE = "assembly_respondent_gsheets"
NEW_TABLE = "assembly_export_gsheets"


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table(OLD_TABLE, NEW_TABLE)
    op.alter_column(NEW_TABLE, "assembly_respondent_gsheet_id", new_column_name="assembly_export_gsheet_id")

    # Every existing row is a respondent export; the default exists only to fill
    # them in, so it goes once they are filled.
    op.add_column(
        NEW_TABLE,
        sa.Column("export_kind", sa.String(length=50), nullable=False, server_default="RESPONDENTS"),
    )
    op.alter_column(NEW_TABLE, "export_kind", server_default=None)

    # Uniqueness moves from the assembly to the (assembly, kind) pair, so an
    # assembly can have one sheet per export kind.
    op.drop_index(op.f(f"ix_{OLD_TABLE}_assembly_id"), table_name=NEW_TABLE)
    op.create_index(op.f(f"ix_{NEW_TABLE}_assembly_id"), NEW_TABLE, ["assembly_id"], unique=False)
    op.create_unique_constraint(
        "uq_assembly_export_gsheets_assembly_kind",
        NEW_TABLE,
        ["assembly_id", "export_kind"],
    )


def downgrade() -> None:
    """Downgrade schema.

    Rows for any export kind other than RESPONDENTS are dropped: the old table
    has nowhere to put them.
    """
    op.execute(sa.text(f"DELETE FROM {NEW_TABLE} WHERE export_kind <> 'RESPONDENTS'"))  # noqa: S608

    op.drop_constraint("uq_assembly_export_gsheets_assembly_kind", NEW_TABLE, type_="unique")
    op.drop_index(op.f(f"ix_{NEW_TABLE}_assembly_id"), table_name=NEW_TABLE)
    op.drop_column(NEW_TABLE, "export_kind")

    op.alter_column(NEW_TABLE, "assembly_export_gsheet_id", new_column_name="assembly_respondent_gsheet_id")
    op.rename_table(NEW_TABLE, OLD_TABLE)
    op.create_index(op.f(f"ix_{OLD_TABLE}_assembly_id"), OLD_TABLE, ["assembly_id"], unique=True)
