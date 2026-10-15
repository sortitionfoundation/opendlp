"""ABOUTME: Unit tests for reading and cleaning uploaded tables
ABOUTME: Covers blank and duplicate columns, ragged rows, row numbering and collecting every problem"""

import csv

import pytest

from opendlp.service_layer.exceptions import InvalidSelection
from opendlp.service_layer.tabular_data import (
    PROBLEM_BLANK_HEADER_WITH_DATA,
    PROBLEM_DUPLICATE_HEADER,
    PROBLEM_EMPTY,
    PROBLEM_NUL_CHARACTER,
    PROBLEM_UNREADABLE,
    Column,
    TableProblem,
    TabularDataError,
    clean_table,
    column_letter,
    rows_from_csv,
    select_columns,
)


def clean_csv(content: str, header_checks=()):
    return clean_table(rows_from_csv(content), header_checks=header_checks)


def problems_of(content: str, header_checks=()) -> list[TableProblem]:
    with pytest.raises(TabularDataError) as exc_info:
        clean_csv(content, header_checks=header_checks)
    return exc_info.value.problems


class TestColumnLetter:
    @pytest.mark.parametrize(
        ("position", "letter"),
        [(0, "A"), (2, "C"), (25, "Z"), (26, "AA"), (51, "AZ"), (54, "BC"), (701, "ZZ"), (702, "AAA")],
    )
    def test_matches_the_spreadsheet(self, position, letter):
        assert column_letter(position) == letter


class TestRowsFromCsv:
    def test_keeps_blank_lines_as_empty_rows(self):
        """Keeping them is what lets row numbers match the spreadsheet."""
        assert rows_from_csv("id,a\n1,x\n\n2,y\n") == [["id", "a"], ["1", "x"], [], ["2", "y"]]

    def test_a_quoted_newline_stays_in_one_row(self):
        assert rows_from_csv('id,a\n1,"two\nlines"\n2,y\n') == [["id", "a"], ["1", "two\nlines"], ["2", "y"]]

    def test_unreadable_content_names_the_row(self):
        """An over-long field - usually an unclosed quote - is what makes the csv module give up."""
        content = "id,a\n1,x\n2," + '"' + "y" * 200 + "\n"
        old_limit = csv.field_size_limit(100)
        try:
            with pytest.raises(TabularDataError) as exc_info:
                rows_from_csv(content)
        finally:
            csv.field_size_limit(old_limit)

        [problem] = exc_info.value.problems
        assert problem.kind == PROBLEM_UNREADABLE
        assert problem.row == 3
        assert "row 3" in str(exc_info.value)


class TestCleanTableBlankColumns:
    def test_keeps_named_columns_and_rows(self):
        table = clean_csv("id,name\n1,Ann\n2,Bob\n")

        assert table.headers == ["id", "name"]
        assert table.rows == [["1", "Ann"], ["2", "Bob"]]
        assert table.as_dicts() == [{"id": "1", "name": "Ann"}, {"id": "2", "name": "Bob"}]

    def test_drops_trailing_empty_columns(self):
        """The spreadsheet-export case the issue was raised for."""
        table = clean_csv("id,name,,,\n1,Ann,,,\n2,Bob,,,\n")

        assert table.headers == ["id", "name"]
        assert table.rows == [["1", "Ann"], ["2", "Bob"]]

    def test_drops_an_empty_column_in_the_middle(self):
        table = clean_csv("id,,name\n1,,Ann\n")

        assert table.headers == ["id", "name"]
        assert table.rows == [["1", "Ann"]]

    def test_drops_two_empty_unnamed_columns(self):
        table = clean_csv("id,,name,\n1,,Ann,\n")

        assert table.headers == ["id", "name"]

    def test_whitespace_only_cells_count_as_blank(self):
        table = clean_csv("id, ,name\n1,  ,Ann\n")

        assert table.headers == ["id", "name"]

    def test_keeps_the_original_letters_after_dropping(self):
        table = clean_csv("id,,name\n1,,Ann\n")

        assert [column.letter for column in table.columns] == ["A", "C"]

    def test_rejects_an_unnamed_column_with_data(self):
        [problem] = problems_of("id,name,,age\n1,Ann,,30\n2,Bob,,40\n3,Cy,note,50\n")

        assert problem.kind == PROBLEM_BLANK_HEADER_WITH_DATA
        assert problem.letters == ("C",)
        assert problem.row == 4
        assert problem.message == (
            "Column C (between 'name' and 'age') has no header but has data in it, starting at row 4. "
            "Delete the column, or give it a header."
        )

    def test_names_only_the_header_before_at_the_right_edge(self):
        [problem] = problems_of("id,name,\n1,Ann,note\n")

        assert problem.message.startswith("Column C (after 'name') has no header")

    def test_names_only_the_header_after_at_the_left_edge(self):
        [problem] = problems_of(",id,name\nnote,1,Ann\n")

        assert problem.message.startswith("Column A (before 'id') has no header")

    def test_neighbours_skip_other_unnamed_columns(self):
        [problem] = problems_of("id,,,name\n1,,x,Ann\n")

        assert problem.message.startswith("Column C (between 'id' and 'name')")

    def test_data_in_the_first_of_two_unnamed_columns(self):
        """A dict-based reader loses this value: both columns share the key ''."""
        [problem] = problems_of("id,,name,\n1,secret,Ann,\n")

        assert problem.letters == ("B",)

    def test_data_in_the_second_of_two_unnamed_columns(self):
        [problem] = problems_of("id,,name,\n1,,Ann,secret\n")

        assert problem.letters == ("D",)

    def test_the_message_does_not_include_the_cell_value(self):
        """The routes log the message, and a cell can hold personal data."""
        [problem] = problems_of("id,name,\n1,Ann,ann@example.org\n")

        assert "ann@example.org" not in problem.message

    def test_columns_past_z(self):
        header = ",".join(f"h{i}" for i in range(26)) + ","
        row = ",".join("x" for _ in range(26)) + ",data"
        [problem] = problems_of(f"{header}\n{row}\n")

        assert problem.letters == ("AA",)


class TestCleanTableRaggedRows:
    def test_a_row_longer_than_the_header_is_an_unnamed_column_with_data(self):
        [problem] = problems_of("id,age\n1,30\n2,40,EXTRA\n")

        assert problem.kind == PROBLEM_BLANK_HEADER_WITH_DATA
        assert problem.letters == ("C",)
        assert problem.row == 3

    def test_a_row_longer_than_the_header_with_only_blanks_is_fine(self):
        table = clean_csv("id,age\n1,30,,\n")

        assert table.rows == [["1", "30"]]

    def test_a_short_row_is_padded_with_blanks(self):
        table = clean_csv("id,age,email\n1,30\n")

        assert table.as_dicts() == [{"id": "1", "age": "30", "email": ""}]


class TestCleanTableRows:
    def test_blank_lines_are_dropped_and_row_numbers_stay_true(self):
        """Respondent 2 is on spreadsheet row 5, not the third row read."""
        table = clean_csv("id,a\n1,x\n\n\n2,y\n")

        assert table.rows == [["1", "x"], ["2", "y"]]
        assert table.row_numbers == [2, 5]

    def test_rows_of_empty_cells_are_dropped(self):
        """How Excel exports a blank row."""
        table = clean_csv("id,a\n1,x\n,\n2,y\n")

        assert table.rows == [["1", "x"], ["2", "y"]]
        assert table.row_numbers == [2, 4]

    def test_a_quoted_newline_does_not_shift_later_rows(self):
        table = clean_csv('id,a\n1,"two\nlines"\n2,y\n')

        assert table.row_numbers == [2, 3]

    def test_header_after_leading_blank_lines(self):
        table = clean_csv("\n\nid,a\n1,x\n")

        assert table.headers == ["id", "a"]
        assert table.row_numbers == [4]

    def test_header_only_file_has_no_rows(self):
        table = clean_csv("id,name\n")

        assert table.headers == ["id", "name"]
        assert table.rows == []

    @pytest.mark.parametrize("content", ["", "\n\n", ",,\n,,\n"])
    def test_empty_file_is_rejected(self, content):
        [problem] = problems_of(content)

        assert problem.kind == PROBLEM_EMPTY
        assert problem.message == "The file is empty or has no header row."

    def test_headers_are_stripped(self):
        table = clean_csv(" id , name \n1,Ann\n")

        assert table.headers == ["id", "name"]


class TestCleanTableDuplicates:
    def test_rejects_a_repeated_header_naming_every_letter(self):
        [problem] = problems_of("email,name,email,x,email\na,b,c,d,e\n")

        assert problem.kind == PROBLEM_DUPLICATE_HEADER
        assert problem.letters == ("A", "C", "E")
        assert problem.header == "email"
        assert problem.message == (
            "The header 'email' appears in columns A, C, E. Delete the extra columns, or rename them."
        )

    def test_repeats_differing_only_in_surrounding_space_are_duplicates(self):
        [problem] = problems_of("email,email \na,b\n")

        assert problem.kind == PROBLEM_DUPLICATE_HEADER

    def test_headers_differing_in_case_are_not_duplicates_here(self):
        """Whether 'Age' and 'age' clash is for the caller's own header checks."""
        assert clean_csv("Age,age\n1,2\n").headers == ["Age", "age"]


class TestCleanTableNulCharacters:
    def test_reports_a_nul_once_per_column_at_its_first_row(self):
        [problem] = problems_of("id,a\n1,x\n2,y\x00\n3,z\x00\n")

        assert problem.kind == PROBLEM_NUL_CHARACTER
        assert problem.letters == ("B",)
        assert problem.row == 3

    def test_reports_a_nul_in_the_header(self):
        [problem] = problems_of("id,a\x00\n1,x\n")

        assert problem.row == 1


class TestReportingEveryProblem:
    def test_every_problem_is_reported_together(self):
        problems = problems_of("id,,email,email,a\n1,note,b,c,x\x00\n")

        assert [problem.kind for problem in problems] == [
            PROBLEM_BLANK_HEADER_WITH_DATA,
            PROBLEM_DUPLICATE_HEADER,
            PROBLEM_NUL_CHARACTER,
        ]

    def test_the_message_has_a_lead_line_then_one_line_per_problem(self):
        with pytest.raises(TabularDataError) as exc_info:
            clean_csv("id,,email,email\n1,note,b,c\n")

        lines = str(exc_info.value).split("\n")
        assert lines[0] == "There are 2 problems with this file:"
        assert lines[1].startswith("Column B (between 'id' and 'email')")
        assert lines[2].startswith("The header 'email' appears in columns C, D.")

    def test_header_checks_run_even_when_the_columns_have_problems(self):
        seen: list[list[str]] = []

        def check(columns: list[Column]) -> list[TableProblem]:
            seen.append([column.header for column in columns])
            return [TableProblem(kind="custom", message="Custom problem.")]

        problems = problems_of("id,,name\n1,note,Ann\n", header_checks=[check])

        assert seen == [["id", "name"]]
        assert [problem.kind for problem in problems] == [PROBLEM_BLANK_HEADER_WITH_DATA, "custom"]

    def test_header_checks_see_the_letters(self):
        def check(columns: list[Column]) -> list[TableProblem]:
            return [TableProblem(kind="custom", message=f"{c.letter}={c.header}") for c in columns]

        problems = problems_of("id,,name\n1,,Ann\n", header_checks=[check])

        assert [problem.message for problem in problems] == ["A=id", "C=name"]

    def test_a_clean_header_check_lets_the_table_through(self):
        table = clean_csv("id,name\n1,Ann\n", header_checks=[lambda columns: []])

        assert table.headers == ["id", "name"]


class TestSelectColumns:
    WANTED = ("feature", "value", "min", "max", "comment")

    def select(self, content: str):
        return select_columns(rows_from_csv(content), self.WANTED)

    def test_ignores_columns_not_wanted(self):
        table = self.select("feature,value,min,max,notes\nage,young,1,2,whatever\n")

        assert table.headers == ["feature", "value", "min", "max"]
        assert table.rows == [["age", "young", "1", "2"]]

    def test_ignores_an_unnamed_column_with_data(self):
        """An unlabelled notes column in a targets file is not a problem."""
        table = self.select("feature,value,min,max,\nage,young,1,2,a note\n")

        assert table.headers == ["feature", "value", "min", "max"]

    def test_matches_ignoring_case_and_returns_the_wanted_name(self):
        table = self.select("Feature, Value ,MIN,Max\nage,young,1,2\n")

        assert table.headers == ["feature", "value", "min", "max"]

    def test_rejects_a_repeated_wanted_header(self):
        with pytest.raises(TabularDataError) as exc_info:
            self.select("feature,value,min,Min,max\nage,young,1,1,2\n")

        [problem] = exc_info.value.problems
        assert problem.kind == PROBLEM_DUPLICATE_HEADER
        assert problem.letters == ("C", "D")

    def test_ignores_a_repeated_unwanted_header(self):
        table = self.select("feature,value,min,max,notes,notes\nage,young,1,2,a,b\n")

        assert table.headers == ["feature", "value", "min", "max"]

    def test_a_missing_wanted_header_is_not_its_concern(self):
        assert self.select("feature,value\nage,young\n").headers == ["feature", "value"]


class TestTabularDataError:
    def test_is_an_invalid_selection(self):
        """So every upload handler that catches InvalidSelection catches it."""
        assert issubclass(TabularDataError, InvalidSelection)

    def test_user_msg_is_the_curated_message(self):
        error = TabularDataError([TableProblem(kind="custom", message="Column C is wrong.")])

        assert error.user_msg() == "Column C is wrong."
