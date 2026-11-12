"""ABOUTME: Contract tests for RespondentFieldDefinitionRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    DerivationType,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
)

if TYPE_CHECKING:
    from tests.contract.conftest import ContractBackend


def _make_field(
    backend: ContractBackend,
    assembly_id: uuid.UUID,
    field_key: str = "",
    label: str = "",
    sort_order: int = 10,
    is_fixed: bool = False,
) -> RespondentFieldDefinition:
    if not field_key:
        field_key = f"attr_{uuid.uuid4().hex[:6]}"
    if not label:
        label = field_key.replace("_", " ").capitalize()
    field = RespondentFieldDefinition(
        assembly_id=assembly_id,
        field_key=field_key,
        label=label,
        sort_order=sort_order,
        is_fixed=is_fixed,
    )
    backend.repo.add(field)
    backend.commit()
    return field


class TestAddAndGet:
    def test_add_and_get_by_id(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        field = _make_field(
            respondent_field_definition_backend,
            assembly.id,
            field_key="gender",
            label="Gender",
        )

        retrieved = respondent_field_definition_backend.repo.get(field.id)
        assert retrieved is not None
        assert retrieved.id == field.id
        assert retrieved.field_key == "gender"
        assert retrieved.label == "Gender"

    def test_get_nonexistent_returns_none(self, respondent_field_definition_backend: ContractBackend) -> None:
        assert respondent_field_definition_backend.repo.get(uuid.uuid4()) is None

    def test_bulk_add(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        fields = [
            RespondentFieldDefinition(
                assembly_id=assembly.id,
                field_key=f"attr_{i}",
                label=f"Attr {i}",
                sort_order=i * 10,
            )
            for i in range(3)
        ]
        respondent_field_definition_backend.repo.bulk_add(fields)
        respondent_field_definition_backend.commit()

        assert respondent_field_definition_backend.repo.count_by_assembly_id(assembly.id) == 3


class TestGetByAssemblyAndKey:
    def test_returns_field_when_exists(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        _make_field(respondent_field_definition_backend, assembly.id, field_key="email")

        retrieved = respondent_field_definition_backend.repo.get_by_assembly_and_key(assembly.id, "email")
        assert retrieved is not None
        assert retrieved.field_key == "email"

    def test_returns_none_when_missing(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        assert respondent_field_definition_backend.repo.get_by_assembly_and_key(assembly.id, "ghost") is None

    def test_scopes_by_assembly(self, respondent_field_definition_backend: ContractBackend) -> None:
        a1 = respondent_field_definition_backend.make_assembly()
        a2 = respondent_field_definition_backend.make_assembly()
        _make_field(respondent_field_definition_backend, a1.id, field_key="email")

        assert respondent_field_definition_backend.repo.get_by_assembly_and_key(a2.id, "email") is None


class TestListByAssembly:
    def test_returns_empty_for_no_fields(self, respondent_field_definition_backend: ContractBackend) -> None:
        assert respondent_field_definition_backend.repo.list_by_assembly(uuid.uuid4()) == []

    def test_orders_by_sort_order(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        _make_field(
            respondent_field_definition_backend,
            assembly.id,
            field_key="custom",
            sort_order=10,
        )
        _make_field(
            respondent_field_definition_backend,
            assembly.id,
            field_key="first_name",
            sort_order=30,
        )
        _make_field(
            respondent_field_definition_backend,
            assembly.id,
            field_key="eligible",
            sort_order=20,
        )

        keys = [f.field_key for f in respondent_field_definition_backend.repo.list_by_assembly(assembly.id)]

        assert keys == ["custom", "eligible", "first_name"]

    def test_derived_fields_come_last(self, respondent_field_definition_backend: ContractBackend) -> None:
        """Computed columns stay at the end of the export, as they did in the Derived section."""
        assembly = respondent_field_definition_backend.make_assembly()
        derived = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="region",
            label="Region",
            sort_order=5,
            is_derived=True,
            derived_from=["postcode"],
            derivation_type=DerivationType.SMALL_MAPPING,
            derivation_config={"mapping": {}},
        )
        respondent_field_definition_backend.repo.add(derived)
        respondent_field_definition_backend.commit()
        _make_field(respondent_field_definition_backend, assembly.id, field_key="postcode", sort_order=10)

        keys = [f.field_key for f in respondent_field_definition_backend.repo.list_by_assembly(assembly.id)]

        assert keys == ["postcode", "region"]

    def test_scopes_by_assembly(self, respondent_field_definition_backend: ContractBackend) -> None:
        a1 = respondent_field_definition_backend.make_assembly()
        a2 = respondent_field_definition_backend.make_assembly()
        _make_field(respondent_field_definition_backend, a1.id, field_key="a1_only")
        _make_field(respondent_field_definition_backend, a2.id, field_key="a2_only")

        a1_fields = respondent_field_definition_backend.repo.list_by_assembly(a1.id)
        assert [f.field_key for f in a1_fields] == ["a1_only"]


class TestCountByAssemblyId:
    def test_counts_fields(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        _make_field(respondent_field_definition_backend, assembly.id, field_key="a")
        _make_field(respondent_field_definition_backend, assembly.id, field_key="b")

        assert respondent_field_definition_backend.repo.count_by_assembly_id(assembly.id) == 2

    def test_returns_zero_for_no_fields(self, respondent_field_definition_backend: ContractBackend) -> None:
        assert respondent_field_definition_backend.repo.count_by_assembly_id(uuid.uuid4()) == 0


class TestDelete:
    def test_delete_removes_field(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        field = _make_field(respondent_field_definition_backend, assembly.id, field_key="x")

        respondent_field_definition_backend.repo.delete(field)
        respondent_field_definition_backend.commit()

        assert respondent_field_definition_backend.repo.get(field.id) is None

    def test_delete_leaves_others(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        a = _make_field(respondent_field_definition_backend, assembly.id, field_key="a")
        b = _make_field(respondent_field_definition_backend, assembly.id, field_key="b")

        respondent_field_definition_backend.repo.delete(a)
        respondent_field_definition_backend.commit()

        assert respondent_field_definition_backend.repo.get(a.id) is None
        assert respondent_field_definition_backend.repo.get(b.id) is not None


class TestDeleteAllForAssembly:
    def test_deletes_all_for_assembly(self, respondent_field_definition_backend: ContractBackend) -> None:
        a1 = respondent_field_definition_backend.make_assembly()
        a2 = respondent_field_definition_backend.make_assembly()
        _make_field(respondent_field_definition_backend, a1.id, field_key="a1_1")
        _make_field(respondent_field_definition_backend, a1.id, field_key="a1_2")
        _make_field(respondent_field_definition_backend, a2.id, field_key="a2_1")

        count = respondent_field_definition_backend.repo.delete_all_for_assembly(a1.id)
        respondent_field_definition_backend.commit()

        assert count == 2
        assert respondent_field_definition_backend.repo.list_by_assembly(a1.id) == []
        assert len(respondent_field_definition_backend.repo.list_by_assembly(a2.id)) == 1

    def test_returns_zero_when_none_to_delete(self, respondent_field_definition_backend: ContractBackend) -> None:
        assert respondent_field_definition_backend.repo.delete_all_for_assembly(uuid.uuid4()) == 0


class TestFieldTypeAndOptions:
    def test_defaults_to_text_type_with_no_options(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        field = _make_field(respondent_field_definition_backend, assembly.id, field_key="freeform")

        retrieved = respondent_field_definition_backend.repo.get(field.id)
        assert retrieved is not None
        assert retrieved.field_type == FieldType.TEXT
        assert retrieved.options is None

    def test_round_trip_choice_options_with_help_text(
        self, respondent_field_definition_backend: ContractBackend
    ) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        field = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="education_level",
            label="Education level",
            sort_order=10,
            field_type=FieldType.CHOICE_RADIO,
            options=[
                ChoiceOption(value="level_0", help_text="None"),
                ChoiceOption(value="level_3", help_text="Post-secondary non-tertiary"),
            ],
        )
        respondent_field_definition_backend.repo.add(field)
        respondent_field_definition_backend.commit()

        retrieved = respondent_field_definition_backend.repo.get(field.id)
        assert retrieved is not None
        assert retrieved.field_type == FieldType.CHOICE_RADIO
        assert retrieved.options == [
            ChoiceOption(value="level_0", help_text="None"),
            ChoiceOption(value="level_3", help_text="Post-secondary non-tertiary"),
        ]


class TestHelpText:
    def test_defaults_to_an_empty_string(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        field = _make_field(respondent_field_definition_backend, assembly.id, field_key="freeform")

        retrieved = respondent_field_definition_backend.fresh_get_field_definition(field.id)
        assert retrieved is not None
        assert retrieved.help_text == ""

    def test_round_trips_the_field_help_text(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        field = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="gender",
            label="Gender",
            sort_order=10,
            help_text="As you describe yourself",
        )
        respondent_field_definition_backend.repo.add(field)
        respondent_field_definition_backend.commit()

        retrieved = respondent_field_definition_backend.fresh_get_field_definition(field.id)
        assert retrieved is not None
        assert retrieved.help_text == "As you describe yourself"


class TestDerivationColumns:
    def test_defaults_to_no_derivation(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        field = _make_field(respondent_field_definition_backend, assembly.id, field_key="freeform")

        retrieved = respondent_field_definition_backend.fresh_get_field_definition(field.id)
        assert retrieved is not None
        assert retrieved.is_derived is False
        assert retrieved.derived_from is None
        assert retrieved.derivation_type is None
        assert retrieved.derivation_config is None

    def test_round_trips_derivation_type_and_config(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        config = {"as_of_date": "2026-05-13", "brackets": [{"from_age": 16, "label": "16+"}], "fallback": "UNKNOWN"}
        field = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="age_bracket",
            label="Age bracket",
            sort_order=10,
            is_derived=True,
            derived_from=["date_of_birth"],
            derivation_type=DerivationType.AGE_BRACKET,
            derivation_config=config,
        )
        respondent_field_definition_backend.repo.add(field)
        respondent_field_definition_backend.commit()

        retrieved = respondent_field_definition_backend.fresh_get_field_definition(field.id)
        assert retrieved is not None
        assert retrieved.is_derived is True
        assert retrieved.derived_from == ["date_of_birth"]
        assert retrieved.derivation_type == DerivationType.AGE_BRACKET
        assert retrieved.derivation_config == config


class TestOnRegistrationPage:
    def test_defaults_to_yes_required(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        field = _make_field(respondent_field_definition_backend, assembly.id, field_key="freeform")

        retrieved = respondent_field_definition_backend.fresh_get_field_definition(field.id)
        assert retrieved is not None
        assert retrieved.on_registration_page == FieldOnRegistrationPage.YES_REQUIRED

    @pytest.mark.parametrize(
        "value",
        [
            FieldOnRegistrationPage.NO,
            FieldOnRegistrationPage.YES_OPTIONAL,
            FieldOnRegistrationPage.YES_REQUIRED,
        ],
    )
    def test_round_trips_each_value(
        self, respondent_field_definition_backend: ContractBackend, value: FieldOnRegistrationPage
    ) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        field = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="nickname",
            label="Nickname",
            sort_order=10,
            on_registration_page=value,
        )
        respondent_field_definition_backend.repo.add(field)
        respondent_field_definition_backend.commit()

        retrieved = respondent_field_definition_backend.fresh_get_field_definition(field.id)
        assert retrieved is not None
        assert retrieved.on_registration_page == value
