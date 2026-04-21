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
from opendlp.service_layer.assembly_service import update_csv_config
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection
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


class TestReconciliation:
    def test_no_schema_yet_reports_all_keys_as_new(self, uow, admin_user, test_assembly):
        with uow:
            diff = respondent_field_schema_service.compute_reconciliation_diff(
                uow,
                test_assembly.id,
                ["external_id", "first_name", "gender"],
                "external_id",
            )
        assert diff.unchanged == []
        assert {k for k, _g in diff.new_keys} == {"first_name", "gender"}
        assert diff.absent_keys == []
        assert diff.has_changes is True

    def test_identical_headers_produce_empty_diff(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name,gender\nR001,Alice,F\n",
        )

        with uow:
            diff = respondent_field_schema_service.compute_reconciliation_diff(
                uow,
                test_assembly.id,
                ["external_id", "first_name", "gender"],
                "external_id",
            )

        assert set(diff.unchanged) == {"first_name", "gender"}
        assert diff.new_keys == []
        assert diff.absent_keys == []
        assert diff.has_changes is False

    def test_added_column_is_new(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name\nR001,Alice\n",
        )

        with uow:
            diff = respondent_field_schema_service.compute_reconciliation_diff(
                uow,
                test_assembly.id,
                ["external_id", "first_name", "postcode"],
                "external_id",
            )

        assert "first_name" in diff.unchanged
        new_keys = {k for k, _g in diff.new_keys}
        assert new_keys == {"postcode"}
        new_groups = dict(diff.new_keys)
        # postcode is recognised by the address heuristic.
        assert new_groups["postcode"] == RespondentFieldGroup.ADDRESS
        assert diff.absent_keys == []
        assert diff.has_changes is True

    def test_removed_column_is_absent(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name,gender,postcode\nR001,Alice,F,SW1A\n",
        )

        with uow:
            diff = respondent_field_schema_service.compute_reconciliation_diff(
                uow,
                test_assembly.id,
                ["external_id", "first_name", "gender"],
                "external_id",
            )

        assert diff.absent_keys == ["postcode"]
        assert diff.new_keys == []

    def test_id_column_change_is_flagged(self, uow, admin_user, test_assembly):
        with uow:
            diff = respondent_field_schema_service.compute_reconciliation_diff(
                uow,
                test_assembly.id,
                ["participant_id", "first_name"],
                "participant_id",
                previous_id_column="external_id",
            )
        assert diff.id_column_changed == ("external_id", "participant_id")
        assert diff.has_changes is True

    def test_apply_reconciliation_inserts_only_new_rows(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name\nR001,Alice\n",
        )
        before = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        before_keys = {f.field_key for f in before}

        with uow:
            diff = respondent_field_schema_service.compute_reconciliation_diff(
                uow,
                test_assembly.id,
                ["external_id", "first_name", "postcode", "favourite_colour"],
                "external_id",
            )
            inserted = respondent_field_schema_service.apply_reconciliation(uow, test_assembly.id, diff)
            uow.commit()

        assert inserted == 2
        after = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        after_keys = {f.field_key for f in after}
        assert after_keys == before_keys | {"postcode", "favourite_colour"}

    def test_re_upload_with_added_column_extends_existing_schema(self, uow, admin_user, test_assembly):
        # First import seeds the schema.
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name\nR001,Alice\n",
            replace_existing=True,
        )
        original = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        original_first_name = next(f for f in original if f.field_key == "first_name")

        # Re-upload with a new column should preserve the existing first_name row's id
        # (no replace-from-scratch), and add a row for the new column.
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name,city\nR001,Alice,London\n",
            replace_existing=True,
        )

        after = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        after_first_name = next(f for f in after if f.field_key == "first_name")
        assert after_first_name.id == original_first_name.id
        assert {f.field_key for f in after} >= {"first_name", "city"}

    def test_compute_diff_for_pending_csv_auto_detects_id_column(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name\nR001,Alice\n",
            replace_existing=True,
        )

        diff = respondent_field_schema_service.compute_diff_for_pending_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name,postcode\nR002,Bob,SW1\n",
            explicit_id_column=None,
        )
        assert diff is not None
        assert {k for k, _ in diff.new_keys} == {"postcode"}

    def test_compute_diff_for_pending_csv_flags_id_column_change(self, uow, admin_user, test_assembly):
        # Seed the schema and record the id column in AssemblyCSV (matching what
        # the upload route does after a successful import).
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name\nR001,Alice\n",
            replace_existing=True,
        )
        update_csv_config(
            uow,
            user_id=admin_user.id,
            assembly_id=test_assembly.id,
            csv_id_column="external_id",
        )

        diff = respondent_field_schema_service.compute_diff_for_pending_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "participant_id,first_name\nP001,Alice\n",
            explicit_id_column="participant_id",
        )
        assert diff is not None
        assert diff.id_column_changed == ("external_id", "participant_id")

    def test_compute_diff_for_pending_csv_returns_none_when_no_schema(self, uow, admin_user, test_assembly):
        diff = respondent_field_schema_service.compute_diff_for_pending_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name\nR001,Alice\n",
            explicit_id_column=None,
        )
        assert diff is None

    def test_compute_diff_for_pending_csv_rejects_empty_csv(self, uow, admin_user, test_assembly):
        with pytest.raises(InvalidSelection):
            respondent_field_schema_service.compute_diff_for_pending_csv(
                uow,
                admin_user.id,
                test_assembly.id,
                "",
                explicit_id_column=None,
            )

    def test_re_upload_with_removed_column_keeps_absent_row(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name,city\nR001,Alice,London\n",
            replace_existing=True,
        )
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,first_name\nR001,Alice\n",
            replace_existing=True,
        )

        after = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        # city's schema row is preserved even though no respondent now has data for it.
        assert "city" in {f.field_key for f in after}
