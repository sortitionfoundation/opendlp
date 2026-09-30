"""ABOUTME: Tests the data migration that deletes age range derived fields stored in the old shape.
ABOUTME: Seeds fields, targets and respondents through the repositories, then runs the migration's SQL."""

import importlib
import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    DerivationType,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

migration = importlib.import_module("migrations.versions.25c6dc66e011_delete_age_range_derived_fields")

OLD_AGE_CONFIG = {"as_of_date": "2026-05-13", "min_age": 16, "max_age": 100, "boundaries": [30], "fallback": "UNKNOWN"}


def _field(assembly_id: uuid.UUID, field_key: str, **kwargs) -> RespondentFieldDefinition:
    return RespondentFieldDefinition(
        assembly_id=assembly_id,
        field_key=field_key,
        label=field_key,
        group=kwargs.pop("group", RespondentFieldGroup.ABOUT_YOU),
        sort_order=10,
        **kwargs,
    )


def _age_field(assembly_id: uuid.UUID, target_category_id: uuid.UUID | None = None) -> RespondentFieldDefinition:
    return _field(
        assembly_id,
        "Age",
        group=RespondentFieldGroup.DERIVED,
        is_derived=True,
        derived_from=["year_of_birth"],
        derivation_type=DerivationType.AGE_BRACKET,
        derivation_config=OLD_AGE_CONFIG,
        field_type=FieldType.CHOICE_RADIO,
        options=[ChoiceOption(value="16-29"), ChoiceOption(value="30-99"), ChoiceOption(value="UNKNOWN")],
        target_category_id=target_category_id,
    )


@pytest.fixture
def seeded(postgres_session_factory):
    """Two assemblies: one with an age range field feeding its target, one with a small mapping only."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        aged = Assembly(title="Aged", question="?", number_to_select=10)
        other = Assembly(title="Other", question="?", number_to_select=10)
        uow.assemblies.add(aged)
        uow.assemblies.add(other)
        category = TargetCategory(assembly_id=aged.id, name="Age", values=[TargetValue(value="16-29", min=1, max=5)])
        uow.target_categories.add(category)
        aged_id, other_id, category_id = aged.id, other.id, category.id
        uow.commit()
    # Without ORM relationships a flush doesn't order rows by their foreign keys,
    # so the target is committed before the field that points at it.
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.respondent_field_definitions.add(_field(aged_id, "year_of_birth", field_type=FieldType.INTEGER))
        uow.respondent_field_definitions.add(_age_field(aged_id, target_category_id=category_id))
        uow.respondent_field_definitions.add(_field(other_id, "Age", field_type=FieldType.TEXT))
        uow.respondent_field_definitions.add(
            _field(
                other_id,
                "Region",
                group=RespondentFieldGroup.DERIVED,
                is_derived=True,
                derived_from=["Age"],
                derivation_type=DerivationType.SMALL_MAPPING,
                derivation_config={"mapping": {"a": "North"}, "fallback": "UNKNOWN"},
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="North"), ChoiceOption(value="UNKNOWN")],
            )
        )
        uow.respondents.add(
            Respondent(
                assembly_id=aged_id, external_id="A1", attributes={"year_of_birth": "1990", "Age": "30-99", "name": "x"}
            )
        )
        uow.respondents.add(
            Respondent(assembly_id=other_id, external_id="O1", attributes={"Age": "42", "Region": "North"})
        )
        uow.commit()
    return {"aged": aged_id, "other": other_id, "category": category_id}


def _run_migration(session_factory) -> None:
    session = session_factory()
    try:
        for statement in (
            migration.REMOVE_AGE_RANGE_VALUES,
            migration.DELETE_AGE_RANGE_MAPPING_ENTRIES,
            migration.DELETE_AGE_RANGE_FIELDS,
        ):
            session.execute(statement)
        session.commit()
    finally:
        session.close()


class TestDeleteAgeRangeFields:
    def test_the_age_range_field_and_its_values_go(self, postgres_session_factory, seeded):
        _run_migration(postgres_session_factory)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            keys = [f.field_key for f in uow.respondent_field_definitions.list_by_assembly(seeded["aged"])]
            respondent = uow.respondents.get_by_external_id(seeded["aged"], "A1")
            assert keys == ["year_of_birth"]
            assert respondent.attributes == {"year_of_birth": "1990", "name": "x"}

    def test_the_source_question_and_the_target_survive(self, postgres_session_factory, seeded):
        """The target is left not set up, and its source can be reused to set it up again."""
        _run_migration(postgres_session_factory)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            category = uow.target_categories.get(seeded["category"])
            source = uow.respondent_field_definitions.get_by_assembly_and_key(seeded["aged"], "year_of_birth")
            assert category is not None
            assert [value.value for value in category.values] == ["16-29"]
            assert source is not None
            assert source.target_category_id is None

    def test_other_fields_and_same_named_values_elsewhere_are_untouched(self, postgres_session_factory, seeded):
        """Only the assembly holding the age range field loses its value; another assembly's "Age" stays."""
        _run_migration(postgres_session_factory)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            keys = sorted(f.field_key for f in uow.respondent_field_definitions.list_by_assembly(seeded["other"]))
            respondent = uow.respondents.get_by_external_id(seeded["other"], "O1")
            assert keys == ["Age", "Region"]
            assert respondent.attributes == {"Age": "42", "Region": "North"}

    def test_running_it_twice_changes_nothing_more(self, postgres_session_factory, seeded):
        _run_migration(postgres_session_factory)
        _run_migration(postgres_session_factory)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = uow.respondents.get_by_external_id(seeded["aged"], "A1")
            assert respondent.attributes == {"year_of_birth": "1990", "name": "x"}
