"""ABOUTME: Unit tests for the selection summary report builder
ABOUTME: Covers happy path, multi-category, deleted respondents, edge cases, and errors"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import (
    RespondentStatus,
    SelectionRunStatus,
    SelectionTaskType,
)
from opendlp.service_layer.selection_report import (
    CategoryReport,
    CategoryReportRow,
    SelectionReport,
    SelectionReportError,
    build_selection_report,
    selection_report_to_csv,
)
from tests.fakes import FakeUnitOfWork


class _StubURLGenerator:
    def __init__(self, url: str = "https://example.test/sel/url") -> None:
        self.url = url
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def generate_url(self, endpoint: str, _external: bool = False, **values: Any) -> str:
        self.calls.append((endpoint, {"_external": _external, **values}))
        return self.url


def _gender_snapshot(woman_min: int = 1, woman_max: int = 1) -> list[dict[str, Any]]:
    return [
        {
            "name": "Gender",
            "description": "",
            "sort_order": 0,
            "values": [
                {
                    "value": "Man",
                    "min": 1,
                    "max": 1,
                    "min_flex": 0,
                    "max_flex": -1,
                    "percentage_target": 50.0,
                    "description": "",
                },
                {
                    "value": "Woman",
                    "min": woman_min,
                    "max": woman_max,
                    "min_flex": 0,
                    "max_flex": -1,
                    "percentage_target": 50.0,
                    "description": "",
                },
            ],
        },
    ]


def _make_assembly(uow: FakeUnitOfWork, *, number_to_select: int = 2) -> Assembly:
    assembly = Assembly(title="Test City Assembly", number_to_select=number_to_select)
    uow.assemblies.add(assembly)
    return assembly


def _make_respondent(
    uow: FakeUnitOfWork,
    assembly_id: uuid.UUID,
    external_id: str,
    attributes: dict[str, str],
    *,
    status: RespondentStatus = RespondentStatus.POOL,
) -> Respondent:
    r = Respondent(
        assembly_id=assembly_id,
        external_id=external_id,
        selection_status=status,
        attributes=attributes,
    )
    uow.respondents.add(r)
    return r


def _make_run_record(
    uow: FakeUnitOfWork,
    assembly_id: uuid.UUID,
    *,
    selected: list[str],
    remaining: list[str],
    targets_used: list[dict[str, Any]] | None,
) -> SelectionRunRecord:
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=uuid.uuid4(),
        status=SelectionRunStatus.COMPLETED,
        task_type=SelectionTaskType.SELECT_FROM_DB,
        selected_ids=[selected],
        remaining_ids=remaining,
        targets_used=targets_used if targets_used is not None else [],
    )
    uow.selection_run_records.add(record)
    return record


class TestHappyPath:
    def test_single_category_two_values(self):
        uow = FakeUnitOfWork()
        assembly = _make_assembly(uow, number_to_select=2)
        _make_respondent(uow, assembly.id, "p1", {"Gender": "Man"})
        _make_respondent(uow, assembly.id, "p2", {"Gender": "Man"})
        _make_respondent(uow, assembly.id, "p3", {"Gender": "Woman"})
        _make_respondent(uow, assembly.id, "p4", {"Gender": "Woman"})
        record = _make_run_record(
            uow,
            assembly.id,
            selected=["p1", "p3"],
            remaining=["p2", "p4"],
            targets_used=_gender_snapshot(),
        )

        report = build_selection_report(uow, assembly.id, record.task_id, _StubURLGenerator())

        assert report.assembly_title == "Test City Assembly"
        assert report.number_selected == 2
        assert report.pool_size == 4
        assert len(report.categories) == 1
        cat = report.categories[0]
        assert cat.name == "Gender"
        assert [r.value for r in cat.rows] == ["Man", "Woman"]
        man = cat.rows[0]
        assert man.target_min == 1
        assert man.target_max == 1
        assert man.target_pct == pytest.approx(50.0)
        assert man.pool_count == 2
        assert man.pool_pct == pytest.approx(50.0)
        assert man.selected_count == 1
        assert man.selected_pct == pytest.approx(50.0)
        assert man.deleted_count == 0


class TestMultiCategory:
    def test_two_categories_isolated(self):
        uow = FakeUnitOfWork()
        assembly = _make_assembly(uow, number_to_select=2)
        snapshot = [
            *_gender_snapshot(),
            {
                "name": "Age",
                "description": "",
                "sort_order": 1,
                "values": [
                    {
                        "value": "18-29",
                        "min": 1,
                        "max": 1,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 50.0,
                        "description": "",
                    },
                    {
                        "value": "30+",
                        "min": 1,
                        "max": 1,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 50.0,
                        "description": "",
                    },
                ],
            },
        ]
        _make_respondent(uow, assembly.id, "p1", {"Gender": "Man", "Age": "18-29"})
        _make_respondent(uow, assembly.id, "p2", {"Gender": "Woman", "Age": "30+"})
        _make_respondent(uow, assembly.id, "p3", {"Gender": "Man", "Age": "30+"})
        _make_respondent(uow, assembly.id, "p4", {"Gender": "Woman", "Age": "18-29"})
        record = _make_run_record(
            uow,
            assembly.id,
            selected=["p1", "p2"],
            remaining=["p3", "p4"],
            targets_used=snapshot,
        )

        report = build_selection_report(uow, assembly.id, record.task_id, _StubURLGenerator())

        assert [c.name for c in report.categories] == ["Gender", "Age"]
        age = report.categories[1]
        assert {r.value: r.pool_count for r in age.rows} == {"18-29": 2, "30+": 2}
        assert {r.value: r.selected_count for r in age.rows} == {"18-29": 1, "30+": 1}


class TestDeletedRespondents:
    def test_deleted_counted_separately_for_selected(self):
        uow = FakeUnitOfWork()
        assembly = _make_assembly(uow, number_to_select=2)
        _make_respondent(uow, assembly.id, "p1", {"Gender": "Man"})
        _make_respondent(uow, assembly.id, "p2", {"Gender": "Woman"})
        _make_respondent(uow, assembly.id, "p3", {"Gender": "Woman"})
        _make_respondent(
            uow,
            assembly.id,
            "p4",
            {"Gender": ""},
            status=RespondentStatus.DELETED,
        )
        record = _make_run_record(
            uow,
            assembly.id,
            selected=["p1", "p4"],
            remaining=["p3", "p2"],
            targets_used=_gender_snapshot(),
        )

        report = build_selection_report(uow, assembly.id, record.task_id, _StubURLGenerator())

        cat = report.categories[0]
        assert sum(r.deleted_count for r in cat.rows) == 0
        assert sum(r.pool_count for r in cat.rows) == 3
        assert cat.rows[0].pool_count == 1
        assert cat.rows[1].pool_count == 2
        assert report.pool_size == 4

    def test_deleted_counted_separately_for_remaining(self):
        uow = FakeUnitOfWork()
        assembly = _make_assembly(uow, number_to_select=2)
        _make_respondent(uow, assembly.id, "p1", {"Gender": "Man"})
        _make_respondent(uow, assembly.id, "p2", {"Gender": "Woman"})
        _make_respondent(uow, assembly.id, "p3", {"Gender": "Woman"})
        _make_respondent(
            uow,
            assembly.id,
            "p4",
            {"Gender": ""},
            status=RespondentStatus.DELETED,
        )
        record = _make_run_record(
            uow,
            assembly.id,
            selected=["p1", "p2"],
            remaining=["p3", "p4"],
            targets_used=_gender_snapshot(),
        )

        report = build_selection_report(uow, assembly.id, record.task_id, _StubURLGenerator())

        cat = report.categories[0]
        assert sum(r.deleted_count for r in cat.rows) == 0
        assert sum(r.pool_count for r in cat.rows) == 3
        assert cat.rows[0].pool_count == 1
        assert cat.rows[1].pool_count == 2
        assert report.pool_size == 4


class TestZeroPool:
    def test_empty_pool_returns_zeroed_pcts(self):
        uow = FakeUnitOfWork()
        assembly = _make_assembly(uow, number_to_select=0)
        record = _make_run_record(
            uow,
            assembly.id,
            selected=[],
            remaining=[],
            targets_used=_gender_snapshot(),
        )

        report = build_selection_report(uow, assembly.id, record.task_id, _StubURLGenerator())

        assert report.pool_size == 0
        assert report.number_selected == 0
        cat = report.categories[0]
        for row in cat.rows:
            assert row.pool_count == 0
            assert row.selected_count == 0
            assert row.pool_pct == 0.0
            assert row.selected_pct == 0.0
            assert row.target_pct == 0.0


class TestUnknownAttributeRaises:
    def test_unknown_value_raises(self):
        uow = FakeUnitOfWork()
        assembly = _make_assembly(uow, number_to_select=1)
        _make_respondent(uow, assembly.id, "p1", {"Gender": "Man"})
        _make_respondent(uow, assembly.id, "p2", {"Gender": "Other"})
        record = _make_run_record(
            uow,
            assembly.id,
            selected=["p1"],
            remaining=["p2"],
            targets_used=_gender_snapshot(),
        )

        with pytest.raises(SelectionReportError, match="Other"):
            build_selection_report(uow, assembly.id, record.task_id, _StubURLGenerator())


class TestEmptyTargetsUsed:
    def test_empty_targets_used_raises(self):
        uow = FakeUnitOfWork()
        assembly = _make_assembly(uow, number_to_select=1)
        _make_respondent(uow, assembly.id, "p1", {"Gender": "Man"})
        record = _make_run_record(
            uow,
            assembly.id,
            selected=["p1"],
            remaining=[],
            targets_used=[],
        )

        with pytest.raises(SelectionReportError, match="no target snapshot"):
            build_selection_report(uow, assembly.id, record.task_id, _StubURLGenerator())


class TestHeaderFields:
    def test_url_generator_called_with_run_id(self):
        uow = FakeUnitOfWork()
        assembly = _make_assembly(uow, number_to_select=1)
        _make_respondent(uow, assembly.id, "p1", {"Gender": "Man"})
        _make_respondent(uow, assembly.id, "p2", {"Gender": "Woman"})
        record = _make_run_record(
            uow,
            assembly.id,
            selected=["p1"],
            remaining=["p2"],
            targets_used=_gender_snapshot(),
        )
        url = _StubURLGenerator(url="https://example.test/back/sel")

        report = build_selection_report(uow, assembly.id, record.task_id, url)

        assert report.selection_url == "https://example.test/back/sel"
        assert len(url.calls) == 1
        endpoint, kwargs = url.calls[0]
        assert endpoint == "gsheets.view_assembly_selection_with_run"
        assert kwargs["assembly_id"] == assembly.id
        assert kwargs["run_id"] == record.task_id
        assert kwargs["_external"] is True


class TestCaseInsensitiveAttributeMatch:
    def test_normalised_keys_match(self):
        uow = FakeUnitOfWork()
        assembly = _make_assembly(uow, number_to_select=1)
        _make_respondent(uow, assembly.id, "p1", {"gender": "Man"})
        _make_respondent(uow, assembly.id, "p2", {"gender": "Woman"})
        record = _make_run_record(
            uow,
            assembly.id,
            selected=["p1"],
            remaining=["p2"],
            targets_used=_gender_snapshot(),
        )

        report = build_selection_report(uow, assembly.id, record.task_id, _StubURLGenerator())

        cat = report.categories[0]
        assert {r.value: r.pool_count for r in cat.rows} == {"Man": 1, "Woman": 1}


class TestRunNotFound:
    def test_unknown_run_raises(self):
        uow = FakeUnitOfWork()
        assembly = _make_assembly(uow, number_to_select=1)

        with pytest.raises(SelectionReportError, match="not found"):
            build_selection_report(uow, assembly.id, uuid.uuid4(), _StubURLGenerator())


class TestCsvSerialisation:
    def _report(self) -> SelectionReport:
        return SelectionReport(
            assembly_title="Climate Assembly",
            selection_url="https://example.test/sel",
            number_selected=2,
            pool_size=4,
            categories=[
                CategoryReport(
                    name="Gender",
                    rows=[
                        CategoryReportRow(
                            value="Man",
                            target_min=1,
                            target_max=1,
                            target_pct=50.0,
                            pool_count=2,
                            pool_pct=50.0,
                            selected_count=1,
                            selected_pct=50.0,
                            deleted_count=0,
                        ),
                        CategoryReportRow(
                            value="Woman",
                            target_min=1,
                            target_max=1,
                            target_pct=50.0,
                            pool_count=2,
                            pool_pct=50.0,
                            selected_count=1,
                            selected_pct=50.0,
                            deleted_count=0,
                        ),
                    ],
                ),
            ],
        )

    def test_starts_with_bom(self):
        csv_text = selection_report_to_csv(self._report())
        assert csv_text.startswith("﻿")

    def test_header_section_contains_metadata(self):
        csv_text = selection_report_to_csv(self._report())
        assert "Climate Assembly" in csv_text
        assert "https://example.test/sel" in csv_text
        assert "2" in csv_text
        assert "4" in csv_text

    def test_category_section_layout(self):
        csv_text = selection_report_to_csv(self._report())
        lines = csv_text.lstrip("﻿").splitlines()
        assert "Gender,Target,,,,All respondents,,Selected,,Deleted" in lines
        assert ",%,#,Min,Max,%,#,%,#,#" in lines
        assert "Man,50.0,1,1,1,50.0,2,50.0,1,0" in lines
        assert "Woman,50.0,1,1,1,50.0,2,50.0,1,0" in lines

    def test_blank_line_between_sections(self):
        report = self._report()
        report.categories.append(
            CategoryReport(
                name="Age",
                rows=[
                    CategoryReportRow(
                        value="18-29",
                        target_min=1,
                        target_max=1,
                        target_pct=50.0,
                        pool_count=2,
                        pool_pct=50.0,
                        selected_count=1,
                        selected_pct=50.0,
                        deleted_count=0,
                    ),
                ],
            ),
        )
        csv_text = selection_report_to_csv(report)
        assert "\n\n" in csv_text or ",,,,,,,,," in csv_text

    def test_quoting_for_values_with_commas(self):
        report = self._report()
        report.categories[0].rows[0].value = "Aspley, Bilborough"
        csv_text = selection_report_to_csv(report)
        assert '"Aspley, Bilborough"' in csv_text
