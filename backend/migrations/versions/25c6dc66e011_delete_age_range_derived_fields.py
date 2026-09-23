"""delete age range derived fields

Revision ID: 25c6dc66e011
Revises: 0ce1cabd7ebe
Create Date: 2026-09-23 18:48:49.432024

An age range derived field now stores one "from" age per target value
instead of a minimum, maximum and boundaries, and the old shape is not read.
Only demo assemblies ever held one, so rather than convert them this deletes
each such field and the value it wrote on every respondent - what unlinking a
derived field does. The target it fed shows as not set up, and its source
question (date or year of birth) stays, answers included, ready to reuse.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "25c6dc66e011"
down_revision: str | Sequence[str] | None = "0ce1cabd7ebe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The values each age range field wrote on its assembly's respondents.
REMOVE_AGE_RANGE_VALUES = sa.text(
    """
    UPDATE respondents SET attributes = (
        SELECT coalesce(json_object_agg(e.key, e.value ORDER BY e.ord), '{}'::json)
        FROM json_each(respondents.attributes) WITH ORDINALITY AS e(key, value, ord)
        WHERE e.key NOT IN (
            SELECT f.field_key FROM respondent_field_definitions AS f
            WHERE f.assembly_id = respondents.assembly_id AND f.derivation_type = 'age_bracket'
        )
    )
    WHERE EXISTS (
        SELECT 1 FROM respondent_field_definitions AS f
        WHERE f.assembly_id = respondents.assembly_id
          AND f.derivation_type = 'age_bracket'
          AND respondents.attributes -> f.field_key IS NOT NULL
    )
    """
)

DELETE_AGE_RANGE_MAPPING_ENTRIES = sa.text(
    """
    DELETE FROM respondent_field_mapping_entries
    WHERE field_id IN (SELECT id FROM respondent_field_definitions WHERE derivation_type = 'age_bracket')
    """
)

DELETE_AGE_RANGE_FIELDS = sa.text("DELETE FROM respondent_field_definitions WHERE derivation_type = 'age_bracket'")


def upgrade() -> None:
    """Delete every age range derived field, its lookup rows and the values it wrote."""
    op.execute(REMOVE_AGE_RANGE_VALUES)
    op.execute(DELETE_AGE_RANGE_MAPPING_ENTRIES)
    op.execute(DELETE_AGE_RANGE_FIELDS)


def downgrade() -> None:
    """Irreversible data migration: the deleted configurations are not recorded, and
    the code this downgrades to could not read the new shape anyway. Set the targets
    up again instead."""
