"""ABOUTME: Unit tests for SelectionRunRecord.progress_info property.
ABOUTME: Verifies phase→label mapping, parameterised labels, unknown-phase fallback, and None handling."""

import uuid

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import ProgressInfo, SelectionRunStatus, SelectionTaskType


def _make_record(progress: dict | None = None) -> SelectionRunRecord:
    return SelectionRunRecord(
        assembly_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        status=SelectionRunStatus.RUNNING,
        task_type=SelectionTaskType.SELECT_FROM_DB,
        progress=progress,
    )


class TestProgressInfoProperty:
    def test_none_progress_returns_default_label(self):
        record = _make_record(progress=None)
        info = record.progress_info
        assert isinstance(info, ProgressInfo)
        assert "Processing" in info.label
        assert info.current is None
        assert info.total is None

    def test_read_gsheet_phase(self):
        record = _make_record({"phase": "read_gsheet", "current": 0, "total": None})
        info = record.progress_info
        assert "Reading spreadsheet" in info.label
        assert info.current == 0
        assert info.total is None

    def test_write_gsheet_phase(self):
        record = _make_record({"phase": "write_gsheet", "current": 0, "total": None})
        info = record.progress_info
        assert "Writing results" in info.label

    def test_multiplicative_weights_with_total(self):
        record = _make_record({"phase": "multiplicative_weights", "current": 45, "total": 200})
        info = record.progress_info
        assert "45" in info.label
        assert "200" in info.label
        assert "Finding diverse committees" in info.label
        assert info.current == 45
        assert info.total == 200

    def test_maximin_optimization_iteration(self):
        record = _make_record({"phase": "maximin_optimization", "current": 17, "total": None})
        info = record.progress_info
        assert "17" in info.label
        assert "maximin" in info.label.lower()
        assert info.total is None

    def test_nash_optimization_iteration(self):
        record = _make_record({"phase": "nash_optimization", "current": 9, "total": None})
        info = record.progress_info
        assert "9" in info.label
        assert "Nash" in info.label

    def test_leximin_outer_with_total(self):
        record = _make_record({"phase": "leximin_outer", "current": 8, "total": 50})
        info = record.progress_info
        assert "8" in info.label
        assert "50" in info.label
        assert "leximin" in info.label.lower()

    def test_legacy_attempt(self):
        record = _make_record({"phase": "legacy_attempt", "current": 2, "total": 10})
        info = record.progress_info
        assert "2" in info.label
        assert "10" in info.label
        assert info.current == 2
        assert info.total == 10

    def test_diversimax_phase(self):
        record = _make_record({"phase": "diversimax", "current": 0, "total": None})
        info = record.progress_info
        assert "diversimax" in info.label.lower()

    def test_unknown_phase_falls_back_to_raw_name(self):
        record = _make_record({"phase": "mystery_future_phase", "current": 5, "total": 10})
        info = record.progress_info
        assert "mystery_future_phase" in info.label
        assert info.current == 5
        assert info.total == 10

    def test_empty_phase_uses_default_label(self):
        record = _make_record({"phase": "", "current": 0, "total": None})
        info = record.progress_info
        assert "Processing" in info.label

    def test_always_returns_progress_info(self):
        """progress_info always returns a ProgressInfo, never None."""
        for progress in [None, {}, {"phase": "read_gsheet", "current": 0, "total": None}]:
            record = _make_record(progress=progress)
            assert isinstance(record.progress_info, ProgressInfo)


class TestProgressInfoPercent:
    def test_percent_with_total(self):
        info = ProgressInfo(label="test", current=45, total=200)
        assert info.percent == 22.5

    def test_percent_none_when_total_is_none(self):
        info = ProgressInfo(label="test", current=5, total=None)
        assert info.percent is None

    def test_percent_none_when_total_is_zero(self):
        info = ProgressInfo(label="test", current=0, total=0)
        assert info.percent is None

    def test_percent_none_when_no_current_or_total(self):
        info = ProgressInfo(label="test")
        assert info.percent is None
