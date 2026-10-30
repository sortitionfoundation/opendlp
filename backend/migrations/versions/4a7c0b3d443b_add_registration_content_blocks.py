"""add registration content blocks

Revision ID: 4a7c0b3d443b
Revises: a78dcf4c5649
Create Date: 2026-10-29 11:24:34.632200

Registration questions are no longer filed under six fixed sections. They are
one ordered list, and an organiser places headings and text in it wherever
they like. This adds the table for those headings and text, and turns each
section that holds a question into a heading above its questions, so every
existing project looks as it did. Sort orders, which restarted in each
section, become one sequence per assembly. Computed (derived) questions are
never on the list and keep their own order.

It also adds assemblies.questions_updated_at, which records when the questions
last changed, seeded from the newest question change so that no form shows a
"questions changed" warning it was not already showing.

The field_group column stays for now, so that a downgrade finds the sections
still there; a later migration drops it.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

import opendlp.adapters.orm

# revision identifiers, used by Alembic.
revision: str = "4a7c0b3d443b"
down_revision: str | Sequence[str] | None = "a78dcf4c5649"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SORT_ORDER_STEP = 10

# The sections in the order they were shown, with their English labels. Written
# as literals: from now on they are headings the organiser can edit, like a
# question's label. The derived section was never shown on the questions step.
SECTIONS = [
    ("eligibility", "Eligibility"),
    ("name_and_contact", "Name and contact"),
    ("address", "Address"),
    ("about_you", "About you"),
    ("consent", "Consent"),
    ("other", "Other"),
]

_ASSEMBLIES_TO_FLATTEN = sa.text(
    """
    SELECT DISTINCT f.assembly_id FROM respondent_field_definitions AS f
    WHERE NOT f.is_derived
      AND NOT EXISTS (SELECT 1 FROM registration_content_blocks AS b WHERE b.assembly_id = f.assembly_id)
    """
)

_QUESTIONS = sa.text(
    """
    SELECT id, field_group FROM respondent_field_definitions
    WHERE assembly_id = :assembly_id AND NOT is_derived
    ORDER BY sort_order, field_key
    """
)

_SET_SORT_ORDER = sa.text("UPDATE respondent_field_definitions SET sort_order = :sort_order WHERE id = :id")

_ADD_HEADING = sa.text(
    """
    INSERT INTO registration_content_blocks (id, assembly_id, sort_order, heading, body_html, created_at, updated_at)
    VALUES (:id, :assembly_id, :sort_order, :heading, '', :now, :now)
    """
)

_SEED_QUESTIONS_UPDATED_AT = sa.text(
    """
    UPDATE assemblies SET questions_updated_at = (
        SELECT max(f.updated_at) FROM respondent_field_definitions AS f WHERE f.assembly_id = assemblies.id
    )
    WHERE questions_updated_at IS NULL
      AND EXISTS (SELECT 1 FROM respondent_field_definitions AS f WHERE f.assembly_id = assemblies.id)
    """
)


def _flatten_assembly(connection: sa.Connection, assembly_id: uuid.UUID, now: datetime) -> None:
    questions_by_section: dict[str, list[uuid.UUID]] = {}
    for row in connection.execute(_QUESTIONS, {"assembly_id": assembly_id}):
        questions_by_section.setdefault(row.field_group, []).append(row.id)

    position = 0
    for section, heading in SECTIONS:
        question_ids = questions_by_section.pop(section, [])
        if not question_ids:
            continue
        position += SORT_ORDER_STEP
        connection.execute(
            _ADD_HEADING,
            {"id": uuid.uuid4(), "assembly_id": assembly_id, "sort_order": position, "heading": heading, "now": now},
        )
        for question_id in question_ids:
            position += SORT_ORDER_STEP
            connection.execute(_SET_SORT_ORDER, {"id": question_id, "sort_order": position})
    # A question left in a section no longer shown (none should be) goes last,
    # without a heading, rather than keep a number from the old per-section scale.
    for question_ids in questions_by_section.values():
        for question_id in question_ids:
            position += SORT_ORDER_STEP
            connection.execute(_SET_SORT_ORDER, {"id": question_id, "sort_order": position})


def flatten_sections(connection: sa.Connection) -> None:
    """Turn each section holding a question into a heading, and number the list as one.

    An assembly that already has a heading or text is skipped, so this is
    safe to run twice.
    """
    now = datetime.now(UTC)
    for row in connection.execute(_ASSEMBLIES_TO_FLATTEN).all():
        _flatten_assembly(connection, row.assembly_id, now)
    connection.execute(_SEED_QUESTIONS_UPDATED_AT)


def upgrade() -> None:
    """Add the headings and text table and questions_updated_at, then flatten the sections."""
    op.create_table(
        "registration_content_blocks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assembly_id", sa.UUID(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(length=255), server_default="", nullable=False),
        sa.Column("body_html", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", opendlp.adapters.orm.TZAwareDatetime(timezone=True), nullable=False),
        sa.Column("updated_at", opendlp.adapters.orm.TZAwareDatetime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assembly_id"], ["assemblies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_registration_content_blocks_assembly_id"),
        "registration_content_blocks",
        ["assembly_id"],
        unique=False,
    )
    op.add_column(
        "assemblies",
        sa.Column("questions_updated_at", opendlp.adapters.orm.TZAwareDatetime(timezone=True), nullable=True),
    )
    flatten_sections(op.get_bind())


def downgrade() -> None:
    """Drop the headings and text. Questions keep the one sequence, which still
    sorts correctly within each section, so the sections come back as they were."""
    op.drop_column("assemblies", "questions_updated_at")
    op.drop_index(op.f("ix_registration_content_blocks_assembly_id"), table_name="registration_content_blocks")
    op.drop_table("registration_content_blocks")
