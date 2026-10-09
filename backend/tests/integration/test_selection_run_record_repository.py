"""ABOUTME: Integration tests for the SelectionRunRecord repository queries that drive the writing guard.
ABOUTME: Checks get_unfinished_for_assembly against Postgres for status, task-type and ordering."""

import uuid
from datetime import UTC, datetime, timedelta

from opendlp.bootstrap import bootstrap
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.value_objects import WRITING_TASK_TYPES, SelectionRunStatus, SelectionTaskType


def _record(assembly_id, status, task_type, minutes_ago):
    return SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=uuid.uuid4(),
        status=status,
        task_type=task_type,
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )


class TestGetUnfinishedForAssembly:
    def _seed(self, session_factory):
        """Two assemblies, each with a mix of unfinished and finished records. Returns (a, b)."""
        a, b = uuid.uuid4(), uuid.uuid4()
        with bootstrap(session_factory=session_factory) as uow:
            uow.assemblies.add(Assembly(assembly_id=a, title="A"))
            uow.assemblies.add(Assembly(assembly_id=b, title="B"))
            for record in [
                _record(a, SelectionRunStatus.RUNNING, SelectionTaskType.SELECT_FROM_DB, minutes_ago=30),
                _record(a, SelectionRunStatus.PENDING, SelectionTaskType.LIST_OLD_TABS, minutes_ago=10),
                _record(a, SelectionRunStatus.PENDING, SelectionTaskType.DELETE_OLD_TABS, minutes_ago=20),
                _record(a, SelectionRunStatus.COMPLETED, SelectionTaskType.SELECT_GSHEET, minutes_ago=5),
                _record(a, SelectionRunStatus.FAILED, SelectionTaskType.SELECT_FROM_DB, minutes_ago=4),
                _record(a, SelectionRunStatus.CANCELLED, SelectionTaskType.SELECT_FROM_DB, minutes_ago=3),
                _record(b, SelectionRunStatus.RUNNING, SelectionTaskType.SELECT_GSHEET, minutes_ago=1),
            ]:
                uow.selection_run_records.add(record)
            uow.commit()
        return a, b

    def test_returns_only_unfinished_records_of_the_assembly_oldest_first(self, postgres_session_factory):
        """Finished records and other assemblies' records are left out; the oldest unfinished comes first."""
        a, _b = self._seed(postgres_session_factory)
        with bootstrap(session_factory=postgres_session_factory) as uow:
            found = uow.selection_run_records.get_unfinished_for_assembly(a)
            assert [r.task_type for r in found] == [
                SelectionTaskType.SELECT_FROM_DB,
                SelectionTaskType.DELETE_OLD_TABS,
                SelectionTaskType.LIST_OLD_TABS,
            ]
            assert all(r.assembly_id == a for r in found)

    def test_task_type_filter_leaves_out_read_only_records(self, postgres_session_factory):
        """Filtering to the writing task types hides the pending read-only tab listing."""
        a, _b = self._seed(postgres_session_factory)
        with bootstrap(session_factory=postgres_session_factory) as uow:
            found = uow.selection_run_records.get_unfinished_for_assembly(a, WRITING_TASK_TYPES)
            assert [r.task_type for r in found] == [
                SelectionTaskType.SELECT_FROM_DB,
                SelectionTaskType.DELETE_OLD_TABS,
            ]

    def test_empty_when_nothing_unfinished(self, postgres_session_factory):
        """An assembly whose runs have all finished has nothing unfinished."""
        assembly_id = uuid.uuid4()
        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Done"))
            uow.selection_run_records.add(
                _record(assembly_id, SelectionRunStatus.COMPLETED, SelectionTaskType.SELECT_FROM_DB, minutes_ago=1)
            )
            uow.commit()
        with bootstrap(session_factory=postgres_session_factory) as uow:
            assert uow.selection_run_records.get_unfinished_for_assembly(assembly_id) == []


class TestLockAssemblyForWrite:
    def test_lock_is_released_at_commit(self, postgres_session_factory):
        """A second unit of work can take the lock once the first has committed."""
        assembly_id = uuid.uuid4()
        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.lock_assembly_for_write(assembly_id)
            uow.commit()
        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.lock_assembly_for_write(assembly_id)
            uow.commit()
