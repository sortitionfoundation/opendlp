"""record who created an assembly

Revision ID: aedb402e99ad
Revises: a31214157d0b
Create Date: 2026-09-03 12:04:08.110410

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aedb402e99ad"
down_revision: str | Sequence[str] | None = "a31214157d0b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "assemblies_created_by_user_id_fkey"


def upgrade() -> None:
    # Nullable and not backfilled: assemblies created before this column existed
    # have no recorded creator, and guessing one from the earliest
    # assembly-manager role would be plausible-looking and often wrong.
    op.add_column("assemblies", sa.Column("created_by_user_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_assemblies_created_by_user_id"), "assemblies", ["created_by_user_id"], unique=False)
    # SET NULL, not CASCADE - deleting a user must never delete their assemblies.
    op.create_foreign_key(FK_NAME, "assemblies", "users", ["created_by_user_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint(FK_NAME, "assemblies", type_="foreignkey")
    op.drop_index(op.f("ix_assemblies_created_by_user_id"), table_name="assemblies")
    op.drop_column("assemblies", "created_by_user_id")
