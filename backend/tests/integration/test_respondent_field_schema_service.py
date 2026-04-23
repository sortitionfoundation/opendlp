"""ABOUTME: Integration tests for the respondent field schema service.
ABOUTME: Covers populate, read, edit, reorder, delete, and initialise flows."""

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondent_field_schema import (
    IN_SCHEMA_FIXED_FIELDS,
    ChoiceOption,
    FieldType,
    RespondentFieldGroup,
)
from opendlp.domain.targets import TargetCategory, TargetValue
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

    def _custom_field_id(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,gender\nR001,Female\n",
        )
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        return next(f for f in schema if f.field_key == "gender").id

    def test_update_field_accepts_field_type_and_options(self, uow, admin_user, test_assembly):
        field_id = self._custom_field_id(uow, admin_user, test_assembly)
        updated = respondent_field_schema_service.update_field(
            uow,
            admin_user.id,
            test_assembly.id,
            field_id,
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="Female"), ChoiceOption(value="Male")],
        )
        assert updated.field_type == FieldType.CHOICE_RADIO
        assert updated.options is not None
        assert [o.value for o in updated.options] == ["Female", "Male"]

    def test_update_field_refuses_type_change_on_fixed_row(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,foo\nR001,v\n",
        )
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        email_field = next(f for f in schema if f.field_key == "email")
        with pytest.raises(FieldDefinitionConflictError, match="fixed"):
            respondent_field_schema_service.update_field(
                uow,
                admin_user.id,
                test_assembly.id,
                email_field.id,
                field_type=FieldType.TEXT,
            )

    def test_update_field_unset_sentinel_preserves_options(self, uow, admin_user, test_assembly):
        field_id = self._custom_field_id(uow, admin_user, test_assembly)
        respondent_field_schema_service.update_field(
            uow,
            admin_user.id,
            test_assembly.id,
            field_id,
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="a"), ChoiceOption(value="b")],
        )
        # Update label only — options should be preserved (sentinel semantics).
        updated = respondent_field_schema_service.update_field(
            uow,
            admin_user.id,
            test_assembly.id,
            field_id,
            label="Gender identity",
        )
        assert updated.options is not None
        assert [o.value for o in updated.options] == ["a", "b"]

    def test_update_field_explicit_none_clears_options(self, uow, admin_user, test_assembly):
        field_id = self._custom_field_id(uow, admin_user, test_assembly)
        respondent_field_schema_service.update_field(
            uow,
            admin_user.id,
            test_assembly.id,
            field_id,
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption(value="a"), ChoiceOption(value="b")],
        )
        updated = respondent_field_schema_service.update_field(
            uow,
            admin_user.id,
            test_assembly.id,
            field_id,
            field_type=FieldType.TEXT,
            options=None,
        )
        assert updated.field_type == FieldType.TEXT
        assert updated.options is None


class TestGuessFieldTypes:
    def _setup_custom_csv(self, uow, admin_user, assembly, csv_content):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            assembly.id,
            csv_content,
            replace_existing=True,
        )

    def test_bool_column_guessed_as_bool_or_none(self, uow, admin_user, test_assembly):
        self._setup_custom_csv(
            uow,
            admin_user,
            test_assembly,
            "external_id,voted\nR1,true\nR2,false\nR3,yes\n",
        )

        changed = respondent_field_schema_service.guess_field_types(uow, admin_user.id, test_assembly.id)

        assert changed.get("voted") == FieldType.BOOL_OR_NONE

    def test_integer_column_guessed(self, uow, admin_user, test_assembly):
        self._setup_custom_csv(
            uow,
            admin_user,
            test_assembly,
            "external_id,age\nR1,30\nR2,45\nR3,62\n",
        )
        changed = respondent_field_schema_service.guess_field_types(uow, admin_user.id, test_assembly.id)
        assert changed.get("age") == FieldType.INTEGER

    def test_small_distinct_column_guessed_as_choice_radio(self, uow, admin_user, test_assembly):
        self._setup_custom_csv(
            uow,
            admin_user,
            test_assembly,
            "external_id,region\nR1,North\nR2,South\nR3,East\n",
        )
        changed = respondent_field_schema_service.guess_field_types(uow, admin_user.id, test_assembly.id)
        assert changed.get("region") == FieldType.CHOICE_RADIO
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        region = next(f for f in schema if f.field_key == "region")
        assert region.options is not None
        assert sorted(o.value for o in region.options) == ["East", "North", "South"]

    def test_mid_distinct_column_guessed_as_choice_dropdown(self, uow, admin_user, test_assembly):
        rows = "\n".join(f"R{i},region_{i}" for i in range(10))
        csv_content = "external_id,region\n" + rows + "\n"
        self._setup_custom_csv(uow, admin_user, test_assembly, csv_content)
        changed = respondent_field_schema_service.guess_field_types(uow, admin_user.id, test_assembly.id)
        assert changed.get("region") == FieldType.CHOICE_DROPDOWN

    def test_many_distinct_left_as_text(self, uow, admin_user, test_assembly):
        rows = "\n".join(f"R{i},name_{i}" for i in range(50))
        csv_content = "external_id,fullname\n" + rows + "\n"
        self._setup_custom_csv(uow, admin_user, test_assembly, csv_content)
        changed = respondent_field_schema_service.guess_field_types(uow, admin_user.id, test_assembly.id)
        assert "fullname" not in changed  # untouched
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        fullname = next(f for f in schema if f.field_key == "fullname")
        assert fullname.field_type == FieldType.TEXT

    def test_target_category_name_match_uses_target_values(self, uow, admin_user, test_assembly):
        # Pre-seed target category with 4 values
        category = TargetCategory(
            assembly_id=test_assembly.id,
            name="Region",
            values=[
                TargetValue(value="North", min=0, max=10),
                TargetValue(value="South", min=0, max=10),
                TargetValue(value="East", min=0, max=10),
                TargetValue(value="West", min=0, max=10),
            ],
        )
        with uow:
            uow.target_categories.add(category)
            uow.commit()

        # CSV has only "North" in the data but target has 4 values
        self._setup_custom_csv(
            uow,
            admin_user,
            test_assembly,
            "external_id,Region\nR1,North\n",
        )

        changed = respondent_field_schema_service.guess_field_types(uow, admin_user.id, test_assembly.id)
        assert changed.get("Region") == FieldType.CHOICE_RADIO
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        region = next(f for f in schema if f.field_key == "Region")
        assert region.options is not None
        assert sorted(o.value for o in region.options) == ["East", "North", "South", "West"]

    def test_skips_already_typed_rows(self, uow, admin_user, test_assembly):
        self._setup_custom_csv(
            uow,
            admin_user,
            test_assembly,
            "external_id,voted\nR1,true\nR2,false\n",
        )
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        voted = next(f for f in schema if f.field_key == "voted")
        respondent_field_schema_service.update_field(
            uow,
            admin_user.id,
            test_assembly.id,
            voted.id,
            field_type=FieldType.LONGTEXT,
        )

        changed = respondent_field_schema_service.guess_field_types(uow, admin_user.id, test_assembly.id)
        assert "voted" not in changed

    def test_skips_fixed_rows(self, uow, admin_user, test_assembly):
        self._setup_custom_csv(
            uow,
            admin_user,
            test_assembly,
            "external_id,email\nR1,a@b.com\n",
        )
        changed = respondent_field_schema_service.guess_field_types(uow, admin_user.id, test_assembly.id)
        assert "email" not in changed

    def test_permission_gated(self, uow, regular_user, test_assembly):
        with pytest.raises(InsufficientPermissions):
            respondent_field_schema_service.guess_field_types(uow, regular_user.id, test_assembly.id)


class TestPopulateSchemaFieldTypes:
    def test_fixed_keys_get_hardcoded_types(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,custom\nR001,val\n",
        )
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        email_field = next(f for f in schema if f.field_key == "email")
        eligible_field = next(f for f in schema if f.field_key == "eligible")
        assert email_field.field_type == FieldType.EMAIL
        assert eligible_field.field_type == FieldType.BOOL_OR_NONE

    def test_new_non_fixed_rows_default_to_text(self, uow, admin_user, test_assembly):
        respondent_service.import_respondents_from_csv(
            uow,
            admin_user.id,
            test_assembly.id,
            "external_id,custom\nR001,val\n",
        )
        schema = respondent_field_schema_service.get_schema(uow, admin_user.id, test_assembly.id)
        custom_field = next(f for f in schema if f.field_key == "custom")
        assert custom_field.field_type == FieldType.TEXT
        assert custom_field.options is None


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
