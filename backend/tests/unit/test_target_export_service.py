"""ABOUTME: Unit tests for the targets export, without a database: the table it builds, and the exports
ABOUTME: Columns match the targets CSV import; flex only when set everywhere; permission; the saved Google Sheet"""

import uuid

import pytest
from sortition_algorithms.features import MAX_FLEX_UNSET

from opendlp.adapters.tabular_export import CsvExportTarget, ExportTargetError
from opendlp.domain.assembly import Assembly
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, GSheetExportKind
from opendlp.service_layer.exceptions import InsufficientPermissions
from opendlp.service_layer.target_export_service import (
    build_targets_table,
    export_targets,
    export_targets_to_gsheet,
    get_targets_gsheet_config,
)
from tests.fakes import FakeGSheetExportTarget, FakeUnitOfWork

SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"

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


def _seed(uow: FakeUnitOfWork, *, global_role: GlobalRole = GlobalRole.ADMIN) -> tuple[User, Assembly]:
    """A user and an assembly with one target category on it."""
    user = User(email="targets-export@example.com", global_role=global_role, password_hash="hash")
    uow.users.add(user)
    assembly = Assembly(title="Targets Export Assembly", number_to_select=20)
    uow.assemblies.add(assembly)
    uow.target_categories.add(
        TargetCategory(
            assembly_id=assembly.id,
            name="Gender",
            values=[TargetValue(value="Woman", min=9, max=11), TargetValue(value="Man", min=8, max=10)],
        )
    )
    return user, assembly


def _export_to_gsheet(uow, user, assembly, target, spreadsheet_url=SHEET_URL, worksheet_name=""):
    export_targets_to_gsheet(
        uow,
        user.id,
        assembly.id,
        spreadsheet_url=spreadsheet_url,
        worksheet_name=worksheet_name,
        target=target,
    )


class TestExportTargets:
    def test_an_assembly_with_no_targets_exports_headers_only(self, uow):
        user = User(email="targets-export@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(user)
        assembly = Assembly(title="No Targets")
        uow.assemblies.add(assembly)
        target = CsvExportTarget()

        export_targets(uow, user.id, assembly.id, target=target)

        assert len([line for line in target.getvalue().splitlines() if line]) == 1

    def test_requires_manage_permission(self, uow):
        """Export is a manage action, matching the respondent and dashboard exports."""
        user, assembly = _seed(uow, global_role=GlobalRole.USER)

        with pytest.raises(InsufficientPermissions):
            export_targets(uow, user.id, assembly.id, target=CsvExportTarget())


class TestExportTargetsToGsheet:
    def test_writes_the_sheet_and_saves_the_config(self, uow):
        user, assembly = _seed(uow)
        target = FakeGSheetExportTarget()

        _export_to_gsheet(uow, user, assembly, target, worksheet_name="Quotas")

        ((title, table),) = target.writes
        assert title == "Quotas"
        assert table.headers[0] == "feature"
        saved = get_targets_gsheet_config(uow, user.id, assembly.id)
        assert saved is not None
        assert saved.export_kind == GSheetExportKind.TARGETS
        assert saved.url == SHEET_URL
        assert saved.worksheet_name == "Quotas"

    def test_a_blank_worksheet_name_writes_to_targets(self, uow):
        user, assembly = _seed(uow)
        target = FakeGSheetExportTarget()

        _export_to_gsheet(uow, user, assembly, target, worksheet_name="  ")

        assert [title for title, _table in target.writes] == ["Targets"]

    def test_keeps_its_own_sheet_apart_from_the_other_exports(self, uow):
        user, assembly = _seed(uow)

        _export_to_gsheet(uow, user, assembly, FakeGSheetExportTarget())

        for kind in (GSheetExportKind.RESPONDENTS, GSheetExportKind.DASHBOARD):
            assert uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly.id, kind) is None

    def test_a_rejected_url_writes_nothing(self, uow):
        user, assembly = _seed(uow)
        target = FakeGSheetExportTarget()

        with pytest.raises(ValueError):
            _export_to_gsheet(uow, user, assembly, target, spreadsheet_url="https://example.com/not-a-sheet")

        assert target.writes == []

    def test_a_failed_write_saves_no_config(self, uow):
        user, assembly = _seed(uow)
        target = FakeGSheetExportTarget(error=ExportTargetError("no access"))

        with pytest.raises(ExportTargetError):
            _export_to_gsheet(uow, user, assembly, target)

        assert get_targets_gsheet_config(uow, user.id, assembly.id) is None
