"""ABOUTME: Reads uploaded tables (CSV now; Sheets or xlsx later) into a list of rows, then cleans them
ABOUTME: Drops empty unnamed columns and reports every problem with the columns in one curated error"""

import csv
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from io import StringIO

import structlog

from opendlp.translations import gettext as _

from .exceptions import CuratedMessage, InvalidSelection

logger = structlog.get_logger(__name__)

PROBLEM_EMPTY = "empty"
PROBLEM_UNREADABLE = "unreadable"
PROBLEM_BLANK_HEADER_WITH_DATA = "blank_header_with_data"
PROBLEM_DUPLICATE_HEADER = "duplicate_header"
PROBLEM_NUL_CHARACTER = "nul_character"

# How many problems the message lists before summarising the rest, so a file
# with a hundred bad columns does not produce a hundred-line message.
MAX_LISTED_PROBLEMS = 10


def column_letter(position: int) -> str:
    """The spreadsheet letter for a 0-based column position: 0 is "A", 26 is "AA"."""
    letters = ""
    number = position + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


@dataclass(frozen=True)
class Column:
    header: str
    position: int

    @property
    def letter(self) -> str:
        return column_letter(self.position)


@dataclass(frozen=True)
class TableProblem:
    """One thing wrong with an uploaded table, with the message to show for it.

    ``kind`` is one of the ``PROBLEM_*`` constants, or a caller's own for a
    problem found by a header check. ``letters`` and ``row`` locate it the way a
    spreadsheet would; ``row`` is 0 when the problem is not about one row.
    """

    kind: str
    message: str
    letters: tuple[str, ...] = ()
    header: str = ""
    row: int = 0


HeaderCheck = Callable[[list[Column]], list[TableProblem]]


class TabularDataError(CuratedMessage, InvalidSelection):
    """A problem with the shape of an uploaded table, written for the organiser."""

    def __init__(self, problems: Sequence[TableProblem]) -> None:
        self.problems = list(problems)
        if len(self.problems) == 1:
            message = self.problems[0].message
        else:
            lead = _("There are %(count)d problems with this file:", count=len(self.problems))
            lines = [lead, *(problem.message for problem in self.problems[:MAX_LISTED_PROBLEMS])]
            if len(self.problems) > MAX_LISTED_PROBLEMS:
                lines.append(_("… and %(count)d more", count=len(self.problems) - MAX_LISTED_PROBLEMS))
            message = "\n".join(lines)
        super().__init__(message)


@dataclass(frozen=True)
class Table:
    """A cleaned table: named columns, and the non-blank rows aligned with them.

    ``row_numbers`` holds the spreadsheet row of each entry in ``rows``, so a
    message about a row can point at the row the organiser will see.
    """

    columns: list[Column]
    rows: list[list[str]] = field(default_factory=list)
    row_numbers: list[int] = field(default_factory=list)

    @property
    def headers(self) -> list[str]:
        return [column.header for column in self.columns]

    def as_dicts(self) -> list[dict[str, str]]:
        headers = self.headers
        return [dict(zip(headers, row, strict=True)) for row in self.rows]


def rows_from_csv(csv_content: str) -> list[list[str]]:
    """Read CSV text into a list of rows, one per spreadsheet row, blank rows included.

    Raises ``TabularDataError`` if the csv module cannot read the content - an
    unclosed quote in a large file, say - naming the row it had reached.
    """
    rows: list[list[str]] = []
    try:
        rows.extend(csv.reader(StringIO(csv_content)))
    except csv.Error as e:
        row_number = len(rows) + 1
        logger.info("unreadable CSV upload", row=row_number, error=str(e))
        raise TabularDataError([
            TableProblem(
                kind=PROBLEM_UNREADABLE,
                message=_(
                    "This file could not be read as a CSV at row %(row)d. "
                    "Check that row for a quotation mark that is not closed.",
                    row=row_number,
                ),
                row=row_number,
            )
        ]) from e
    return rows


def clean_table(raw: list[list[str]], header_checks: Sequence[HeaderCheck] = ()) -> Table:
    """Clean a table in which every column counts.

    A column with no header and no data is dropped. A column with no header but
    some data, and a header used more than once, are problems. Every problem -
    including those the ``header_checks`` find - is collected and raised as one
    ``TabularDataError``.
    """
    split = _split_header(raw)
    problems: list[TableProblem] = []
    named: list[Column] = []
    dropped = 0
    for position, header in enumerate(split.header_row):
        if header:
            named.append(Column(header=header, position=position))
            continue
        first_row = _first_row_with_data(split.body, split.row_numbers, position)
        if first_row:
            problems.append(_blank_header_problem(split.header_row, position, first_row))
        else:
            dropped += 1
    if dropped:
        logger.debug("dropped empty unnamed columns", count=dropped)
    return _finish(named, split, problems, header_checks)


def select_columns(raw: list[list[str]], wanted: Iterable[str], header_checks: Sequence[HeaderCheck] = ()) -> Table:
    """Clean a table keeping only the columns whose header is in ``wanted``.

    Headers match ignoring case and surrounding space, and come back as the
    name given in ``wanted``. Every other column - named or not, empty or not -
    is ignored. A wanted header used more than once is a problem.
    """
    canonical = {name.strip().lower(): name for name in wanted}
    split = _split_header(raw)
    selected = [
        Column(header=canonical[header.lower()], position=position)
        for position, header in enumerate(split.header_row)
        if header.lower() in canonical
    ]
    return _finish(selected, split, [], header_checks)


@dataclass(frozen=True)
class _Split:
    header_row: list[str]
    header_row_number: int
    body: list[list[str]]
    row_numbers: list[int]


def _split_header(raw: list[list[str]]) -> _Split:
    """Find the header row, pad every row to one width, and drop blank rows.

    The header is the first row with anything in it, as ``csv.DictReader``
    treats it. Short rows are padded with blanks; a row longer than the header
    gives the header blank cells, so its overhang shows up as an unnamed column.
    """
    header_index = next((index for index, row in enumerate(raw) if _has_data(row)), None)
    if header_index is None:
        raise TabularDataError([TableProblem(kind=PROBLEM_EMPTY, message=_("The file is empty or has no header row."))])
    width = max(len(row) for row in raw)
    header_row = [cell.strip() for cell in _padded(raw[header_index], width)]
    body: list[list[str]] = []
    row_numbers: list[int] = []
    for index in range(header_index + 1, len(raw)):
        if _has_data(raw[index]):
            body.append(_padded(raw[index], width))
            row_numbers.append(index + 1)
    return _Split(header_row, header_index + 1, body, row_numbers)


def _finish(
    columns: list[Column], split: _Split, problems: list[TableProblem], header_checks: Sequence[HeaderCheck]
) -> Table:
    problems.extend(_duplicate_header_problems(columns))
    problems.extend(_nul_character_problems(columns, split.header_row_number, split.body, split.row_numbers))
    for check in header_checks:
        problems.extend(check(columns))
    if problems:
        raise TabularDataError(problems)
    rows = [[row[column.position] for column in columns] for row in split.body]
    return Table(columns=columns, rows=rows, row_numbers=split.row_numbers)


def _has_data(row: list[str]) -> bool:
    return any(cell.strip() for cell in row)


def _padded(row: list[str], width: int) -> list[str]:
    return row + [""] * (width - len(row))


def _first_row_with_data(body: list[list[str]], row_numbers: list[int], position: int) -> int:
    for row, row_number in zip(body, row_numbers, strict=True):
        if row[position].strip():
            return row_number
    return 0


def _blank_header_problem(header_row: list[str], position: int, first_row: int) -> TableProblem:
    letter = column_letter(position)
    before = next((header for header in reversed(header_row[:position]) if header), "")
    after = next((header for header in header_row[position + 1 :] if header), "")
    if before and after:
        message = _(
            "Column %(letter)s (between '%(before)s' and '%(after)s') has no header but has data in it, "
            "starting at row %(row)d. Delete the column, or give it a header.",
            letter=letter,
            before=before,
            after=after,
            row=first_row,
        )
    elif before:
        message = _(
            "Column %(letter)s (after '%(before)s') has no header but has data in it, "
            "starting at row %(row)d. Delete the column, or give it a header.",
            letter=letter,
            before=before,
            row=first_row,
        )
    else:
        message = _(
            "Column %(letter)s (before '%(after)s') has no header but has data in it, "
            "starting at row %(row)d. Delete the column, or give it a header.",
            letter=letter,
            after=after,
            row=first_row,
        )
    return TableProblem(kind=PROBLEM_BLANK_HEADER_WITH_DATA, message=message, letters=(letter,), row=first_row)


def _duplicate_header_problems(columns: list[Column]) -> list[TableProblem]:
    by_header: dict[str, list[Column]] = {}
    for column in columns:
        by_header.setdefault(column.header, []).append(column)
    problems: list[TableProblem] = []
    for header, same in by_header.items():
        if len(same) < 2:
            continue
        letters = tuple(column.letter for column in same)
        problems.append(
            TableProblem(
                kind=PROBLEM_DUPLICATE_HEADER,
                message=_(
                    "The header '%(header)s' appears in columns %(letters)s. Delete the extra columns, or rename them.",
                    header=header,
                    letters=", ".join(letters),
                ),
                letters=letters,
                header=header,
            )
        )
    return problems


def _nul_character_problems(
    columns: list[Column], header_row_number: int, body: list[list[str]], row_numbers: list[int]
) -> list[TableProblem]:
    """Report each column holding a NUL character once, at the first row it appears in.

    The csv module reads a NUL without complaint, but the database refuses to
    store one, so it has to be caught here.
    """
    problems: list[TableProblem] = []
    for column in columns:
        if "\x00" in column.header:
            first_row = header_row_number
        else:
            first_row = next(
                (number for row, number in zip(body, row_numbers, strict=True) if "\x00" in row[column.position]), 0
            )
        if not first_row:
            continue
        problems.append(
            TableProblem(
                kind=PROBLEM_NUL_CHARACTER,
                message=_(
                    "Column %(letter)s has a null character in it at row %(row)d, which cannot be saved. "
                    "Remove it, and upload the file again.",
                    letter=column.letter,
                    row=first_row,
                ),
                letters=(column.letter,),
                header=column.header,
                row=first_row,
            )
        )
    return problems
