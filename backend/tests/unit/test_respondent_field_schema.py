"""Unit tests for the RespondentFieldDefinition domain entity."""

import uuid

import pytest

from opendlp.domain.respondent_field_schema import (
    BOOL_TYPES,
    CHOICE_TYPES,
    FIELD_TYPE_LABELS,
    FIXED_FIELD_ON_REGISTRATION_PAGE,
    FIXED_FIELD_TYPES,
    GROUP_DISPLAY_ORDER,
    GROUP_LABELS,
    IN_SCHEMA_FIXED_FIELDS,
    ChoiceOption,
    DerivationType,
    DerivedFieldError,
    FieldOnRegistrationPage,
    FieldType,
    FixedFieldError,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    RespondentFieldMappingEntry,
    humanise_field_key,
    normalise_field_key,
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
        assert field.derivation_type is None
        assert field.derivation_config is None
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
                group=RespondentFieldGroup.DERIVED,
                sort_order=10,
                is_derived=True,
                derivation_type=DerivationType.AGE_BRACKET,
                derivation_config={"as_of_date": "2026-05-13"},
            )

    def test_derived_requires_derivation_type(self) -> None:
        with pytest.raises(ValueError, match="derivation_type must be provided"):
            RespondentFieldDefinition(
                assembly_id=uuid.uuid4(),
                field_key="age_bracket",
                label="Age bracket",
                group=RespondentFieldGroup.DERIVED,
                sort_order=10,
                is_derived=True,
                derived_from=["date_of_birth"],
                derivation_config={"as_of_date": "2026-05-13"},
            )

    def test_derived_requires_derivation_config(self) -> None:
        with pytest.raises(ValueError, match="derivation_config must be provided"):
            RespondentFieldDefinition(
                assembly_id=uuid.uuid4(),
                field_key="age_bracket",
                label="Age bracket",
                group=RespondentFieldGroup.DERIVED,
                sort_order=10,
                is_derived=True,
                derived_from=["date_of_birth"],
                derivation_type=DerivationType.AGE_BRACKET,
            )

    def test_non_derived_rejects_derivation_type(self) -> None:
        with pytest.raises(ValueError, match="only allowed when is_derived"):
            RespondentFieldDefinition(
                assembly_id=uuid.uuid4(),
                field_key="postcode",
                label="Postcode",
                group=RespondentFieldGroup.ADDRESS,
                sort_order=10,
                derivation_type=DerivationType.LARGE_MAPPING,
            )

    def test_non_derived_rejects_derivation_config(self) -> None:
        with pytest.raises(ValueError, match="only allowed when is_derived"):
            RespondentFieldDefinition(
                assembly_id=uuid.uuid4(),
                field_key="postcode",
                label="Postcode",
                group=RespondentFieldGroup.ADDRESS,
                sort_order=10,
                derivation_config={"fallback": "UNKNOWN"},
            )

    def test_derived_field_accepts_full_derivation(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="age_bracket",
            label="Age bracket",
            group=RespondentFieldGroup.DERIVED,
            sort_order=10,
            is_derived=True,
            derived_from=["date_of_birth"],
            derivation_type=DerivationType.AGE_BRACKET,
            derivation_config={"as_of_date": "2026-05-13", "min_age": 16},
        )
        assert field.is_derived is True
        assert field.derived_from == ["date_of_birth"]
        assert field.derivation_type == DerivationType.AGE_BRACKET
        assert field.derivation_config == {"as_of_date": "2026-05-13", "min_age": 16}

    def test_update_rejects_type_and_options_on_derived_field(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="age_bracket",
            label="Age bracket",
            group=RespondentFieldGroup.DERIVED,
            sort_order=10,
            is_derived=True,
            derived_from=["date_of_birth"],
            derivation_type=DerivationType.AGE_BRACKET,
            derivation_config={"as_of_date": "2026-05-13"},
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="16-21"), ChoiceOption(value="UNKNOWN")],
        )
        with pytest.raises(DerivedFieldError):
            field.update(field_type=FieldType.TEXT)
        with pytest.raises(DerivedFieldError):
            field.update(options=[ChoiceOption(value="other")])

    def test_update_keeps_derived_field_off_the_registration_page(self) -> None:
        """update() must re-apply the is_derived => NO invariant the constructor sets."""
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="age_bracket",
            label="Age bracket",
            group=RespondentFieldGroup.DERIVED,
            sort_order=10,
            is_derived=True,
            derived_from=["date_of_birth"],
            derivation_type=DerivationType.AGE_BRACKET,
            derivation_config={"as_of_date": "2026-05-13"},
        )
        field.update(on_registration_page=FieldOnRegistrationPage.YES_REQUIRED)
        assert field.on_registration_page == FieldOnRegistrationPage.NO

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
            derivation_type=DerivationType.SMALL_MAPPING,
            derivation_config={"mapping": {"a": "b"}, "fallback": "UNKNOWN"},
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
        assert copy.derivation_type == DerivationType.SMALL_MAPPING
        assert copy.derivation_config == {"mapping": {"a": "b"}, "fallback": "UNKNOWN"}
        assert copy.derivation_config is not original.derivation_config  # actual copy


class TestDerivationType:
    def test_enum_values(self) -> None:
        assert DerivationType.AGE_BRACKET.value == "age_bracket"
        assert DerivationType.SMALL_MAPPING.value == "small_mapping"
        assert DerivationType.LARGE_MAPPING.value == "large_mapping"
        assert len(list(DerivationType)) == 3


class TestDerivedGroup:
    def test_derived_group_exists_and_sorts_last(self) -> None:
        assert RespondentFieldGroup.DERIVED.value == "derived"
        assert GROUP_DISPLAY_ORDER[-1] == RespondentFieldGroup.DERIVED
        assert GROUP_DISPLAY_ORDER.index(RespondentFieldGroup.DERIVED) > GROUP_DISPLAY_ORDER.index(
            RespondentFieldGroup.OTHER
        )

    def test_derived_group_has_label(self) -> None:
        assert str(GROUP_LABELS[RespondentFieldGroup.DERIVED]) == "Derived"

    def test_every_group_is_in_display_order_and_labels(self) -> None:
        assert set(GROUP_DISPLAY_ORDER) == set(RespondentFieldGroup)
        assert set(GROUP_LABELS) == set(RespondentFieldGroup)


class TestRespondentFieldMappingEntry:
    def test_create_with_valid_data(self) -> None:
        field_id = uuid.uuid4()
        entry = RespondentFieldMappingEntry(field_id=field_id, lookup_key="SW1A1AA", output_value="London")
        assert entry.field_id == field_id
        assert entry.lookup_key == "SW1A1AA"
        assert entry.output_value == "London"
        assert entry.id is not None

    def test_rejects_blank_lookup_key(self) -> None:
        with pytest.raises(ValueError, match="lookup_key is required"):
            RespondentFieldMappingEntry(field_id=uuid.uuid4(), lookup_key="  ", output_value="London")

    def test_rejects_blank_output_value(self) -> None:
        with pytest.raises(ValueError, match="output_value is required"):
            RespondentFieldMappingEntry(field_id=uuid.uuid4(), lookup_key="SW1A1AA", output_value="")

    def test_equality_by_id(self) -> None:
        entry_id = uuid.uuid4()
        a = RespondentFieldMappingEntry(field_id=uuid.uuid4(), lookup_key="A", output_value="X", entry_id=entry_id)
        b = RespondentFieldMappingEntry(field_id=uuid.uuid4(), lookup_key="B", output_value="Y", entry_id=entry_id)
        assert a == b
        assert hash(a) == hash(b)


class TestFieldOnRegistrationPage:
    def test_enum_values(self) -> None:
        assert FieldOnRegistrationPage.NO.value == "no"
        assert FieldOnRegistrationPage.YES_OPTIONAL.value == "yes_optional"
        assert FieldOnRegistrationPage.YES_REQUIRED.value == "yes_required"
        assert len(list(FieldOnRegistrationPage)) == 3

    def test_constructor_defaults_to_yes_required(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="first_name",
            label="First name",
            group=RespondentFieldGroup.NAME_AND_CONTACT,
            sort_order=10,
        )
        assert field.on_registration_page == FieldOnRegistrationPage.YES_REQUIRED

    def test_constructor_accepts_explicit_value(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="nickname",
            label="Nickname",
            group=RespondentFieldGroup.OTHER,
            sort_order=10,
            on_registration_page=FieldOnRegistrationPage.YES_OPTIONAL,
        )
        assert field.on_registration_page == FieldOnRegistrationPage.YES_OPTIONAL

    def test_derived_field_is_forced_to_no(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="age_bracket",
            label="Age bracket",
            group=RespondentFieldGroup.ABOUT_YOU,
            sort_order=10,
            is_derived=True,
            derived_from=["dob"],
            derivation_type=DerivationType.AGE_BRACKET,
            derivation_config={"as_of_date": "2026-05-13"},
            on_registration_page=FieldOnRegistrationPage.YES_REQUIRED,
        )
        assert field.on_registration_page == FieldOnRegistrationPage.NO

    def test_update_changes_on_registration_page(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="x",
            label="X",
            group=RespondentFieldGroup.OTHER,
            sort_order=10,
        )
        original_updated_at = field.updated_at
        field.update(on_registration_page=FieldOnRegistrationPage.NO)
        assert field.on_registration_page == FieldOnRegistrationPage.NO
        assert field.updated_at > original_updated_at

    def test_update_changes_on_registration_page_for_fixed_field(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="can_attend",
            label="Can attend",
            group=RespondentFieldGroup.ELIGIBILITY,
            sort_order=10,
            is_fixed=True,
        )
        field.update(on_registration_page=FieldOnRegistrationPage.NO)
        assert field.on_registration_page == FieldOnRegistrationPage.NO

    def test_update_leaves_on_registration_page_unchanged_when_omitted(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="x",
            label="X",
            group=RespondentFieldGroup.OTHER,
            sort_order=10,
            on_registration_page=FieldOnRegistrationPage.YES_OPTIONAL,
        )
        field.update(label="Xylophone")
        assert field.on_registration_page == FieldOnRegistrationPage.YES_OPTIONAL

    def test_create_detached_copy_preserves_on_registration_page(self) -> None:
        original = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="x",
            label="X",
            group=RespondentFieldGroup.OTHER,
            sort_order=10,
            on_registration_page=FieldOnRegistrationPage.YES_OPTIONAL,
        )
        copy = original.create_detached_copy()
        assert copy.on_registration_page == FieldOnRegistrationPage.YES_OPTIONAL

    def test_fixed_field_seed_defaults(self) -> None:
        assert FIXED_FIELD_ON_REGISTRATION_PAGE["email"] == FieldOnRegistrationPage.YES_REQUIRED
        assert FIXED_FIELD_ON_REGISTRATION_PAGE["eligible"] == FieldOnRegistrationPage.YES_REQUIRED
        assert FIXED_FIELD_ON_REGISTRATION_PAGE["can_attend"] == FieldOnRegistrationPage.YES_REQUIRED
        assert FIXED_FIELD_ON_REGISTRATION_PAGE["consent"] == FieldOnRegistrationPage.YES_REQUIRED
        assert FIXED_FIELD_ON_REGISTRATION_PAGE["stay_on_db"] == FieldOnRegistrationPage.YES_OPTIONAL


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
        assert FieldType.DATE.value == "date"
        assert len(list(FieldType)) == 9

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
        # FixedFieldError is a ValueError subclass, but the distinct type lets the
        # service layer translate the message without matching on its text.
        with pytest.raises(FixedFieldError):
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


class TestNormaliseFieldKey:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("age_range", "age_range"),
            ("Age Range", "age_range"),
            ("  Favourite Colour  ", "favourite_colour"),
            ("address-line-1", "address_line_1"),
            ("First   name", "first_name"),
            ("Gender (self-described)", "gender_self_described"),
            ("naïve", "nave"),
            ("__weird__key__", "weird_key"),
            ("!!!", ""),
            ("", ""),
        ],
    )
    def test_normalise(self, raw: str, expected: str) -> None:
        assert normalise_field_key(raw) == expected


class TestSetDerivation:
    def _derived_field(self) -> RespondentFieldDefinition:
        return RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="age_bracket",
            label="Age bracket",
            group=RespondentFieldGroup.DERIVED,
            sort_order=10,
            is_derived=True,
            derived_from=["date_of_birth"],
            derivation_type=DerivationType.AGE_BRACKET,
            derivation_config={"as_of_date": "2026-05-13"},
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="16-99"), ChoiceOption(value="UNKNOWN")],
        )

    def test_replaces_type_config_and_options(self) -> None:
        field = self._derived_field()
        field.set_derivation(
            derivation_type=DerivationType.AGE_BRACKET,
            derivation_config={"as_of_date": "2027-01-01", "min_age": 18},
            options=[ChoiceOption(value="under-18"), ChoiceOption(value="18-99"), ChoiceOption(value="UNKNOWN")],
        )
        assert field.derivation_config == {"as_of_date": "2027-01-01", "min_age": 18}
        assert [o.value for o in field.options] == ["under-18", "18-99", "UNKNOWN"]

    def test_rejects_non_derived_field(self) -> None:
        field = RespondentFieldDefinition(
            assembly_id=uuid.uuid4(),
            field_key="plain",
            label="Plain",
            group=RespondentFieldGroup.OTHER,
            sort_order=10,
        )
        with pytest.raises(DerivedFieldError):
            field.set_derivation(
                derivation_type=DerivationType.AGE_BRACKET,
                derivation_config={"as_of_date": "2026-05-13"},
                options=[ChoiceOption(value="x")],
            )

    def test_rejects_empty_options(self) -> None:
        field = self._derived_field()
        with pytest.raises(ValueError):
            field.set_derivation(
                derivation_type=DerivationType.AGE_BRACKET,
                derivation_config={"as_of_date": "2026-05-13"},
                options=[],
            )
