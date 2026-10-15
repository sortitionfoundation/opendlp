"""ABOUTME: Unit tests for the check a respondent upload's headers must pass
ABOUTME: Covers the ID column, unusable and reserved names, same-field clashes and header lengths"""

import pytest

from opendlp.service_layer.respondent_field_schema_service import (
    MAX_FIELD_KEY_LENGTH,
    MAX_ID_COLUMN_NAME_LENGTH,
    PROBLEM_HEADER_TOO_LONG,
    PROBLEM_HEADER_WITHOUT_LETTERS,
    PROBLEM_ID_COLUMN_MISSING,
    PROBLEM_RESERVED_HEADER,
    PROBLEM_SAME_FIELD,
    respondent_header_check,
)
from opendlp.service_layer.tabular_data import (
    PROBLEM_BLANK_HEADER_WITH_DATA,
    TableProblem,
    TabularDataError,
    clean_table,
    rows_from_csv,
)


def check_csv(content: str, id_column: str | None = None, previous_id_column: str | None = None):
    return clean_table(rows_from_csv(content), header_checks=[respondent_header_check(id_column, previous_id_column)])


def problems_of(
    content: str, id_column: str | None = None, previous_id_column: str | None = None
) -> list[TableProblem]:
    with pytest.raises(TabularDataError) as exc_info:
        check_csv(content, id_column, previous_id_column)
    return exc_info.value.problems


class TestPassingHeaders:
    def test_ordinary_headers_pass(self):
        table = check_csv("id,first_name,age,email,consent\n1,Ann,30,a@example.org,true\n")

        assert table.headers == ["id", "first_name", "age", "email", "consent"]

    def test_export_only_columns_pass(self):
        """A previously exported file re-imports cleanly."""
        check_csv("external_id,selection_status,created_at,view_url\n1,Pool,2026-01-01,https://x\n")

    def test_the_id_column_may_use_a_reserved_name(self):
        check_csv("name,external_id\nAnn,1\n", id_column="external_id")


class TestIdColumn:
    def test_missing_id_column_is_reported(self):
        [problem] = problems_of("id,first_name\n1,Ann\n", id_column="nationbuilder_id")

        assert problem.kind == PROBLEM_ID_COLUMN_MISSING
        assert "no column called 'nationbuilder_id'" in problem.message
        assert "Its columns are: id, first_name." in problem.message

    def test_says_when_the_id_column_was_prefilled(self):
        [problem] = problems_of(
            "id,first_name\n1,Ann\n", id_column="nationbuilder_id", previous_id_column="nationbuilder_id"
        )

        assert "pre-filled from your last upload" in problem.message

    def test_the_first_named_column_is_the_default(self):
        """A dropped empty column in front does not become the ID column."""
        table = check_csv(",person_ref,name\n,1,Ann\n")

        assert table.headers == ["person_ref", "name"]

    def test_an_id_column_name_too_long_to_store(self):
        long_name = "i" * (MAX_ID_COLUMN_NAME_LENGTH + 1)
        [problem] = problems_of(f"name,{long_name}\nAnn,1\n", id_column=long_name)

        assert problem.kind == PROBLEM_HEADER_TOO_LONG
        assert problem.letters == ("B",)
        assert "the ID column" in problem.message


class TestFieldNames:
    @pytest.mark.parametrize("header", ["#", "???", "---"])
    def test_header_without_letters_or_numbers(self, header):
        [problem] = problems_of(f"id,{header}\n1,x\n")

        assert problem.kind == PROBLEM_HEADER_WITHOUT_LETTERS
        assert problem.letters == ("B",)
        assert problem.message == (f"The header of column B, '{header}', has no letters or numbers in it. Rename it.")

    @pytest.mark.parametrize("header", ["external_id", "Comments", "registration page id", "assembly_id"])
    def test_reserved_header(self, header):
        [problem] = problems_of(f"person_ref,{header}\n1,x\n")

        assert problem.kind == PROBLEM_RESERVED_HEADER
        assert problem.letters == ("B",)

    def test_a_non_id_column_called_id_is_reserved(self):
        """e.g. a Timestamp column first, so it is chosen as the ID column."""
        [problem] = problems_of("Timestamp,ID,name\n2026-01-01,1,Ann\n")

        assert problem.kind == PROBLEM_RESERVED_HEADER
        assert problem.header == "ID"

    def test_a_header_too_long_to_store(self):
        long_header = "h" * (MAX_FIELD_KEY_LENGTH + 1)
        [problem] = problems_of(f"id,{long_header}\n1,x\n")

        assert problem.kind == PROBLEM_HEADER_TOO_LONG
        assert problem.letters == ("B",)
        assert long_header not in problem.message

    def test_a_header_at_the_limit_is_fine(self):
        check_csv(f"id,{'h' * MAX_FIELD_KEY_LENGTH}\n1,x\n")


class TestSameField:
    def test_headers_differing_in_case_and_space(self):
        [problem] = problems_of("id,Age,name,age \n1,30,Ann,31\n")

        assert problem.kind == PROBLEM_SAME_FIELD
        assert problem.letters == ("B", "D")
        assert problem.message.startswith("Columns B ('Age'), D ('age') have headers that count as the same field.")

    def test_lifted_columns_are_checked_too(self):
        """Two email columns would otherwise leave one behind as a reserved attribute."""
        [problem] = problems_of("id,Email,e-mail\n1,a@example.org,b@example.org\n")

        assert problem.kind == PROBLEM_SAME_FIELD

    def test_exact_repeats_are_left_to_the_table_cleaning(self):
        problems = problems_of("id,age,age\n1,30,31\n")

        assert [problem.kind for problem in problems] == ["duplicate_header"]


class TestEveryProblemTogether:
    def test_reports_table_and_header_problems_in_one_error(self):
        problems = problems_of("id,,#,Age,age,comments\n1,note,x,30,31,y\n")

        assert [problem.kind for problem in problems] == [
            PROBLEM_BLANK_HEADER_WITH_DATA,
            PROBLEM_HEADER_WITHOUT_LETTERS,
            PROBLEM_RESERVED_HEADER,
            PROBLEM_SAME_FIELD,
        ]

    def test_a_missing_id_column_is_reported_with_the_other_problems(self):
        problems = problems_of("id,,#,Age,age\n1,note,x,30,31\n", id_column="person_ref")

        assert [problem.kind for problem in problems] == [
            PROBLEM_BLANK_HEADER_WITH_DATA,
            PROBLEM_ID_COLUMN_MISSING,
            PROBLEM_HEADER_WITHOUT_LETTERS,
            PROBLEM_SAME_FIELD,
        ]

    def test_reserved_names_wait_for_the_id_column_to_be_found(self):
        """Which names are reserved depends on which column is the ID."""
        problems = problems_of("id,comments\n1,x\n", id_column="person_ref")

        assert [problem.kind for problem in problems] == [PROBLEM_ID_COLUMN_MISSING]
