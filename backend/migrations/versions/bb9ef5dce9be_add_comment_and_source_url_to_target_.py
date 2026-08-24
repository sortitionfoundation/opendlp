"""add comment and source_url to target categories, drop description

Revision ID: bb9ef5dce9be
Revises: 4b420dba5d65
Create Date: 2026-08-24 13:43:38.054493

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bb9ef5dce9be"
down_revision: str | Sequence[str] | None = "4b420dba5d65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Rewrites every stored TargetValue: drops the `description` key the dataclass no
# longer has, and sets minmax_manual on values that already carry a percentage, so
# a later change to number_to_select cannot silently move deliberate min/max.
#
# "values" is a reserved word in Postgres and must be quoted. The column is `json`,
# not `jsonb`, so it is cast in and back out again to get the key-delete operator.
# WITH ORDINALITY plus ORDER BY is load-bearing: the order of values within a
# category is the display order, and jsonb_agg does not guarantee it.
REWRITE_TARGET_VALUES = """
    UPDATE target_categories
    SET "values" = (
        SELECT COALESCE(
            jsonb_agg(
                CASE
                    WHEN jsonb_typeof(elem -> 'percentage_target') = 'number'
                    THEN (elem - 'description') || '{"minmax_manual": true}'::jsonb
                    ELSE elem - 'description'
                END
                ORDER BY ord
            ),
            '[]'::jsonb
        )::json
        FROM jsonb_array_elements("values"::jsonb) WITH ORDINALITY AS t(elem, ord)
    )
    WHERE "values"::text <> '[]'
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("target_categories", sa.Column("comment", sa.Text(), server_default="", nullable=False))
    op.add_column("target_categories", sa.Column("source_url", sa.Text(), server_default="", nullable=False))
    op.drop_column("target_categories", "description")
    op.execute(REWRITE_TARGET_VALUES)


def downgrade() -> None:
    """Downgrade schema."""
    # server_default so the NOT NULL column can be added against existing rows.
    # The values JSON needs no downgrade: the old dataclass declares
    # description: str = "", so a missing key simply takes the default.
    op.add_column(
        "target_categories",
        sa.Column("description", sa.TEXT(), server_default="", autoincrement=False, nullable=False),
    )
    op.drop_column("target_categories", "source_url")
    op.drop_column("target_categories", "comment")
