"""ABOUTME: Unit tests for cleaning uploaded CSVs before they are imported, over a FakeUnitOfWork
ABOUTME: Blank, unnamed, duplicate and badly named columns across the respondent and target upload services"""

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import (
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


@pytest.fixture
def admin_user(uow):
    user = User(email="admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    uow.users.add(user)
    return user


@pytest.fixture
def test_assembly(uow):
    assembly = Assembly(title="Test Assembly", question="Test?", number_to_select=30)
    uow.assemblies.add(assembly)
    return assembly


def import_csv(uow, user, assembly, content: str, id_column: str | None = None):
    return respondent_service.import_respondents_from_csv(
        uow, user.id, assembly.id, content, replace_existing=True, id_column=id_column
    )


def respondents_in(uow, assembly) -> list[tuple]:
    """Each respondent's identity and attributes, to tell whether any were replaced or changed."""
    respondents = uow.respondents.get_by_assembly_id(assembly.id)
    return sorted((r.id, r.external_id, dict(r.attributes)) for r in respondents)


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
        """The import replaces what is there, so the file must be checked before anything is deleted."""
        import_csv(uow, admin_user, test_assembly, "id,age\nR1,30\nR2,40\n")
        before = respondents_in(uow, test_assembly)

        with pytest.raises(TabularDataError):
            import_csv(uow, admin_user, test_assembly, "id,age,\nR9,30,note\n")

        assert respondents_in(uow, test_assembly) == before
        assert {external_id: attributes for _, external_id, attributes in before} == {
            "R1": {"age": "30"},
            "R2": {"age": "40"},
        }

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

    def test_a_short_row_is_padded(self, uow, admin_user: User, test_assembly: Assembly):
        """A short row used to reach the library as None: "'None' is not a number"."""
        result = self.import_targets(uow, admin_user, test_assembly, "feature,value,min,max,comment\nGender,Male,1,2\n")

        assert result.categories[0].get_value("Male").comment == ""

    def test_an_empty_file_is_rejected(self, uow, admin_user: User, test_assembly: Assembly):
        with pytest.raises(TabularDataError) as exc_info:
            self.import_targets(uow, admin_user, test_assembly, "\n\n")

        assert exc_info.value.user_msg() == "The file is empty or has no header row."
