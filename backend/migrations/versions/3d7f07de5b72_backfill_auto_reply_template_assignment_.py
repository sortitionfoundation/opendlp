"""backfill auto reply template assignment always on

Revision ID: 3d7f07de5b72
Revises: 62e37f3ab7e8
Create Date: 2026-07-28 11:02:19.650130

The auto-reply is always-on: the enable/disable toggle (which worked by
clearing registration_pages.auto_reply_email_template_id) has been removed, so
a page whose assembly has a template must have that template assigned. This
backfills the assignment for any page left unassigned by the old toggle,
picking the assembly's oldest template (the seeded default). The toggle never
shipped to production, so no deliberate "off" choice is being overridden.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3d7f07de5b72"
down_revision: str | Sequence[str] | None = "62e37f3ab7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Assign each assembly's oldest email template to its unassigned registration page."""
    op.execute(
        sa.text(
            """
            UPDATE registration_pages AS rp
            SET auto_reply_email_template_id = t.id
            FROM (
                SELECT DISTINCT ON (assembly_id) id, assembly_id
                FROM email_templates
                ORDER BY assembly_id, created_at
            ) AS t
            WHERE rp.auto_reply_email_template_id IS NULL
              AND t.assembly_id = rp.assembly_id
            """
        )
    )


def downgrade() -> None:
    """Irreversible data migration: the pre-backfill NULLs are not recorded, so
    there is nothing to restore — and the always-on rule makes the old state
    invalid anyway."""
    pass
