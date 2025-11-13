"""add password reset tokens table

Revision ID: a1b2c3d4e5f6
Revises: d87ee6f88367
Create Date: 2025-01-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import opendlp.adapters.orm

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "d87ee6f88367"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create password_reset_tokens table
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", opendlp.adapters.orm.CrossDatabaseUUID(), nullable=False),
        sa.Column(
            "user_id",
            opendlp.adapters.orm.CrossDatabaseUUID(),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            opendlp.adapters.orm.TZAwareDatetime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            opendlp.adapters.orm.TZAwareDatetime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "used_at",
            opendlp.adapters.orm.TZAwareDatetime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(
        op.f("ix_password_reset_tokens_created_at"),
        "password_reset_tokens",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_expires_at"),
        "password_reset_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_token"),
        "password_reset_tokens",
        ["token"],
        unique=True,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_user_id"),
        "password_reset_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index(
        op.f("ix_password_reset_tokens_user_id"),
        table_name="password_reset_tokens",
    )
    op.drop_index(
        op.f("ix_password_reset_tokens_token"),
        table_name="password_reset_tokens",
    )
    op.drop_index(
        op.f("ix_password_reset_tokens_expires_at"),
        table_name="password_reset_tokens",
    )
    op.drop_index(
        op.f("ix_password_reset_tokens_created_at"),
        table_name="password_reset_tokens",
    )

    # Drop table
    op.drop_table("password_reset_tokens")
