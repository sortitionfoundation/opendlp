"""add email templates send records and reply-to

Revision ID: 5e06447b7861
Revises: a644849bb5d2
Create Date: 2026-06-16 13:59:17.360873

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from opendlp.adapters import orm
from opendlp.domain.email_send_record import EmailSendOutcome

# revision identifiers, used by Alembic.
revision: str = "5e06447b7861"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "a644849bb5d2"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
    op.create_table(
        "respondent_email_send_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("respondent_id", sa.UUID(), nullable=False),
        sa.Column("email_template_id", sa.UUID(), nullable=True),
        sa.Column("to_email", sa.String(length=255), nullable=False),
        sa.Column("from_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("outcome", orm.EnumAsString(EmailSendOutcome, 16), nullable=False),
        sa.Column("missing_variables", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", orm.TZAwareDatetime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["email_template_id"], ["email_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["respondent_id"], ["respondents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_respondent_email_send_records_respondent_id"),
        "respondent_email_send_records",
        ["respondent_id"],
        unique=False,
    )
    op.add_column("assemblies", sa.Column("reply_to_name", sa.String(length=255), server_default="", nullable=False))
    op.add_column("assemblies", sa.Column("reply_to_email", sa.String(length=255), server_default="", nullable=False))
    op.add_column("registration_pages", sa.Column("auto_reply_email_template_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_registration_pages_auto_reply_email_template_id",
        "registration_pages",
        "email_templates",
        ["auto_reply_email_template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_registration_pages_auto_reply_email_template_id", "registration_pages", type_="foreignkey")
    op.drop_column("registration_pages", "auto_reply_email_template_id")
    op.drop_column("assemblies", "reply_to_email")
    op.drop_column("assemblies", "reply_to_name")
    op.drop_index(op.f("ix_respondent_email_send_records_respondent_id"), table_name="respondent_email_send_records")
    op.drop_table("respondent_email_send_records")
    op.drop_index(op.f("ix_email_templates_assembly_id"), table_name="email_templates")
    op.drop_table("email_templates")
