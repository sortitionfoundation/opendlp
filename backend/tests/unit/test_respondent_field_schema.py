"""Unit tests for the RespondentFieldDefinition domain entity."""

import uuid

import pytest

from opendlp.domain.respondent_field_schema import (
    BOOL_TYPES,
    CHOICE_TYPES,
    FIELD_TYPE_LABELS,
    FIXED_FIELD_TYPES,
    GROUP_DISPLAY_ORDER,
    GROUP_LABELS,
    IN_SCHEMA_FIXED_FIELDS,
    ChoiceOption,
    FieldType,
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


class TestFieldType:
    def test_field_type_enum_values(self) -> None:
        assert FieldType.TEXT.value == "text"
        assert FieldType.LONGTEXT.value == "longtext"
        assert FieldType.BOOL.value == "bool"
        assert FieldType.BOOL_OR_NONE.value == "bool_or_none"
        assert FieldType.CHOICE_RADIO.value == "choice_radio"
        assert FieldType.CHOICE_DROPDOWN.value == "choice_dropdown"
        assert FieldType.INTEGER.value == "integer"
        assert FieldType.EMAIL.value == "email"
        assert len(list(FieldType)) == 8

    def test_field_type_labels_cover_every_value(self) -> None:
        assert set(FIELD_TYPE_LABELS) == set(FieldType)

    def test_bool_types_and_choice_types_groupings(self) -> None:
        assert frozenset({FieldType.BOOL, FieldType.BOOL_OR_NONE}) == BOOL_TYPES
        assert frozenset({FieldType.CHOICE_RADIO, FieldType.CHOICE_DROPDOWN}) == CHOICE_TYPES

    def test_fixed_field_types_overrides(self) -> None:
        assert FIXED_FIELD_TYPES["email"] == FieldType.EMAIL
        assert FIXED_FIELD_TYPES["eligible"] == FieldType.BOOL_OR_NONE
        assert FIXED_FIELD_TYPES["can_attend"] == FieldType.BOOL_OR_NONE
        assert FIXED_FIELD_TYPES["consent"] == FieldType.BOOL_OR_NONE
        assert FIXED_FIELD_TYPES["stay_on_db"] == FieldType.BOOL_OR_NONE


class TestChoiceOption:
    def test_requires_non_blank_value(self) -> None:
        with pytest.raises(ValueError, match="value cannot be blank"):
            ChoiceOption(value="   ")

    def test_defaults_help_text_to_empty(self) -> None:
        opt = ChoiceOption(value="yes")
        assert opt.help_text == ""

    def test_to_dict_round_trip(self) -> None:
        original = ChoiceOption(value="level_3", help_text="Post-secondary non-tertiary")
        data = original.to_dict()
        assert data == {"value": "level_3", "help_text": "Post-secondary non-tertiary"}
        assert ChoiceOption.from_dict(data) == original

    def test_from_dict_defaults_help_text_when_missing(self) -> None:
        assert ChoiceOption.from_dict({"value": "a"}) == ChoiceOption(value="a")


class TestRespondentFieldDefinitionTyping:
    def _field(self, **overrides) -> RespondentFieldDefinition:
        base: dict = dict(
            assembly_id=uuid.uuid4(),
            field_key="x",
            label="X",
            group=RespondentFieldGroup.OTHER,
            sort_order=10,
        )
        base.update(overrides)
        return RespondentFieldDefinition(**base)

    def test_defaults_to_text_type(self) -> None:
        field = self._field()
        assert field.field_type == FieldType.TEXT
        assert field.options is None

    def test_rejects_choice_without_options(self) -> None:
        with pytest.raises(ValueError, match="options"):
            self._field(field_type=FieldType.CHOICE_RADIO)

    def test_rejects_options_on_non_choice_type(self) -> None:
        with pytest.raises(ValueError, match="options"):
            self._field(field_type=FieldType.TEXT, options=[ChoiceOption(value="a")])

    def test_accepts_choice_radio_with_options(self) -> None:
        field = self._field(
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="a"), ChoiceOption(value="b", help_text="second")],
        )
        assert field.field_type == FieldType.CHOICE_RADIO
        assert len(field.options or []) == 2

    def test_accepts_choice_dropdown_with_options(self) -> None:
        field = self._field(
            field_type=FieldType.CHOICE_DROPDOWN,
            options=[ChoiceOption(value="a"), ChoiceOption(value="b")],
        )
        assert field.field_type == FieldType.CHOICE_DROPDOWN

    def test_update_refuses_type_change_on_fixed_row(self) -> None:
        field = self._field(field_key="email", is_fixed=True)
        with pytest.raises(ValueError, match="fixed"):
            field.update(field_type=FieldType.TEXT)

    def test_update_changes_type_and_options_together_for_non_fixed_row(self) -> None:
        field = self._field()
        field.update(
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="a"), ChoiceOption(value="b")],
        )
        assert field.field_type == FieldType.CHOICE_RADIO
        assert field.options is not None
        assert [o.value for o in field.options] == ["a", "b"]

    def test_update_clears_options_when_switching_away_from_choice(self) -> None:
        field = self._field(
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="a")],
        )
        field.update(field_type=FieldType.TEXT, options=None)
        assert field.field_type == FieldType.TEXT
        assert field.options is None

    def test_update_auto_clears_options_when_switching_to_non_choice_without_explicit_none(self) -> None:
        field = self._field(
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="a")],
        )
        # Note: options argument NOT passed — default sentinel.
        field.update(field_type=FieldType.TEXT)
        assert field.field_type == FieldType.TEXT
        assert field.options is None

    def test_update_switches_between_choice_types_preserves_options(self) -> None:
        field = self._field(
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="a"), ChoiceOption(value="b")],
        )
        field.update(field_type=FieldType.CHOICE_DROPDOWN)
        assert field.field_type == FieldType.CHOICE_DROPDOWN
        assert field.options is not None
        assert [o.value for o in field.options] == ["a", "b"]

    def test_effective_field_type_uses_override_for_fixed_keys(self) -> None:
        field = self._field(field_key="email", is_fixed=True, field_type=FieldType.TEXT)
        assert field.effective_field_type == FieldType.EMAIL

    def test_effective_field_type_returns_own_type_for_non_fixed_keys(self) -> None:
        field = self._field(field_key="somefield", field_type=FieldType.INTEGER)
        assert field.effective_field_type == FieldType.INTEGER

    def test_create_detached_copy_preserves_field_type_and_options(self) -> None:
        original = self._field(
            field_type=FieldType.CHOICE_DROPDOWN,
            options=[ChoiceOption(value="a"), ChoiceOption(value="b", help_text="h")],
        )
        copy = original.create_detached_copy()
        assert copy.field_type == FieldType.CHOICE_DROPDOWN
        assert copy.options is not None
        assert copy.options == original.options
        assert copy.options is not original.options


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
