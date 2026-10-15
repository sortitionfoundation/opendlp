"""ABOUTME: Integration tests for cleaning uploaded CSVs before they are imported
ABOUTME: Blank, unnamed, duplicate and badly named columns across the upload services, with a real database"""

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import respondent_field_schema_service, respondent_service
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
