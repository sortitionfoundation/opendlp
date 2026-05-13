"""ABOUTME: Contract tests for RespondentFieldDefinitionRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid

from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from tests.contract.conftest import ContractBackend


def _make_field(
    backend: ContractBackend,
    assembly_id: uuid.UUID,
    field_key: str = "",
    label: str = "",
    group: RespondentFieldGroup = RespondentFieldGroup.OTHER,
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
        group=group,
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
            group=RespondentFieldGroup.ABOUT_YOU,
        )

        retrieved = respondent_field_definition_backend.repo.get(field.id)
        assert retrieved is not None
        assert retrieved.id == field.id
        assert retrieved.field_key == "gender"
        assert retrieved.label == "Gender"
        assert retrieved.group == RespondentFieldGroup.ABOUT_YOU

    def test_get_nonexistent_returns_none(self, respondent_field_definition_backend: ContractBackend) -> None:
        assert respondent_field_definition_backend.repo.get(uuid.uuid4()) is None

    def test_bulk_add(self, respondent_field_definition_backend: ContractBackend) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        fields = [
            RespondentFieldDefinition(
                assembly_id=assembly.id,
                field_key=f"attr_{i}",
                label=f"Attr {i}",
                group=RespondentFieldGroup.OTHER,
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

    def test_orders_by_group_display_order_then_sort_order(
        self, respondent_field_definition_backend: ContractBackend
    ) -> None:
        assembly = respondent_field_definition_backend.make_assembly()
        # Insert out of display order: OTHER first, then NAME_AND_CONTACT.
        _make_field(
            respondent_field_definition_backend,
            assembly.id,
            field_key="custom",
            group=RespondentFieldGroup.OTHER,
            sort_order=10,
        )
        _make_field(
            respondent_field_definition_backend,
            assembly.id,
            field_key="first_name",
            group=RespondentFieldGroup.NAME_AND_CONTACT,
            sort_order=20,
        )
        _make_field(
            respondent_field_definition_backend,
            assembly.id,
            field_key="email",
            group=RespondentFieldGroup.NAME_AND_CONTACT,
            sort_order=10,
        )
        _make_field(
            respondent_field_definition_backend,
            assembly.id,
            field_key="eligible",
            group=RespondentFieldGroup.ELIGIBILITY,
            sort_order=10,
        )

        fields = respondent_field_definition_backend.repo.list_by_assembly(assembly.id)
        keys = [f.field_key for f in fields]
        # ELIGIBILITY first, then NAME_AND_CONTACT (email before first_name by sort_order), then OTHER.
        assert keys == ["eligible", "email", "first_name", "custom"]

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
            group=RespondentFieldGroup.ABOUT_YOU,
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
