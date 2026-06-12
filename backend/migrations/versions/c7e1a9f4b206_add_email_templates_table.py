"""add email templates table and registration auto-reply link

Revision ID: c7e1a9f4b206
Revises: 28ad0135cfe8
Create Date: 2026-06-12 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from opendlp.adapters import orm

# revision identifiers, used by Alembic.
revision: str = "c7e1a9f4b206"
down_revision: str | Sequence[str] | None = "28ad0135cfe8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUTO_REPLY_FK = "fk_registration_pages_auto_reply_email_template_id"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "email_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assembly_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("created_at", orm.TZAwareDatetime(timezone=True), nullable=False),
        sa.Column("updated_at", orm.TZAwareDatetime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assembly_id"], ["assemblies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_templates_assembly_id"), "email_templates", ["assembly_id"], unique=False)

    op.add_column(
        "registration_pages",
        sa.Column("auto_reply_email_template_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        _AUTO_REPLY_FK,
        "registration_pages",
        "email_templates",
        ["auto_reply_email_template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(_AUTO_REPLY_FK, "registration_pages", type_="foreignkey")
    op.drop_column("registration_pages", "auto_reply_email_template_id")
    op.drop_index(op.f("ix_email_templates_assembly_id"), table_name="email_templates")
    op.drop_table("email_templates")
