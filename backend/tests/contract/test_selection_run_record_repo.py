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


class TestTargetsUsedRoundTrip:
    def test_targets_used_persists_and_round_trips(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        snapshot = [
            {
                "name": "Gender",
                "description": "",
                "sort_order": 0,
                "values": [
                    {
                        "value": "Man",
                        "min": 5,
                        "max": 7,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 50.0,
                        "description": "",
                    },
                    {
                        "value": "Woman",
                        "min": 5,
                        "max": 7,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 50.0,
                        "description": "",
                    },
                ],
            },
        ]
        record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=uuid.uuid4(),
            status=SelectionRunStatus.PENDING,
            task_type=SelectionTaskType.SELECT_FROM_DB,
            targets_used=snapshot,
        )
        selection_run_backend.repo.add(record)
        selection_run_backend.commit()

        retrieved = selection_run_backend.repo.get_by_task_id(record.task_id)
        assert retrieved is not None
        assert retrieved.targets_used == snapshot

    def test_targets_used_default_empty(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        record = _make_record(selection_run_backend, assembly.id)

        retrieved = selection_run_backend.repo.get_by_task_id(record.task_id)
        assert retrieved is not None
        assert retrieved.targets_used == []


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


class TestGetLatestForAssemblyByTaskType:
    def test_filter_returns_newest_matching(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        now = datetime.now(UTC)
        select_old = _make_record(
            selection_run_backend,
            assembly.id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            created_at=now - timedelta(hours=3),
        )
        select_new = _make_record(
            selection_run_backend,
            assembly.id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            created_at=now - timedelta(hours=2),
        )
        # newer cleanup should not be returned by SELECT_GSHEET filter
        _make_record(
            selection_run_backend,
            assembly.id,
            task_type=SelectionTaskType.DELETE_OLD_TABS,
            created_at=now - timedelta(hours=1),
        )
        _make_record(
            selection_run_backend,
            assembly.id,
            task_type=SelectionTaskType.LOAD_GSHEET,
            created_at=now,
        )

        latest = selection_run_backend.repo.get_latest_for_assembly(
            assembly.id, task_type=SelectionTaskType.SELECT_GSHEET
        )
        assert latest is not None
        assert latest.task_id == select_new.task_id
        assert latest.task_id != select_old.task_id

    def test_no_task_type_returns_newest_overall(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        now = datetime.now(UTC)
        _make_record(
            selection_run_backend,
            assembly.id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            created_at=now - timedelta(hours=2),
        )
        newest = _make_record(
            selection_run_backend,
            assembly.id,
            task_type=SelectionTaskType.DELETE_OLD_TABS,
            created_at=now,
        )

        latest = selection_run_backend.repo.get_latest_for_assembly(assembly.id)
        assert latest is not None
        assert latest.task_id == newest.task_id

    def test_filter_returns_none_when_no_match(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        _make_record(
            selection_run_backend,
            assembly.id,
            task_type=SelectionTaskType.LOAD_GSHEET,
        )
        latest = selection_run_backend.repo.get_latest_for_assembly(
            assembly.id, task_type=SelectionTaskType.SELECT_GSHEET
        )
        assert latest is None


class TestGetRecentForAssembly:
    def test_returns_newest_first_up_to_limit(self, selection_run_backend: ContractBackend):
        """Records come back ordered newest-first, capped at the limit."""
        assembly = selection_run_backend.make_assembly()
        now = datetime.now(UTC)
        made = [
            _make_record(
                selection_run_backend,
                assembly.id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                created_at=now - timedelta(minutes=10 * (5 - i)),
            )
            for i in range(5)
        ]

        recent = selection_run_backend.repo.get_recent_for_assembly(
            assembly.id, task_type=SelectionTaskType.SELECT_GSHEET, limit=3
        )
        assert [r.task_id for r in recent] == [made[4].task_id, made[3].task_id, made[2].task_id]

    def test_filters_by_task_type(self, selection_run_backend: ContractBackend):
        """Only records of the requested task type are returned."""
        assembly = selection_run_backend.make_assembly()
        now = datetime.now(UTC)
        select_record = _make_record(
            selection_run_backend,
            assembly.id,
            task_type=SelectionTaskType.SELECT_GSHEET,
            created_at=now - timedelta(hours=2),
        )
        _make_record(
            selection_run_backend,
            assembly.id,
            task_type=SelectionTaskType.DELETE_OLD_TABS,
            created_at=now,
        )

        recent = selection_run_backend.repo.get_recent_for_assembly(
            assembly.id, task_type=SelectionTaskType.SELECT_GSHEET, limit=3
        )
        assert [r.task_id for r in recent] == [select_record.task_id]

    def test_scopes_to_assembly(self, selection_run_backend: ContractBackend):
        """Records from other assemblies are excluded."""
        a1 = selection_run_backend.make_assembly()
        a2 = selection_run_backend.make_assembly()
        mine = _make_record(selection_run_backend, a1.id, task_type=SelectionTaskType.SELECT_GSHEET)
        _make_record(selection_run_backend, a2.id, task_type=SelectionTaskType.SELECT_GSHEET)

        recent = selection_run_backend.repo.get_recent_for_assembly(
            a1.id, task_type=SelectionTaskType.SELECT_GSHEET, limit=3
        )
        assert [r.task_id for r in recent] == [mine.task_id]

    def test_returns_empty_when_none(self, selection_run_backend: ContractBackend):
        """No matching records yields an empty list."""
        recent = selection_run_backend.repo.get_recent_for_assembly(
            uuid.uuid4(), task_type=SelectionTaskType.SELECT_GSHEET, limit=3
        )
        assert recent == []


class TestDeleteOldForAssembly:
    def test_keeps_most_recent_n(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        now = datetime.now(UTC)
        # Insert 8 records, oldest first
        records = [
            _make_record(
                selection_run_backend,
                assembly.id,
                created_at=now - timedelta(minutes=10 * (8 - i)),
            )
            for i in range(8)
        ]

        deleted_count = selection_run_backend.repo.delete_old_for_assembly(assembly.id, keep=3)
        selection_run_backend.commit()

        assert deleted_count == 5
        remaining = list(selection_run_backend.repo.get_by_assembly_id(assembly.id))
        assert len(remaining) == 3
        # The three remaining should be the newest three (last three in records list)
        kept_ids = {r.task_id for r in remaining}
        expected_kept_ids = {r.task_id for r in records[-3:]}
        assert kept_ids == expected_kept_ids

    def test_does_not_touch_other_assemblies(self, selection_run_backend: ContractBackend):
        a = selection_run_backend.make_assembly()
        b = selection_run_backend.make_assembly()
        now = datetime.now(UTC)
        for i in range(5):
            _make_record(selection_run_backend, a.id, created_at=now - timedelta(minutes=10 * (5 - i)))
        b_records = [
            _make_record(selection_run_backend, b.id, created_at=now - timedelta(minutes=10 * (3 - i)))
            for i in range(3)
        ]

        deleted = selection_run_backend.repo.delete_old_for_assembly(a.id, keep=1)
        selection_run_backend.commit()

        assert deleted == 4
        remaining_b = list(selection_run_backend.repo.get_by_assembly_id(b.id))
        assert {r.task_id for r in remaining_b} == {r.task_id for r in b_records}

    def test_keep_larger_than_total_is_noop(self, selection_run_backend: ContractBackend):
        assembly = selection_run_backend.make_assembly()
        for _ in range(2):
            _make_record(selection_run_backend, assembly.id)

        deleted = selection_run_backend.repo.delete_old_for_assembly(assembly.id, keep=10)
        selection_run_backend.commit()

        assert deleted == 0
        assert len(list(selection_run_backend.repo.get_by_assembly_id(assembly.id))) == 2


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
