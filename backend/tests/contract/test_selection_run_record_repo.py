"""ABOUTME: Contract tests for SelectionRunRecordRepository.
ABOUTME: Each test runs against both fake and SQL backends to verify identical behaviour."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from tests.contract.conftest import ContractBackend


def _make_record(
    backend: ContractBackend,
    assembly_id: uuid.UUID,
    status: SelectionRunStatus = SelectionRunStatus.PENDING,
    task_type: SelectionTaskType = SelectionTaskType.SELECT_FROM_DB,
    created_at: datetime | None = None,
) -> SelectionRunRecord:
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=uuid.uuid4(),
        status=status,
        task_type=task_type,
        created_at=created_at,
    )
    backend.repo.add(record)
    backend.commit()
    return record


class TestAddAndGet:
    def test_add_and_get_by_task_id(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        record = _make_record(selection_run_backend, assembly.id)

        retrieved = selection_run_backend.repo.get(record.task_id)
        assert retrieved is not None
        assert retrieved.task_id == record.task_id
        assert retrieved.assembly_id == assembly.id

    def test_get_nonexistent_returns_none(self, selection_run_backend: ContractBackend):
        assert selection_run_backend.repo.get(uuid.uuid4()) is None

    def test_all_returns_added_records(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        r1 = _make_record(selection_run_backend, assembly.id)
        r2 = _make_record(selection_run_backend, assembly.id)

        all_records = list(selection_run_backend.repo.all())
        task_ids = {r.task_id for r in all_records}
        assert r1.task_id in task_ids
        assert r2.task_id in task_ids


class TestGetByTaskId:
    def test_finds_by_task_id(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        record = _make_record(selection_run_backend, assembly.id)

        retrieved = selection_run_backend.repo.get_by_task_id(record.task_id)
        assert retrieved is not None
        assert retrieved.task_id == record.task_id

    def test_returns_none_for_nonexistent(self, selection_run_backend: ContractBackend):
        assert selection_run_backend.repo.get_by_task_id(uuid.uuid4()) is None


class TestGetByAssemblyId:
    def test_returns_records_for_assembly(self, selection_run_backend: ContractBackend):
        a1 = selection_run_backend.make_assembly()
        a2 = selection_run_backend.make_assembly()
        _make_record(selection_run_backend, a1.id)
        _make_record(selection_run_backend, a1.id)
        _make_record(selection_run_backend, a2.id)

        records = list(selection_run_backend.repo.get_by_assembly_id(a1.id))
        assert len(records) == 2
        assert all(r.assembly_id == a1.id for r in records)

    def test_returns_empty_for_no_records(self, selection_run_backend: ContractBackend):
        assert list(selection_run_backend.repo.get_by_assembly_id(uuid.uuid4())) == []


class TestGetLatestForAssembly:
    def test_returns_most_recent(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        _make_record(selection_run_backend, assembly.id, created_at=datetime.now(UTC) - timedelta(hours=2))
        newer = _make_record(selection_run_backend, assembly.id, created_at=datetime.now(UTC))

        latest = selection_run_backend.repo.get_latest_for_assembly(assembly.id)
        assert latest is not None
        assert latest.task_id == newer.task_id

    def test_returns_none_for_no_records(self, selection_run_backend: ContractBackend):
        assert selection_run_backend.repo.get_latest_for_assembly(uuid.uuid4()) is None


class TestGetRunningTasks:
    def test_returns_running_tasks(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        running = _make_record(selection_run_backend, assembly.id, status=SelectionRunStatus.RUNNING)
        _make_record(selection_run_backend, assembly.id, status=SelectionRunStatus.COMPLETED)

        tasks = list(selection_run_backend.repo.get_running_tasks())
        assert len(tasks) == 1
        assert tasks[0].task_id == running.task_id

    def test_returns_empty_when_none_running(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        _make_record(selection_run_backend, assembly.id, status=SelectionRunStatus.COMPLETED)

        assert list(selection_run_backend.repo.get_running_tasks()) == []


class TestGetAllUnfinished:
    def test_returns_pending_and_running(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        pending = _make_record(selection_run_backend, assembly.id, status=SelectionRunStatus.PENDING)
        running = _make_record(selection_run_backend, assembly.id, status=SelectionRunStatus.RUNNING)
        _make_record(selection_run_backend, assembly.id, status=SelectionRunStatus.COMPLETED)
        _make_record(selection_run_backend, assembly.id, status=SelectionRunStatus.FAILED)

        unfinished = selection_run_backend.repo.get_all_unfinished()
        task_ids = {r.task_id for r in unfinished}
        assert len(unfinished) == 2
        assert pending.task_id in task_ids
        assert running.task_id in task_ids

    def test_returns_empty_when_all_finished(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        _make_record(selection_run_backend, assembly.id, status=SelectionRunStatus.COMPLETED)

        assert selection_run_backend.repo.get_all_unfinished() == []
