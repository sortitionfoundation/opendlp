"""ABOUTME: Unit tests for the fake SelectionRunRecord repository query behind the writing guard.
ABOUTME: Keeps the fake's get_unfinished_for_assembly in step with the SQL implementation."""

import uuid
from datetime import UTC, datetime, timedelta

from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.value_objects import WRITING_TASK_TYPES, SelectionRunStatus, SelectionTaskType
from tests.fakes import FakeUnitOfWork


def _record(assembly_id, status, task_type, minutes_ago):
    return SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=uuid.uuid4(),
        status=status,
        task_type=task_type,
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )


class TestFakeGetUnfinishedForAssembly:
    def test_filters_by_assembly_status_and_task_type_oldest_first(self):
        """The fake applies the same three filters and ordering as the SQL repository."""
        a, b = uuid.uuid4(), uuid.uuid4()
        uow = FakeUnitOfWork()
        for record in [
            _record(a, SelectionRunStatus.RUNNING, SelectionTaskType.SELECT_FROM_DB, minutes_ago=30),
            _record(a, SelectionRunStatus.PENDING, SelectionTaskType.LIST_OLD_TABS, minutes_ago=10),
            _record(a, SelectionRunStatus.PENDING, SelectionTaskType.DELETE_OLD_TABS, minutes_ago=20),
            _record(a, SelectionRunStatus.COMPLETED, SelectionTaskType.SELECT_GSHEET, minutes_ago=5),
            _record(b, SelectionRunStatus.RUNNING, SelectionTaskType.SELECT_GSHEET, minutes_ago=1),
        ]:
            uow.fake_selection_run_records.add(record)

        with uow:
            everything = uow.selection_run_records.get_unfinished_for_assembly(a)
            writers = uow.selection_run_records.get_unfinished_for_assembly(a, WRITING_TASK_TYPES)

        assert [r.task_type for r in everything] == [
            SelectionTaskType.SELECT_FROM_DB,
            SelectionTaskType.DELETE_OLD_TABS,
            SelectionTaskType.LIST_OLD_TABS,
        ]
        assert [r.task_type for r in writers] == [SelectionTaskType.SELECT_FROM_DB, SelectionTaskType.DELETE_OLD_TABS]

    def test_lock_call_is_recorded(self):
        """The fake lock does nothing but remember which assembly was locked."""
        assembly_id = uuid.uuid4()
        uow = FakeUnitOfWork()
        with uow:
            uow.lock_assembly_for_write(assembly_id)
        assert uow.locked_assembly_ids == [assembly_id]
