"""ABOUTME: Abstract export target for tabular respondent data
ABOUTME: TabularData plus an in-memory CsvExportTarget, sharing one write interface"""

import csv
from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import StringIO

# Excel misreads non-ASCII CSVs that lack a byte-order mark, so we prefix one.
_CSV_BOM = "﻿"


@dataclass(frozen=True)
class TabularData:
    """A single sheet of already-stringified tabular data.

    Every row has the same length as ``headers``.
    """

    headers: list[str]
    rows: list[list[str]]


class AbstractTabularExportTarget(ABC):
    """A destination that a table of respondent data can be written to.

    Concrete targets (CSV download, Google Sheets) expose their result
    through target-specific accessors rather than a return value.
    """

    @abstractmethod
    def write_sheet(self, title: str, table: TabularData) -> None:
        """Write one sheet of tabular data to this target."""


class CsvExportTarget(AbstractTabularExportTarget):
    """Accumulate a single sheet into an in-memory, BOM-prefixed CSV string."""

    def __init__(self) -> None:
        self._buffer = StringIO()
        self._written = False

    def write_sheet(self, title: str, table: TabularData) -> None:
        if self._written:
            raise ValueError("CsvExportTarget accepts only one sheet")
        self._written = True
        writer = csv.writer(self._buffer, lineterminator="\n")
        writer.writerow(table.headers)
        for row in table.rows:
            writer.writerow(row)

    def getvalue(self) -> str:
        """Return the accumulated CSV, prefixed with a byte-order mark."""
        return _CSV_BOM + self._buffer.getvalue()
