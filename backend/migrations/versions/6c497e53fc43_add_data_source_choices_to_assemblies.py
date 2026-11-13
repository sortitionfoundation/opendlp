"""add data source choices to assemblies

Revision ID: 6c497e53fc43
Revises: a62d0a510eee
Create Date: 2026-11-13 14:28:33.689358

Records what an organiser said about where a project's data is managed, and
how they mean to get its targets and respondents in. The empty string means
"not yet said", which is what every existing project gets: the location of a
project that already has data is still worked out from that data.

Backwards compatible: the previous release neither reads nor writes these
columns, and the server default fills them for the rows it inserts.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c497e53fc43"
down_revision: str | Sequence[str] | None = "a62d0a510eee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("assemblies", sa.Column("data_source", sa.String(length=20), server_default="", nullable=False))
    op.add_column("assemblies", sa.Column("targets_source", sa.String(length=20), server_default="", nullable=False))
    op.add_column(
        "assemblies", sa.Column("respondents_source", sa.String(length=20), server_default="", nullable=False)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("assemblies", "respondents_source")
    op.drop_column("assemblies", "targets_source")
    op.drop_column("assemblies", "data_source")
