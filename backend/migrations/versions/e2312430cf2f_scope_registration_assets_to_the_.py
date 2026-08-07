"""scope registration assets to the assembly

Revision ID: e2312430cf2f
Revises: 0be930d1ad89
Create Date: 2026-08-06 12:24:08.161979

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2312430cf2f"
down_revision: str | Sequence[str] | None = "0be930d1ad89"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _move_to_assembly(table: str) -> None:
    """Repoint a page-scoped asset table at the assembly.

    The column is added nullable and backfilled through the owning page before
    being made NOT NULL, so the migration works on a table that already has
    rows. Backfill is unambiguous only while each assembly has at most one page,
    which the preceding revision still guarantees.
    """
    op.add_column(table, sa.Column("assembly_id", sa.UUID(), nullable=True))

    # `table` is one of this module's own literals, never caller input.
    op.execute(
        f"UPDATE {table} AS a SET assembly_id = p.assembly_id "  # noqa: S608
        f"FROM registration_pages AS p WHERE p.id = a.registration_page_id"
    )
    op.alter_column(table, "assembly_id", nullable=False)

    op.drop_index(op.f(f"ix_{table}_page_sha_unique"), table_name=table)
    op.drop_index(op.f(f"ix_{table}_registration_page_id"), table_name=table)
    op.create_index(op.f(f"ix_{table}_assembly_id"), table, ["assembly_id"], unique=False)
    op.create_index(f"ix_{table}_assembly_sha_unique", table, ["assembly_id", "sha256"], unique=True)
    op.drop_constraint(op.f(f"{table}_registration_page_id_fkey"), table, type_="foreignkey")
    op.create_foreign_key(f"{table}_assembly_id_fkey", table, "assemblies", ["assembly_id"], ["id"], ondelete="CASCADE")
    op.drop_column(table, "registration_page_id")


def _move_to_page(table: str) -> None:
    """Repoint an assembly-scoped asset table back at a registration page.

    An assembly-scoped asset has no single owning page, so the backfill picks the
    assembly's oldest page. Rows whose assembly has no page cannot be represented
    and are dropped.
    """
    op.add_column(table, sa.Column("registration_page_id", sa.UUID(), nullable=True))
    op.execute(
        f"UPDATE {table} AS a SET registration_page_id = ("  # noqa: S608
        "SELECT p.id FROM registration_pages AS p "
        "WHERE p.assembly_id = a.assembly_id ORDER BY p.created_at LIMIT 1)"
    )
    op.execute(f"DELETE FROM {table} WHERE registration_page_id IS NULL")  # noqa: S608
    op.alter_column(table, "registration_page_id", nullable=False)

    op.drop_index(f"ix_{table}_assembly_sha_unique", table_name=table)
    op.drop_index(op.f(f"ix_{table}_assembly_id"), table_name=table)
    op.create_index(op.f(f"ix_{table}_registration_page_id"), table, ["registration_page_id"], unique=False)
    op.create_index(op.f(f"ix_{table}_page_sha_unique"), table, ["registration_page_id", "sha256"], unique=True)
    op.drop_constraint(f"{table}_assembly_id_fkey", table, type_="foreignkey")
    op.create_foreign_key(
        op.f(f"{table}_registration_page_id_fkey"),
        table,
        "registration_pages",
        ["registration_page_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column(table, "assembly_id")


def upgrade() -> None:
    """Upgrade schema."""
    _move_to_assembly("registration_images")
    _move_to_assembly("registration_documents")


def downgrade() -> None:
    """Downgrade schema."""
    _move_to_page("registration_documents")
    _move_to_page("registration_images")
