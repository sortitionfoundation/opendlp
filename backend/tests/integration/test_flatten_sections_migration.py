"""ABOUTME: Tests the data migration that turns the fixed question sections into heading blocks.
ABOUTME: Seeds grouped fields through the repositories, then runs the migration's data step."""

import importlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_content_block import RegistrationContentBlock, form_items
from opendlp.domain.respondent_field_schema import (
    DerivationType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

migration = importlib.import_module("migrations.versions.4a7c0b3d443b_add_registration_content_blocks")

LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)


def _field(assembly_id: uuid.UUID, key: str, group: RespondentFieldGroup, sort_order: int, **kwargs):
    return RespondentFieldDefinition(
        assembly_id=assembly_id,
        field_key=key,
        label=key,
        group=group,
        sort_order=sort_order,
        created_at=LONG_AGO,
        updated_at=kwargs.pop("updated_at", LONG_AGO),
        **kwargs,
    )


@pytest.fixture
def seeded(postgres_session_factory):
    """One assembly with questions in three sections and a computed one; another with no questions."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        grouped = Assembly(title="Grouped", question="?", number_to_select=10)
        empty = Assembly(title="Empty", question="?", number_to_select=10)
        uow.assemblies.add(grouped)
        uow.assemblies.add(empty)
        uow.commit()
        grouped_id, empty_id = grouped.id, empty.id
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        add = uow.respondent_field_definitions.add
        # Sort orders restart in each section, as they did while sections existed.
        add(_field(grouped_id, "consent", RespondentFieldGroup.CONSENT, 10))
        add(_field(grouped_id, "first_name", RespondentFieldGroup.NAME_AND_CONTACT, 20))
        add(_field(grouped_id, "email", RespondentFieldGroup.NAME_AND_CONTACT, 10))
        add(
            _field(
                grouped_id,
                "eligible",
                RespondentFieldGroup.ELIGIBILITY,
                10,
                updated_at=LONG_AGO + timedelta(days=3),
            )
        )
        add(
            _field(
                grouped_id,
                "region",
                RespondentFieldGroup.DERIVED,
                10,
                is_derived=True,
                derived_from=["postcode"],
                derivation_type=DerivationType.SMALL_MAPPING,
                derivation_config={"mapping": {}},
                updated_at=LONG_AGO + timedelta(days=9),
            )
        )
        uow.commit()
    return {"grouped": grouped_id, "empty": empty_id}


def _run_migration(session_factory) -> None:
    session = session_factory()
    try:
        migration.flatten_sections(session.connection())
        session.commit()
    finally:
        session.close()


def _layout(session_factory, assembly_id: uuid.UUID) -> list[str]:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        fields = uow.respondent_field_definitions.list_by_assembly(assembly_id)
        blocks = uow.registration_content_blocks.list_by_assembly(assembly_id)
        return [
            f"# {item.heading}" if isinstance(item, RegistrationContentBlock) else item.field_key
            for item in form_items(fields, blocks)
        ]


class TestFlattenSections:
    def test_each_section_with_questions_becomes_a_heading_above_them(self, postgres_session_factory, seeded):
        _run_migration(postgres_session_factory)

        assert _layout(postgres_session_factory, seeded["grouped"]) == [
            "# Eligibility",
            "eligible",
            "# Name and contact",
            "email",
            "first_name",
            "# Consent",
            "consent",
        ]

    def test_sort_orders_become_one_sequence(self, postgres_session_factory, seeded):
        _run_migration(postgres_session_factory)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            fields = uow.respondent_field_definitions.list_by_assembly(seeded["grouped"])
            blocks = uow.registration_content_blocks.list_by_assembly(seeded["grouped"])
            orders = [item.sort_order for item in form_items(fields, blocks)]
        assert orders == [10, 20, 30, 40, 50, 60, 70]

    def test_a_computed_question_gets_no_heading(self, postgres_session_factory, seeded):
        """The Derived section was never on the questions step, so it leaves no heading behind."""
        _run_migration(postgres_session_factory)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            headings = [b.heading for b in uow.registration_content_blocks.list_by_assembly(seeded["grouped"])]
            region = uow.respondent_field_definitions.get_by_assembly_and_key(seeded["grouped"], "region")
            assert region is not None
            assert region.sort_order == 10
        assert "Derived" not in headings

    def test_an_assembly_without_questions_gets_no_headings(self, postgres_session_factory, seeded):
        _run_migration(postgres_session_factory)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.registration_content_blocks.list_by_assembly(seeded["empty"]) == []

    def test_questions_updated_at_is_the_latest_field_change(self, postgres_session_factory, seeded):
        """So a form saved after the questions last changed shows no warning once the headings appear."""
        _run_migration(postgres_session_factory)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            grouped = uow.assemblies.get(seeded["grouped"])
            empty = uow.assemblies.get(seeded["empty"])
            assert grouped.questions_updated_at == LONG_AGO + timedelta(days=9)
            assert empty.questions_updated_at is None

    def test_running_it_twice_adds_no_more_headings(self, postgres_session_factory, seeded):
        _run_migration(postgres_session_factory)
        _run_migration(postgres_session_factory)

        assert _layout(postgres_session_factory, seeded["grouped"]).count("# Consent") == 1
