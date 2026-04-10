"""ABOUTME: Unit tests for DatabaseProgressReporter.
ABOUTME: Verifies throttling, phase transitions, missing-record no-op, and end_phase."""

import uuid

import pytest

from opendlp.adapters import sortition_progress as sp
from opendlp.adapters.sortition_progress import DatabaseProgressReporter
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from tests.fakes import FakeUnitOfWork


def _make_uow_with_record(task_id: uuid.UUID) -> FakeUnitOfWork:
    uow = FakeUnitOfWork()
    assembly_id = uuid.uuid4()
    uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Test Assembly"))
    uow.selection_run_records.add(
        SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=task_id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            status=SelectionRunStatus.RUNNING,
        )
    )
    return uow


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fake_clock(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(sp.time, "monotonic", clock.monotonic)
    return clock


@pytest.fixture
def register_uow(monkeypatch):
    registered: list[FakeUnitOfWork] = []

    def fake_bootstrap(session_factory=None):
        assert registered, "no fake UoW registered — call register_uow(uow) in the test"
        return registered[-1]

    monkeypatch.setattr(sp, "bootstrap", fake_bootstrap)

    def _register(uow: FakeUnitOfWork) -> None:
        registered.append(uow)

    return _register


class TestDatabaseProgressReporter:
    def test_constructor_does_not_touch_db(self, register_uow):
        # No uow registered — if construction called bootstrap, the assertion
        # inside fake_bootstrap would trip.
        DatabaseProgressReporter(task_id=uuid.uuid4(), session_factory=None)

    def test_start_phase_always_writes(self, fake_clock, register_uow):
        task_id = uuid.uuid4()
        uow = _make_uow_with_record(task_id)
        register_uow(uow)
        reporter = DatabaseProgressReporter(task_id=task_id, session_factory=None)

        reporter.start_phase("phase_a", total=10)
        fake_clock.advance(0.01)
        reporter.start_phase("phase_b", total=20)

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.progress is not None
        assert record.progress["phase"] == "phase_b"
        assert record.progress["current"] == 0
        assert record.progress["total"] == 20

    def test_update_within_min_interval_is_dropped(self, fake_clock, register_uow):
        task_id = uuid.uuid4()
        uow = _make_uow_with_record(task_id)
        register_uow(uow)
        reporter = DatabaseProgressReporter(task_id=task_id, session_factory=None, min_interval_seconds=1.0)

        reporter.start_phase("phase_a", total=100)
        fake_clock.advance(0.1)
        reporter.update(1)

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.progress is not None
        # The update within the interval was dropped; progress still shows
        # the start_phase force-flush value.
        assert record.progress["current"] == 0

    def test_update_beyond_min_interval_writes(self, fake_clock, register_uow):
        task_id = uuid.uuid4()
        uow = _make_uow_with_record(task_id)
        register_uow(uow)
        reporter = DatabaseProgressReporter(task_id=task_id, session_factory=None, min_interval_seconds=1.0)

        reporter.start_phase("phase_a", total=100)
        fake_clock.advance(1.5)
        reporter.update(5)

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.progress is not None
        assert record.progress["phase"] == "phase_a"
        assert record.progress["current"] == 5
        assert record.progress["total"] == 100

    def test_phase_transition_forces_flush_within_interval(self, fake_clock, register_uow):
        task_id = uuid.uuid4()
        uow = _make_uow_with_record(task_id)
        register_uow(uow)
        reporter = DatabaseProgressReporter(task_id=task_id, session_factory=None, min_interval_seconds=1.0)

        reporter.start_phase("phase_a", total=10)
        fake_clock.advance(0.1)
        reporter.start_phase("phase_b", total=20)

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.progress is not None
        assert record.progress["phase"] == "phase_b"
        assert record.progress["total"] == 20

    def test_missing_record_is_silent_noop(self, fake_clock, register_uow):
        task_id = uuid.uuid4()
        register_uow(FakeUnitOfWork())  # no record for this task_id
        reporter = DatabaseProgressReporter(task_id=task_id, session_factory=None)

        reporter.start_phase("phase_a", total=10)
        fake_clock.advance(5.0)
        reporter.update(5)
        reporter.end_phase()

    def test_end_phase_is_noop(self, fake_clock, register_uow):
        task_id = uuid.uuid4()
        uow = _make_uow_with_record(task_id)
        register_uow(uow)
        reporter = DatabaseProgressReporter(task_id=task_id, session_factory=None)

        reporter.end_phase()

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.progress is None

    def test_update_includes_updated_at_timestamp(self, fake_clock, register_uow):
        task_id = uuid.uuid4()
        uow = _make_uow_with_record(task_id)
        register_uow(uow)
        reporter = DatabaseProgressReporter(task_id=task_id, session_factory=None)

        reporter.start_phase("phase_a", total=10)

        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        assert record.progress is not None
        assert "updated_at" in record.progress
        assert isinstance(record.progress["updated_at"], str)
