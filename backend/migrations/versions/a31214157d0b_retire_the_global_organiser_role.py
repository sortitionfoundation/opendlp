"""retire the global-organiser role

Revision ID: a31214157d0b
Revises: a1f4c7d20b93
Create Date: 2026-09-03 11:18:20.707372

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a31214157d0b"
down_revision: str | Sequence[str] | None = "a1f4c7d20b93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# `global-organiser` is retired: the role it named is gone, and `organiser` now
# means something narrower (create assemblies, see only your own). Anyone still
# holding the old value is converted to `user` and has whatever access they
# actually need granted by hand afterwards. Both columns store the role as its
# string value, so this is a value update rather than a type change.
#
# The application cannot load a row holding a value no longer in the GlobalRole
# enum, so this migration is not optional - an unconverted account fails to load
# rather than logging in with reduced access.
RETIRE_ROLE_ON_USERS = """
    UPDATE users SET global_role = 'user' WHERE global_role = 'global-organiser'
"""

# An unredeemed invite promising the old role becomes a plain user invite, so
# whoever holds that link signs up with less access than they were offered.
RETIRE_ROLE_ON_INVITES = """
    UPDATE user_invites SET global_role = 'user' WHERE global_role = 'global-organiser'
"""


def upgrade() -> None:
    op.execute(RETIRE_ROLE_ON_USERS)
    op.execute(RETIRE_ROLE_ON_INVITES)


def downgrade() -> None:
    """Deliberately a no-op: the upgrade cannot be reversed.

    After the update there is nothing distinguishing a converted row from one
    that was always `user`, so any downgrade would have to guess. Turning every
    user into a global-organiser to make the migration look reversible would be
    a privilege escalation, so we do nothing and say so.
    """
