"""registration pages status enum and activity log

Revision ID: 6157c89afb01
Revises: 6c832644862b
Create Date: 2026-05-19 15:30:59.417048

Downgrade is lossy: CLOSED rows collapse to is_published=False (indistinguishable
from DRAFT) and the activity log is discarded.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from opendlp.adapters import orm

# revision identifiers, used by Alembic.
revision: str = "6157c89afb01"
down_revision: str | Sequence[str] | None = "6c832644862b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "registration_pages",
        sa.Column("status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "registration_pages",
        sa.Column(
            "activity",
            orm.RegistrationPageActivityListJSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.execute(
        """
        UPDATE registration_pages
        SET status = CASE WHEN is_published THEN 'PUBLISHED' ELSE 'DRAFT' END
        """
    )
    op.alter_column("registration_pages", "status", nullable=False)
    op.create_index(op.f("ix_registration_pages_status"), "registration_pages", ["status"], unique=False)
    op.drop_index(op.f("ix_registration_pages_is_published"), table_name="registration_pages")
    op.drop_column("registration_pages", "is_published")
    op.alter_column("registration_pages", "activity", server_default=None)


def downgrade() -> None:
    """Downgrade schema. Lossy: CLOSED rows become is_published=False; activity log is dropped."""
    op.add_column(
        "registration_pages",
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.execute(
        """
        UPDATE registration_pages
        SET is_published = (status = 'PUBLISHED')
        """
    )
    op.alter_column("registration_pages", "is_published", server_default=None)
    op.create_index(
        op.f("ix_registration_pages_is_published"),
        "registration_pages",
        ["is_published"],
        unique=False,
    )
    op.drop_index(op.f("ix_registration_pages_status"), table_name="registration_pages")
    op.drop_column("registration_pages", "status")
    op.drop_column("registration_pages", "activity")
