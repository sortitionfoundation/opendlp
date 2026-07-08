"""ABOUTME: Unit tests for the tabular export target abstractions
ABOUTME: Covers TabularData and the in-memory CsvExportTarget"""

import csv
from io import StringIO

import pytest

from opendlp.adapters.tabular_export import CsvExportTarget, TabularData

_BOM = "﻿"


class TestTabularData:
    def test_holds_headers_and_rows(self):
        table = TabularData(headers=["id", "name"], rows=[["R1", "Alice"]])
        assert table.headers == ["id", "name"]
        assert table.rows == [["R1", "Alice"]]


class TestCsvExportTarget:
    def test_writes_header_and_rows_as_csv(self):
        target = CsvExportTarget()
        table = TabularData(headers=["id", "name"], rows=[["R1", "Alice"], ["R2", "Bob"]])

        target.write_sheet("Respondents", table)

        content = target.getvalue()
        assert content.startswith(_BOM)
        rows = list(csv.reader(StringIO(content[len(_BOM) :])))
        assert rows == [["id", "name"], ["R1", "Alice"], ["R2", "Bob"]]

    def test_quotes_values_with_commas(self):
        target = CsvExportTarget()
        table = TabularData(headers=["id", "note"], rows=[["R1", "a, b, c"]])

        target.write_sheet("Respondents", table)

        rows = list(csv.reader(StringIO(target.getvalue()[len(_BOM) :])))
        assert rows == [["id", "note"], ["R1", "a, b, c"]]

    def test_handles_no_rows(self):
        target = CsvExportTarget()
        table = TabularData(headers=["id", "name"], rows=[])

        target.write_sheet("Respondents", table)

        rows = list(csv.reader(StringIO(target.getvalue()[len(_BOM) :])))
        assert rows == [["id", "name"]]

    def test_rejects_second_write_sheet_call(self):
        target = CsvExportTarget()
        table = TabularData(headers=["id"], rows=[["R1"]])
        target.write_sheet("First", table)

        with pytest.raises(ValueError, match="one sheet"):
            target.write_sheet("Second", table)
