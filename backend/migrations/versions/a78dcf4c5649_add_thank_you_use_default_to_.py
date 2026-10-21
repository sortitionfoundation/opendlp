"""add thank_you_use_default to registration_pages

Revision ID: a78dcf4c5649
Revises: 9d468767d423
Create Date: 2026-10-21 19:24:45.384327

A page now chooses between the standard, translated thank-you page and its own
HTML. Until now every page was seeded with OLD_DEFAULT_THANK_YOU_HTML and had no
way to change it, so those pages switch to the standard page, which says the
same in the respondent's language, and their copy of the old default is blanked:
it opens in the visual editor's HTML view, and the step's starter button offers
a version that does not. A page holding any other HTML keeps it and shows it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a78dcf4c5649"
down_revision: str | Sequence[str] | None = "9d468767d423"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# What every page was seeded with before this migration, spelled out so the
# migration does not change when the domain's starter does.
OLD_DEFAULT_THANK_YOU_HTML = """\
<div class="govuk-grid-row">
    <div class="govuk-grid-column-two-thirds" style="float: none; margin: 0 auto;">
        <div class="govuk-panel govuk-panel--confirmation">
            <h1 class="govuk-panel__title">Thank you for registering</h1>
            <div class="govuk-panel__body">Your registration has been received</div>
        </div>
        <p class="govuk-body">We'll be in touch.</p>
    </div>
</div>
"""

KEEP_OWN_THANK_YOU = sa.text(
    """
    UPDATE registration_pages SET thank_you_use_default = false
    WHERE btrim(thank_you_html) <> '' AND thank_you_html <> :old_default
    """
).bindparams(old_default=OLD_DEFAULT_THANK_YOU_HTML)

BLANK_OLD_DEFAULT = sa.text(
    "UPDATE registration_pages SET thank_you_html = '' WHERE thank_you_html = :old_default"
).bindparams(old_default=OLD_DEFAULT_THANK_YOU_HTML)

RESTORE_OLD_DEFAULT = sa.text(
    """
    UPDATE registration_pages SET thank_you_html = :old_default
    WHERE thank_you_use_default AND btrim(thank_you_html) = ''
    """
).bindparams(old_default=OLD_DEFAULT_THANK_YOU_HTML)


def upgrade() -> None:
    """Add the flag, on by default; keep pages with HTML of their own on it."""
    op.add_column(
        "registration_pages",
        sa.Column("thank_you_use_default", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.execute(KEEP_OWN_THANK_YOU)
    op.execute(BLANK_OLD_DEFAULT)


def downgrade() -> None:
    """Put the old default back where the standard page was in use, then drop the flag."""
    op.execute(RESTORE_OLD_DEFAULT)
    op.drop_column("registration_pages", "thank_you_use_default")
