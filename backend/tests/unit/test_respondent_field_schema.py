"""Unit tests for the RespondentFieldDefinition domain entity."""

import uuid

import pytest

from opendlp.domain.respondent_field_schema import (
    GROUP_DISPLAY_ORDER,
    GROUP_LABELS,
    IN_SCHEMA_FIXED_FIELDS,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    humanise_field_key,
)


class TestRespondentFieldDefinition:
    def test_create_with_valid_data(self) -> None:
        assembly_id = uuid.uuid4()
        field = RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="first_name",
            label="First name",
            group=RespondentFieldGroup.NAME_AND_CONTACT,
            sort_order=10,
        )

        assert field.assembly_id == assembly_id
        assert field.field_key == "first_name"
        assert field.label == "First name"
        assert field.group == RespondentFieldGroup.NAME_AND_CONTACT
        assert field.sort_order == 10
        assert field.is_fixed is False
        assert field.is_derived is False
        assert field.derived_from is None
        assert field.derivation_kind == ""
        assert field.id is not None

    def test_field_key_is_stripped(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="  first_name  ",
            label="First name",
            group=RespondentFieldGroup.NAME_AND_CONTACT,
            sort_order=10,
        )
        assert field.field_key == "first_name"

    def test_rejects_empty_field_key(self) -> None:
        with pytest.raises(ValueError, match="field_key is required"):
            RespondentFieldDefinition(
                assembly_id=uuid.uuid4(),
                field_key="   ",
                label="whatever",
                group=RespondentFieldGroup.OTHER,
                sort_order=10,
            )

    def test_rejects_empty_label(self) -> None:
        with pytest.raises(ValueError, match="label is required"):
            RespondentFieldDefinition(
                assembly_id=uuid.uuid4(),
                field_key="x",
                label="",
                group=RespondentFieldGroup.OTHER,
                sort_order=10,
            )

    def test_rejects_negative_sort_order(self) -> None:
        with pytest.raises(ValueError, match="sort_order cannot be negative"):
            RespondentFieldDefinition(
                assembly_id=uuid.uuid4(),
                field_key="x",
                label="X",
                group=RespondentFieldGroup.OTHER,
                sort_order=-1,
            )

    def test_derived_requires_derived_from(self) -> None:
        with pytest.raises(ValueError, match="derived_from must be provided"):
            RespondentFieldDefinition(
                assembly_id=uuid.uuid4(),
                field_key="age_bracket",
                label="Age bracket",
                group=RespondentFieldGroup.ABOUT_YOU,
                sort_order=10,
                is_derived=True,
            )

    def test_derived_field_accepts_derived_from(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="age_bracket",
            label="Age bracket",
            group=RespondentFieldGroup.ABOUT_YOU,
            sort_order=10,
            is_derived=True,
            derived_from=["dob_day", "dob_month", "dob_year"],
            derivation_kind="age_bracket_from_dob",
        )
        assert field.is_derived is True
        assert field.derived_from == ["dob_day", "dob_month", "dob_year"]
        assert field.derivation_kind == "age_bracket_from_dob"

    def test_update_changes_label_and_touches_updated_at(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="x",
            label="X",
            group=RespondentFieldGroup.OTHER,
            sort_order=10,
        )
        original_updated_at = field.updated_at

        field.update(label="Xylophone")

        assert field.label == "Xylophone"
        assert field.updated_at > original_updated_at

    def test_update_moves_to_new_group(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="x",
            label="X",
            group=RespondentFieldGroup.OTHER,
            sort_order=10,
        )
        field.update(group=RespondentFieldGroup.ABOUT_YOU, sort_order=20)
        assert field.group == RespondentFieldGroup.ABOUT_YOU
        assert field.sort_order == 20

    def test_update_rejects_empty_label(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="x",
            label="X",
            group=RespondentFieldGroup.OTHER,
            sort_order=10,
        )
        with pytest.raises(ValueError, match="label cannot be empty"):
            field.update(label="   ")

    def test_equality_by_id(self) -> None:
        assembly_id = uuid.uuid4()
        field_id = uuid.uuid4()
        a = RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="x",
            label="X",
            group=RespondentFieldGroup.OTHER,
            sort_order=10,
            field_id=field_id,
        )
        b = RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key="y",
            label="Y",
            group=RespondentFieldGroup.OTHER,
            sort_order=20,
            field_id=field_id,
        )
        assert a == b
        assert hash(a) == hash(b)

    def test_create_detached_copy_preserves_identity_and_state(self) -> None:
        original = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="x",
            label="X",
            group=RespondentFieldGroup.ABOUT_YOU,
            sort_order=10,
            is_fixed=True,
            is_derived=True,
            derived_from=["a", "b"],
            derivation_kind="some_kind",
        )
        copy = original.create_detached_copy()

        assert copy.id == original.id
        assert copy.field_key == original.field_key
        assert copy.label == original.label
        assert copy.group == original.group
        assert copy.sort_order == original.sort_order
        assert copy.is_fixed is True
        assert copy.is_derived is True
        assert copy.derived_from == ["a", "b"]
        assert copy.derived_from is not original.derived_from  # actual copy
        assert copy.derivation_kind == "some_kind"


class TestGroupMetadata:
    def test_display_order_contains_every_group_exactly_once(self) -> None:
        assert set(GROUP_DISPLAY_ORDER) == set(RespondentFieldGroup)
        assert len(GROUP_DISPLAY_ORDER) == len(RespondentFieldGroup)

    def test_group_labels_cover_every_group(self) -> None:
        assert set(GROUP_LABELS) == set(RespondentFieldGroup)

    def test_in_schema_fixed_fields_have_unique_keys(self) -> None:
        keys = [key for key, _group, _label in IN_SCHEMA_FIXED_FIELDS]
        assert len(keys) == len(set(keys))


class TestHumaniseFieldKey:
    @pytest.mark.parametrize(
        ("field_key", "expected"),
        [
            ("first_name", "First name"),
            ("dob_day", "Dob day"),
            ("address-line-1", "Address line 1"),
            ("email", "Email"),
            ("NHS_number", "NHS number"),
            ("", ""),
        ],
    )
    def test_humanise(self, field_key: str, expected: str) -> None:
        assert humanise_field_key(field_key) == expected
