"""ABOUTME: Round-trip tests for the progress JSON column on SelectionRunRecord.
ABOUTME: Ensures the field survives persistence via the SQLAlchemy imperative mapping."""

import uuid

from opendlp.bootstrap import bootstrap
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType


class TestSelectionRunRecordProgress:
    def test_progress_round_trip(self, postgres_session_factory):
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        progress_payload = {
            "phase": "multiplicative_weights",
            "current": 45,
            "total": 200,
            "updated_at": "2026-04-09T16:00:00+00:00",
        }

        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Test Assembly"))
            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                status=SelectionRunStatus.RUNNING,
                progress=progress_payload,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        with bootstrap(session_factory=postgres_session_factory) as uow:
            loaded = uow.selection_run_records.get_by_task_id(task_id)
            assert loaded is not None
            assert loaded.progress == progress_payload

    def test_progress_defaults_to_none(self, postgres_session_factory):
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Test Assembly"))
            record = SelectionRunRecord(
                assembly_id=assembly_id,
                task_id=task_id,
                task_type=SelectionTaskType.SELECT_GSHEET,
                status=SelectionRunStatus.PENDING,
            )
            uow.selection_run_records.add(record)
            uow.commit()

        with bootstrap(session_factory=postgres_session_factory) as uow:
            loaded = uow.selection_run_records.get_by_task_id(task_id)
            assert loaded is not None
            assert loaded.progress is None
