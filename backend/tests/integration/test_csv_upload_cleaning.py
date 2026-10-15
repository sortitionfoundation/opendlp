"""ABOUTME: Integration tests for cleaning uploaded CSVs before they are imported
ABOUTME: Blank, unnamed, duplicate and badly named columns across the upload services, with a real database"""

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondent_derivation import LargeMappingRule
from opendlp.domain.respondent_field_schema import FieldType, RespondentFieldDefinition, RespondentFieldGroup
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import (
    derivation_service,
    respondent_field_schema_service,
    respondent_service,
    target_csv_import,
)
from opendlp.service_layer.respondent_field_schema_service import (
    PROBLEM_ID_COLUMN_MISSING,
    PROBLEM_SAME_FIELD,
)
from opendlp.service_layer.tabular_data import (
    PROBLEM_BLANK_HEADER_WITH_DATA,
    PROBLEM_DUPLICATE_HEADER,
    TabularDataError,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def uow(postgres_session_factory):
    """An already-entered UnitOfWork; the whole test is one transaction."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as entered:
        yield entered


@pytest.fixture
def admin_user(uow):
    user = User(email="admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    uow.users.add(user)
    detached_user = user.create_detached_copy()
    uow.commit()
    return detached_user


@pytest.fixture
def test_assembly(uow):
    assembly = Assembly(title="Test Assembly", question="Test?", number_to_select=30)
    uow.assemblies.add(assembly)
    detached_assembly = assembly.create_detached_copy()
    uow.commit()
    return detached_assembly


def import_csv(uow, user, assembly, content: str, id_column: str | None = None):
    return respondent_service.import_respondents_from_csv(
        uow, user.id, assembly.id, content, replace_existing=True, id_column=id_column
    )


class TestRespondentImport:
    def test_trailing_empty_columns_are_ignored(self, uow, admin_user: User, test_assembly: Assembly):
        """The spreadsheet export the issue was raised for."""
        respondents, errors, _ = import_csv(uow, admin_user, test_assembly, "id,age,,,\nR1,30,,,\nR2,40,,,\n")

        assert errors == []
        assert [r.attributes for r in respondents] == [{"age": "30"}, {"age": "40"}]
        keys = {field.field_key for field in uow.respondent_field_definitions.list_by_assembly(test_assembly.id)}
        assert "" not in keys
        assert "age" in keys

    def test_an_unnamed_column_with_data_is_rejected(self, uow, admin_user: User, test_assembly: Assembly):
        with pytest.raises(TabularDataError) as exc_info:
            import_csv(uow, admin_user, test_assembly, "id,age,\nR1,30,\nR2,40,note\n")

        [problem] = exc_info.value.problems
        assert problem.kind == PROBLEM_BLANK_HEADER_WITH_DATA
        assert problem.letters == ("C",)
        assert problem.row == 3

    def test_a_rejected_file_leaves_existing_respondents_alone(self, uow, admin_user: User, test_assembly: Assembly):
        import_csv(uow, admin_user, test_assembly, "id,age\nR1,30\n")
        uow.commit()

        with pytest.raises(TabularDataError):
            import_csv(uow, admin_user, test_assembly, "id,age,\nR9,30,note\n")

        assert [r.external_id for r in uow.respondents.get_by_assembly_id(test_assembly.id)] == ["R1"]

    def test_headers_that_are_the_same_field_are_rejected(self, uow, admin_user: User, test_assembly: Assembly):
        """Before, the domain refused these once per row, and the route showed a generic error."""
        with pytest.raises(TabularDataError) as exc_info:
            import_csv(uow, admin_user, test_assembly, "id,Email,email\nR1,a@example.org,b@example.org\n")

        assert [problem.kind for problem in exc_info.value.problems] == [PROBLEM_SAME_FIELD]

    def test_ragged_rows_import(self, uow, admin_user: User, test_assembly: Assembly):
        """A short row used to crash on a None value."""
        respondents, errors, _ = import_csv(uow, admin_user, test_assembly, "id,age,postcode\nR1,30\nR2,40,SW1\n")

        assert errors == []
        assert [r.attributes for r in respondents] == [{"age": "30", "postcode": ""}, {"age": "40", "postcode": "SW1"}]

    def test_row_warnings_name_the_spreadsheet_row(self, uow, admin_user: User, test_assembly: Assembly):
        """Blank lines above a row used to make its warning point at the wrong row."""
        _, errors, _ = import_csv(uow, admin_user, test_assembly, "id,age\nR1,30\n\n\n,40\nR1,50\n")

        assert errors == ["Row 5: skipped, empty id", "Row 6: skipped duplicate id: R1"]

    def test_a_missing_id_column_is_reported_with_the_columns(self, uow, admin_user: User, test_assembly: Assembly):
        with pytest.raises(TabularDataError) as exc_info:
            import_csv(uow, admin_user, test_assembly, "id,age,\nR1,30,note\n", id_column="person_ref")

        assert [problem.kind for problem in exc_info.value.problems] == [
            PROBLEM_BLANK_HEADER_WITH_DATA,
            PROBLEM_ID_COLUMN_MISSING,
        ]


class TestComputeDiffForPendingCsv:
    @pytest.fixture
    def seeded(self, uow, admin_user: User, test_assembly: Assembly):
        import_csv(uow, admin_user, test_assembly, "id,age\nR1,30\n")
        uow.commit()

    def diff(self, uow, user, assembly, content: str, id_column: str | None = None):
        return respondent_field_schema_service.compute_diff_for_pending_csv(
            uow, user.id, assembly.id, content, explicit_id_column=id_column
        )

    def test_trailing_empty_columns_add_no_fields(self, uow, admin_user, test_assembly, seeded):
        diff = self.diff(uow, admin_user, test_assembly, "id,age,postcode,,\nR2,40,SW1,,\n")

        assert diff is not None
        assert {key for key, _ in diff.new_keys} == {"postcode"}

    def test_an_unnamed_column_with_data_is_rejected_before_confirming(self, uow, admin_user, test_assembly, seeded):
        """The diff page used to offer a confirmation for a file the import then failed on."""
        with pytest.raises(TabularDataError) as exc_info:
            self.diff(uow, admin_user, test_assembly, "id,age,\nR2,40,note\n")

        assert [problem.kind for problem in exc_info.value.problems] == [PROBLEM_BLANK_HEADER_WITH_DATA]

    def test_a_repeated_header_is_rejected(self, uow, admin_user, test_assembly, seeded):
        with pytest.raises(TabularDataError) as exc_info:
            self.diff(uow, admin_user, test_assembly, "id,age,age\nR2,40,41\n")

        assert [problem.kind for problem in exc_info.value.problems] == [PROBLEM_DUPLICATE_HEADER]

    def test_a_missing_id_column_is_rejected(self, uow, admin_user, test_assembly, seeded):
        with pytest.raises(TabularDataError) as exc_info:
            self.diff(uow, admin_user, test_assembly, "id,age\nR2,40\n", id_column="person_ref")

        assert "no column called 'person_ref'" in exc_info.value.user_msg()


class TestTargetImport:
    def import_targets(self, uow, user, assembly, content: str):
        return target_csv_import.import_targets_from_csv(uow, user.id, assembly.id, content, replace_existing=True)

    def test_an_unnamed_notes_column_is_ignored(self, uow, admin_user: User, test_assembly: Assembly):
        """Organisers keep notes beside their targets; that column is not ours to judge."""
        result = self.import_targets(
            uow, admin_user, test_assembly, "feature,value,min,max,\nGender,Male,1,2,check this\nGender,Female,1,2,\n"
        )

        assert [(c.name, [v.value for v in c.values]) for c in result.categories] == [("Gender", ["Male", "Female"])]

    def test_capitalised_headers_import(self, uow, admin_user: User, test_assembly: Assembly):
        """These used to fail with a message asking for the old column names."""
        result = self.import_targets(
            uow, admin_user, test_assembly, "Feature,Value,Min,Max,Comment\nGender,Male,1,2,from the census\n"
        )

        [category] = result.categories
        male = category.get_value("Male")
        assert (male.min, male.max, male.comment) == (1, 2, "from the census")

    def test_a_repeated_wanted_header_is_rejected(self, uow, admin_user: User, test_assembly: Assembly):
        with pytest.raises(TabularDataError) as exc_info:
            self.import_targets(uow, admin_user, test_assembly, "feature,value,min,Min,max\nGender,Male,1,1,2\n")

        [problem] = exc_info.value.problems
        assert problem.kind == PROBLEM_DUPLICATE_HEADER
        assert problem.letters == ("C", "D")

    def test_a_short_row_is_padded(self, uow, admin_user: User, test_assembly: Assembly):
        """A short row used to reach the library as None: "'None' is not a number"."""
        result = self.import_targets(uow, admin_user, test_assembly, "feature,value,min,max,comment\nGender,Male,1,2\n")

        assert result.categories[0].get_value("Male").comment == ""

    def test_an_empty_file_is_rejected(self, uow, admin_user: User, test_assembly: Assembly):
        with pytest.raises(TabularDataError) as exc_info:
            self.import_targets(uow, admin_user, test_assembly, "\n\n")

        assert exc_info.value.user_msg() == "The file is empty or has no header row."


class TestLargeMappingUpload:
    @pytest.fixture
    def region_field(self, uow, admin_user: User, test_assembly: Assembly):
        uow.respondent_field_definitions.add(
            RespondentFieldDefinition(
                assembly_id=test_assembly.id,
                field_key="postcode",
                label="Postcode",
                group=RespondentFieldGroup.ABOUT_YOU,
                sort_order=10,
                field_type=FieldType.TEXT,
            )
        )
        field, _ = derivation_service.create_derived_field(
            uow,
            admin_user.id,
            test_assembly.id,
            field_key="region",
            label="Region",
            source_field_key="postcode",
            rule=LargeMappingRule(),
            output_values=["London", "North"],
        )
        uow.commit()
        return field

    def upload(self, uow, user, assembly, field, content: str):
        return derivation_service.upload_large_mapping(uow, user.id, assembly.id, field.id, content)

    def test_a_leading_empty_column_does_not_empty_the_table(
        self, uow, admin_user: User, test_assembly: Assembly, region_field
    ):
        report = self.upload(
            uow, admin_user, test_assembly, region_field, ",pc,area\n,SW1A 1AA,London\n,M1 1AE,North\n"
        )

        assert report.row_count == 2
        entries = uow.respondent_field_mapping_entries.list_for_field(region_field.id)
        assert {(e.lookup_key, e.output_value) for e in entries} == {("SW1A1AA", "London"), ("M11AE", "North")}

    def test_a_repeated_header_is_rejected(self, uow, admin_user: User, test_assembly: Assembly, region_field):
        with pytest.raises(TabularDataError) as exc_info:
            self.upload(uow, admin_user, test_assembly, region_field, "postcode,region,region\nSW1A 1AA,London,North\n")

        assert [problem.kind for problem in exc_info.value.problems] == [PROBLEM_DUPLICATE_HEADER]
        assert uow.respondent_field_mapping_entries.count_for_field(region_field.id) == 0
