"""add user_signup_surveys table

Revision ID: ef642787cb4a
Revises: 35e8f845a79f
Create Date: 2026-09-17 11:06:33.329758

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON

from opendlp.adapters import orm

# revision identifiers, used by Alembic.
revision: str = "ef642787cb4a"
down_revision: str | Sequence[str] | None = "25c6dc66e011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_signup_surveys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("answers", JSON, nullable=False),
        sa.Column("created_at", orm.TZAwareDatetime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_signup_surveys_user_id"), "user_signup_surveys", ["user_id"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_user_signup_surveys_user_id"), table_name="user_signup_surveys")
    op.drop_table("user_signup_surveys")
