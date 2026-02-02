"""add email confirmation

Revision ID: f1g2h3i4j5k6
Revises: d0da5f725d79
Create Date: 2026-01-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import opendlp.adapters.orm

# revision identifiers, used by Alembic.
revision: str = "f1g2h3i4j5k6"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "d0da5f725d79"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add email_confirmed_at column to users table
    op.add_column(
        "users",
        sa.Column(
            "email_confirmed_at",
            opendlp.adapters.orm.TZAwareDatetime(timezone=True),
            nullable=True,
        ),
    )

    # Grandfather existing users: set email_confirmed_at = created_at
    op.execute(
        """
        UPDATE users
        SET email_confirmed_at = created_at
        WHERE email_confirmed_at IS NULL
        """
    )

    # Create email_confirmation_tokens table
    op.create_table(
        "email_confirmation_tokens",
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
        op.f("ix_email_confirmation_tokens_created_at"),
        "email_confirmation_tokens",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_confirmation_tokens_expires_at"),
        "email_confirmation_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_confirmation_tokens_token"),
        "email_confirmation_tokens",
        ["token"],
        unique=True,
    )
    op.create_index(
        op.f("ix_email_confirmation_tokens_user_id"),
        "email_confirmation_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index(
        op.f("ix_email_confirmation_tokens_user_id"),
        table_name="email_confirmation_tokens",
    )
    op.drop_index(
        op.f("ix_email_confirmation_tokens_token"),
        table_name="email_confirmation_tokens",
    )
    op.drop_index(
        op.f("ix_email_confirmation_tokens_expires_at"),
        table_name="email_confirmation_tokens",
    )
    op.drop_index(
        op.f("ix_email_confirmation_tokens_created_at"),
        table_name="email_confirmation_tokens",
    )

    # Drop table
    op.drop_table("email_confirmation_tokens")

    # Remove email_confirmed_at column from users table
    op.drop_column("users", "email_confirmed_at")
