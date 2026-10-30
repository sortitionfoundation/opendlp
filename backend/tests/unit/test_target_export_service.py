"""ABOUTME: Unit tests for building the targets export table, without a database
ABOUTME: Columns match the targets CSV import; flex only when set everywhere; percentages and notes"""

import uuid

from sortition_algorithms.features import MAX_FLEX_UNSET

from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.service_layer.target_export_service import build_targets_table

ASSEMBLY_ID = uuid.uuid4()


def _category(name, values, comment="", source_url=""):
    return TargetCategory(assembly_id=ASSEMBLY_ID, name=name, values=values, comment=comment, source_url=source_url)


def _rows_as_dicts(table):
    return [dict(zip(table.headers, row, strict=True)) for row in table.rows]


class TestBuildTargetsTable:
    def test_writes_the_columns_the_import_reads(self):
        table = build_targets_table([_category("Gender", [TargetValue(value="Woman", min=3, max=7)])])

        assert table.headers == [
            "feature",
            "value",
            "min",
            "max",
            "percentage",
            "comment",
            "category_comment",
            "source_url",
        ]

    def test_one_row_per_value_in_the_order_given(self):
        table = build_targets_table([
            _category("Gender", [TargetValue(value="Woman", min=3, max=7), TargetValue(value="Man", min=2, max=6)]),
            _category("Age", [TargetValue(value="16-29", min=1, max=4)]),
        ])

        assert [row[:4] for row in table.rows] == [
            ["Gender", "Woman", "3", "7"],
            ["Gender", "Man", "2", "6"],
            ["Age", "16-29", "1", "4"],
        ]

    def test_carries_the_percentage_and_the_value_comment(self):
        table = build_targets_table([
            _category(
                "Gender",
                [
                    TargetValue(value="Woman", min=3, max=7, percentage_target=51.5, comment="census"),
                    TargetValue(value="Man", min=3, max=7, percentage_target=48.0),
                    TargetValue(value="Other", min=0, max=1),
                ],
            )
        ])

        rows = _rows_as_dicts(table)
        assert [(row["percentage"], row["comment"]) for row in rows] == [("51.5", "census"), ("48", ""), ("", "")]

    def test_repeats_the_category_comment_and_source_on_every_row(self):
        """So a row keeps them when the sheet is sorted or filtered; the import takes repeats as one."""
        table = build_targets_table([
            _category(
                "Gender",
                [TargetValue(value="Woman", min=3, max=7), TargetValue(value="Man", min=3, max=7)],
                comment="from the 2021 census",
                source_url="https://example.com/census",
            )
        ])

        for row in _rows_as_dicts(table):
            assert row["category_comment"] == "from the 2021 census"
            assert row["source_url"] == "https://example.com/census"

    def test_keeps_the_line_breaks_in_a_comment(self):
        table = build_targets_table([
            _category("Gender", [TargetValue(value="Woman", min=3, max=7, comment="first\nsecond")])
        ])

        assert _rows_as_dicts(table)[0]["comment"] == "first\nsecond"

    def test_writes_flex_when_every_value_has_it(self):
        table = build_targets_table([
            _category(
                "Gender",
                [
                    TargetValue(value="Woman", min=3, max=7, min_flex=1, max_flex=9),
                    TargetValue(value="Man", min=3, max=7, min_flex=0, max_flex=8),
                ],
            )
        ])

        assert table.headers[:6] == ["feature", "value", "min", "max", "min_flex", "max_flex"]
        assert [row[4:6] for row in table.rows] == [["1", "9"], ["0", "8"]]

    def test_leaves_flex_out_when_any_value_lacks_it(self):
        """Selection lets the library work flex out then, so a re-upload should too."""
        table = build_targets_table([
            _category(
                "Gender",
                [
                    TargetValue(value="Woman", min=3, max=7, min_flex=1, max_flex=9),
                    TargetValue(value="Man", min=3, max=7, max_flex=MAX_FLEX_UNSET),
                ],
            )
        ])

        assert "min_flex" not in table.headers
        assert "max_flex" not in table.headers

    def test_a_category_with_no_values_has_no_row(self):
        table = build_targets_table([
            _category("Empty", []),
            _category("Gender", [TargetValue(value="Woman", min=3, max=7)]),
        ])

        assert [row[0] for row in table.rows] == ["Gender"]

    def test_no_targets_give_the_headers_alone(self):
        table = build_targets_table([])

        assert table.headers[0] == "feature"
        assert table.rows == []
