"""ABOUTME: Integration tests for the respondent field schema service.
ABOUTME: Covers populate, read, edit, reorder, delete, and initialise flows."""

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondent_field_schema import (
    IN_SCHEMA_FIXED_FIELDS,
    RespondentFieldGroup,
)
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import respondent_field_schema_service, respondent_service
from opendlp.service_layer.exceptions import InsufficientPermissions
from opendlp.service_layer.respondent_field_schema_service import (
    FieldDefinitionConflictError,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def uow(postgres_session_factory):
    return SqlAlchemyUnitOfWork(postgres_session_factory)


@pytest.fixture
def admin_user(uow):
    user = User(email="schema-admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    with uow:
        uow.users.add(user)
        detached = user.create_detached_copy()
        uow.commit()
        return detached


@pytest.fixture
def regular_user(uow):
    user = User(email="schema-user@test.com", global_role=GlobalRole.USER, password_hash="hash123")
    with uow:
        uow.users.add(user)
        detached = user.create_detached_copy()
        uow.commit()
        return detached


@pytest.fixture
def test_assembly(uow):
    assembly = Assembly(title="Schema Test Assembly", question="Test?", number_to_select=30)
    with uow:
        uow.assemblies.add(assembly)
        detached = assembly.create_detached_copy()
        uow.commit()
        return detached


FIXED_KEYS = [key for key, _group, _label in IN_SCHEMA_FIXED_FIELDS]


class TestCsvImportPopulatesSchema:
    def test_first_csv_import_seeds_schema(self, uow, admin_user, test_assembly):
        csv_content = (
            "external_id,first_name,last_name,gender,dob_year,postcode,region,custom_notes\n"
            "R001,Alice,Jones,Female,1990,SW1A 1AA,London,note1\n"
            "R002,Bob,Smith,Male,1985,E1 6AN,London,note2\n"
        )

        respondent_service.import_respondents_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        keys = [f.field_key for f in schema]

        # Fixed fields are all present
        for fixed_key in FIXED_KEYS:
            assert fixed_key in keys

        # CSV columns are present (other than the id column)
        assert "first_name" in keys
        assert "last_name" in keys
        assert "gender" in keys
        assert "dob_year" in keys
        assert "postcode" in keys
        assert "region" in keys
        assert "custom_notes" in keys
        # id column is NOT in the schema
        assert "external_id" not in keys

    def test_heuristics_bucket_fields_into_expected_groups(self, uow, admin_user, test_assembly):
        csv_content = (
            "external_id,first_name,last_name,email,gender,postcode,custom\nR001,Alice,Jones,alice@ex.com,F,SW1,foo\n"
        )

        respondent_service.import_respondents_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        grouped = respondent_field_schema_service.get_schema_grouped(uow, admin_user.id, test_assembly.id)
        by_key = {f.field_key: f.group for group_fields in grouped.values() for f in group_fields}

        assert by_key["first_name"] == RespondentFieldGroup.NAME_AND_CONTACT
        assert by_key["last_name"] == RespondentFieldGroup.NAME_AND_CONTACT
        # "email" is a fixed field, not a custom one; it shows as is_fixed with NAME_AND_CONTACT
        assert by_key["email"] == RespondentFieldGroup.NAME_AND_CONTACT
        assert by_key["gender"] == RespondentFieldGroup.ABOUT_YOU
        assert by_key["postcode"] == RespondentFieldGroup.ADDRESS
        assert by_key["custom"] == RespondentFieldGroup.OTHER

    def test_re_import_does_not_duplicate_schema(self, uow, admin_user, test_assembly):
        csv = "external_id,first_name\nR001,Alice\n"
        respondent_service.import_respondents_from_csv(uow, admin_user.id, test_assembly.id, csv, replace_existing=True)
        first_count = len(respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id))

        respondent_service.import_respondents_from_csv(uow, admin_user.id, test_assembly.id, csv, replace_existing=True)
        second_count = len(respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id))

        assert first_count == second_count


class TestInitialiseEmptySchema:
    def test_creates_fixed_rows_only(self, uow, admin_user, test_assembly):
        count = respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, test_assembly.id)

        assert count == len(IN_SCHEMA_FIXED_FIELDS)
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        keys = [f.field_key for f in schema]
        assert sorted(keys) == sorted(FIXED_KEYS)
        assert all(f.is_fixed for f in schema)

    def test_noop_when_schema_already_exists(self, uow, admin_user, test_assembly):
        respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, test_assembly.id)
        count = respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, test_assembly.id)
        assert count == 0


class TestUpdateField:
    def test_update_label_and_group(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,custom\nR001,val\n",
        )
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        custom_field = next(f for f in schema if f.field_key == "custom")

        updated = respondent_field_schema_service.update_field(
            uow,
            admin_user.id,
            test_assembly.id,
            custom_field.id,
            label="Custom notes",
            group=RespondentFieldGroup.ABOUT_YOU,
        )
        assert updated.label == "Custom notes"
        assert updated.group == RespondentFieldGroup.ABOUT_YOU


class TestReorderGroup:
    def test_reorders_within_group(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,a,b,c\nR001,1,2,3\n",
        )
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        other_fields = [f for f in schema if f.group == RespondentFieldGroup.OTHER]
        assert [f.field_key for f in other_fields] == ["a", "b", "c"]

        # Reverse the order.
        respondent_field_schema_service.reorder_group(
            uow,
            admin_user.id,
            test_assembly.id,
            RespondentFieldGroup.OTHER,
            [other_fields[2].id, other_fields[1].id, other_fields[0].id],
        )

        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        reordered = [f.field_key for f in schema if f.group == RespondentFieldGroup.OTHER]
        assert reordered == ["c", "b", "a"]


class TestDeleteField:
    def test_deletes_non_fixed_field(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,custom\nR001,v\n",
        )
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        custom_field = next(f for f in schema if f.field_key == "custom")

        respondent_field_schema_service.delete_field(uow, admin_user.id, test_assembly.id, custom_field.id)

        remaining = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        assert custom_field.id not in {f.id for f in remaining}

    def test_cannot_delete_fixed_field(self, uow, admin_user, test_assembly):
        respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, test_assembly.id)
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        fixed_field = next(f for f in schema if f.is_fixed)

        with pytest.raises(FieldDefinitionConflictError, match="cannot be deleted"):
            respondent_field_schema_service.delete_field(uow, admin_user.id, test_assembly.id, fixed_field.id)


class TestPermissions:
    def test_regular_user_cannot_edit(self, uow, admin_user, regular_user, test_assembly):
        respondent_field_schema_service.initialise_empty_schema(uow, admin_user.id, test_assembly.id)
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        field = schema[0]

        with pytest.raises(InsufficientPermissions):
            respondent_field_schema_service.update_field(
                uow, regular_user.id, test_assembly.id, field.id, label="Hacked"
            )
