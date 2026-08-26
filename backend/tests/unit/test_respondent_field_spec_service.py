"""ABOUTME: Unit tests for the respondent field spec builder
ABOUTME: Covers the CSV column layout, the exact target-category join, and permission enforcement"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.exceptions import AssemblyNotFoundError, InsufficientPermissions
from opendlp.service_layer.respondent_field_spec_service import SPEC_VERSION, build_field_spec
from tests.fakes import FakeUnitOfWork


def _seed(uow: FakeUnitOfWork, *, global_role: GlobalRole = GlobalRole.ADMIN) -> tuple[User, Assembly]:
    user = User(email="admin@example.com", global_role=global_role, password_hash="hash")
    uow.users.add(user)
    assembly = Assembly(title="Test Assembly", number_to_select=40)
    uow.assemblies.add(assembly)
    return user, assembly


def _add_field(uow: FakeUnitOfWork, assembly: Assembly, field_key: str, **kwargs) -> RespondentFieldDefinition:
    field = RespondentFieldDefinition(
        assembly_id=assembly.id,
        field_key=field_key,
        label=kwargs.pop("label", field_key.replace("_", " ").capitalize()),
        group=kwargs.pop("group", RespondentFieldGroup.ABOUT_YOU),
        sort_order=kwargs.pop("sort_order", 10),
        **kwargs,
    )
    uow.respondent_field_definitions.add(field)
    return field


def _add_category(uow: FakeUnitOfWork, assembly: Assembly, name: str, values: list[str]) -> TargetCategory:
    category = TargetCategory(
        assembly_id=assembly.id,
        name=name,
        values=[TargetValue(value=value, min=1, max=5) for value in values],
    )
    uow.target_categories.add(category)
    return category


def _field_by_key(spec: dict, field_key: str) -> dict:
    return next(f for f in spec["fields"] if f["field_key"] == field_key)


class TestSpecEnvelope:
    def test_reports_the_spec_version_and_assembly(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)

            spec = build_field_spec(uow, user.id, assembly.id)

        assert spec["spec_version"] == SPEC_VERSION
        assert spec["assembly"] == {
            "id": str(assembly.id),
            "title": "Test Assembly",
            "number_to_select": 40,
        }

    def test_empty_schema_yields_no_fields_and_just_the_id_column(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)

            spec = build_field_spec(uow, user.id, assembly.id)

        assert spec["fields"] == []
        assert spec["csv"]["columns"] == ["external_id"]

    def test_missing_assembly_raises(self):
        with FakeUnitOfWork() as uow:
            user, _assembly = _seed(uow)

            with pytest.raises(AssemblyNotFoundError):
                build_field_spec(uow, user.id, uuid.uuid4())

    def test_user_without_access_is_refused(self):
        with FakeUnitOfWork() as uow:
            _admin, assembly = _seed(uow)
            outsider = User(email="nobody@example.com", global_role=GlobalRole.USER, password_hash="hash")
            uow.users.add(outsider)

            with pytest.raises(InsufficientPermissions):
                build_field_spec(uow, outsider.id, assembly.id)


class TestCsvColumns:
    def test_columns_are_the_id_column_then_the_field_keys(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            _add_field(uow, assembly, "email", group=RespondentFieldGroup.NAME_AND_CONTACT, sort_order=0)
            _add_field(uow, assembly, "gender", sort_order=10)
            _add_field(uow, assembly, "age_bracket", sort_order=20)

            spec = build_field_spec(uow, user.id, assembly.id)

        assert spec["csv"]["id_column"] == "external_id"
        assert spec["csv"]["columns"] == ["external_id", "email", "gender", "age_bracket"]

    def test_id_column_follows_the_assembly_csv_config(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            assembly.csv = AssemblyCSV(assembly_id=assembly.id, csv_id_column="nationbuilder_id")
            _add_field(uow, assembly, "gender")

            spec = build_field_spec(uow, user.id, assembly.id)

        assert spec["csv"]["id_column"] == "nationbuilder_id"
        assert spec["csv"]["columns"] == ["nationbuilder_id", "gender"]

    def test_derived_fields_are_described_but_are_not_columns_to_write(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            _add_field(uow, assembly, "postcode", group=RespondentFieldGroup.ADDRESS, sort_order=10)
            _add_field(
                uow,
                assembly,
                "region",
                group=RespondentFieldGroup.ADDRESS,
                sort_order=20,
                is_derived=True,
                derived_from=["postcode"],
                derivation_kind="postcode_lookup",
            )

            spec = build_field_spec(uow, user.id, assembly.id)

        assert "region" not in spec["csv"]["columns"]
        region = _field_by_key(spec, "region")
        assert region["is_derived"] is True
        assert region["derived_from"] == ["postcode"]
        assert region["derivation_kind"] == "postcode_lookup"
        # A derived field is never collected, so it is never on the form either.
        assert region["on_registration_page"] == FieldOnRegistrationPage.NO.value

    def test_a_field_named_like_the_id_column_is_not_emitted_twice(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            _add_field(uow, assembly, "external_id", sort_order=10)
            _add_field(uow, assembly, "gender", sort_order=20)

            spec = build_field_spec(uow, user.id, assembly.id)

        assert spec["csv"]["columns"] == ["external_id", "gender"]

    def test_internal_export_columns_are_listed_as_ignored(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)

            spec = build_field_spec(uow, user.id, assembly.id)

        ignored = spec["csv"]["internal_columns_ignored_on_import"]
        assert "selection_status" in ignored
        assert "created_at" in ignored
        # They are not columns a generator should write.
        assert not set(ignored) & set(spec["csv"]["columns"])


class TestFieldPayload:
    def test_choice_options_are_the_valid_values(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            _add_field(
                uow,
                assembly,
                "gender",
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="Male"), ChoiceOption(value="Female", help_text="Includes trans women")],
            )

            spec = build_field_spec(uow, user.id, assembly.id)

        gender = _field_by_key(spec, "gender")
        assert gender["field_type"] == "choice_radio"
        assert gender["options"] == [
            {"value": "Male", "help_text": ""},
            {"value": "Female", "help_text": "Includes trans women"},
        ]

    def test_non_choice_fields_have_null_options(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            _add_field(uow, assembly, "notes", field_type=FieldType.LONGTEXT)

            spec = build_field_spec(uow, user.id, assembly.id)

        assert _field_by_key(spec, "notes")["options"] is None

    def test_fixed_fields_report_their_effective_type_not_the_stored_one(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            # A fixed row is seeded with the default TEXT type; FIXED_FIELD_TYPES
            # is what the app actually honours, so that is what the spec reports.
            _add_field(
                uow,
                assembly,
                "consent",
                group=RespondentFieldGroup.CONSENT,
                is_fixed=True,
                field_type=FieldType.TEXT,
            )

            spec = build_field_spec(uow, user.id, assembly.id)

        consent = _field_by_key(spec, "consent")
        assert consent["is_fixed"] is True
        assert consent["field_type"] == FieldType.BOOL_OR_NONE.value

    def test_registration_page_setting_is_reported(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            _add_field(uow, assembly, "gender", on_registration_page=FieldOnRegistrationPage.YES_OPTIONAL)

            spec = build_field_spec(uow, user.id, assembly.id)

        assert _field_by_key(spec, "gender")["on_registration_page"] == "yes_optional"


class TestTargetJoin:
    def test_target_values_are_attached_to_the_matching_field(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            _add_field(uow, assembly, "age_bracket")
            _add_category(uow, assembly, "age_bracket", ["16-29", "30-44"])

            spec = build_field_spec(uow, user.id, assembly.id)

        age = _field_by_key(spec, "age_bracket")
        assert [v["value"] for v in age["target_values"]] == ["16-29", "30-44"]
        assert age["target_values"][0]["min"] == 1
        assert age["target_values"][0]["max"] == 5
        # -1 is the library's "unset" sentinel, so it calculates a safe default.
        assert age["target_values"][0]["max_flex"] == -1
        assert spec["unmatched_target_categories"] == []

    def test_target_values_are_attached_to_the_matching_field_case_insensitive(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            _add_field(uow, assembly, "age_bracket")
            _add_category(uow, assembly, "Age_Bracket", ["16-29", "30-44"])

            spec = build_field_spec(uow, user.id, assembly.id)

        age = _field_by_key(spec, "age_bracket")
        assert [v["value"] for v in age["target_values"]] == ["16-29", "30-44"]
        assert age["target_values"][0]["min"] == 1
        assert age["target_values"][0]["max"] == 5
        # -1 is the library's "unset" sentinel, so it calculates a safe default.
        assert age["target_values"][0]["max_flex"] == -1
        assert spec["unmatched_target_categories"] == []

    def test_a_field_with_no_category_has_null_target_values(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            _add_field(uow, assembly, "first_name", group=RespondentFieldGroup.NAME_AND_CONTACT)

            spec = build_field_spec(uow, user.id, assembly.id)

        assert _field_by_key(spec, "first_name")["target_values"] is None

    def test_a_category_matching_no_field_is_reported_separately(self):
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            _add_field(uow, assembly, "gender")
            _add_category(uow, assembly, "education", ["School", "Degree"])

            spec = build_field_spec(uow, user.id, assembly.id)

        assert _field_by_key(spec, "gender")["target_values"] is None
        assert [c["name"] for c in spec["unmatched_target_categories"]] == ["education"]
        assert [v["value"] for v in spec["unmatched_target_categories"][0]["values"]] == ["School", "Degree"]

    def test_the_join_is_exact_because_selection_matches_exactly(self):
        """``Age Bracket`` and ``age_bracket`` normalise alike but select nothing.

        The heuristics that bucket a new column into a group match target names
        loosely; sortition-algorithms does not. A loose match here would report a
        category as wired up when selection would fail to find its column.

        (Although ``Age_Bracket`` and ``age_bracket`` do match - as sortition-algorithms does
        case-insensitive matching of field names.)
        """
        with FakeUnitOfWork() as uow:
            user, assembly = _seed(uow)
            _add_field(uow, assembly, "age_bracket")
            _add_category(uow, assembly, "Age Bracket", ["16-29"])

            spec = build_field_spec(uow, user.id, assembly.id)

        assert _field_by_key(spec, "age_bracket")["target_values"] is None
        assert [c["name"] for c in spec["unmatched_target_categories"]] == ["Age Bracket"]
