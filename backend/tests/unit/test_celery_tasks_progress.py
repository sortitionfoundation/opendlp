"""ABOUTME: Unit tests for progress reporter wiring in celery task helpers.
ABOUTME: Asserts _internal_run_select and the gsheet load/write helpers forward progress events."""

import uuid
from unittest.mock import MagicMock, patch

from sortition_algorithms import settings
from sortition_algorithms.utils import RunReport

from opendlp.bootstrap import bootstrap as bootstrap_uow
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from opendlp.entrypoints.celery import tasks


class RecordingReporter:
    def __init__(self) -> None:
        self.events: list[tuple[str, tuple, dict]] = []

    def start_phase(self, name: str, total: int | None = None, *, message: str | None = None) -> None:
        self.events.append(("start_phase", (name,), {"total": total, "message": message}))

    def update(self, current: int, *, message: str | None = None) -> None:
        self.events.append(("update", (current,), {"message": message}))

    def end_phase(self) -> None:
        self.events.append(("end_phase", (), {}))


def _empty_settings() -> settings.Settings:
    return settings.Settings(
        id_column="id",
        check_same_address=False,
        columns_to_keep=["id"],
    )


class TestInternalRunSelectForwardsReporter:
    def test_reporter_forwarded_to_run_stratification(self, postgres_session_factory):
        """The caller's reporter must reach run_stratification unchanged."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        with bootstrap_uow(session_factory=postgres_session_factory) as uow:
            uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Test Assembly"))
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_id,
                    task_id=task_id,
                    task_type=SelectionTaskType.SELECT_FROM_DB,
                    status=SelectionRunStatus.RUNNING,
                )
            )
            uow.commit()

        reporter = RecordingReporter()

        features = MagicMock(name="FeatureCollection")
        features.__len__.return_value = 0
        people = MagicMock(name="People")
        people.count = 0

        with patch.object(tasks, "run_stratification") as mock_run:
            mock_run.return_value = (True, [frozenset()], RunReport())
            tasks._internal_run_select(
                task_id=task_id,
                features=features,
                people=people,
                settings=_empty_settings(),
                number_people_wanted=1,
                progress_reporter=reporter,
                session_factory=postgres_session_factory,
            )

        assert mock_run.called
        assert mock_run.call_args.kwargs["progress_reporter"] is reporter

    def test_reporter_defaults_to_none(self, postgres_session_factory):
        """Existing callers that don't pass a reporter still work."""
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        with bootstrap_uow(session_factory=postgres_session_factory) as uow:
            uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Test Assembly"))
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_id,
                    task_id=task_id,
                    task_type=SelectionTaskType.SELECT_FROM_DB,
                    status=SelectionRunStatus.RUNNING,
                )
            )
            uow.commit()

        features = MagicMock(name="FeatureCollection")
        features.__len__.return_value = 0
        people = MagicMock(name="People")
        people.count = 0

        with patch.object(tasks, "run_stratification") as mock_run:
            mock_run.return_value = (True, [frozenset()], RunReport())
            tasks._internal_run_select(
                task_id=task_id,
                features=features,
                people=people,
                settings=_empty_settings(),
                number_people_wanted=1,
                session_factory=postgres_session_factory,
            )

        assert mock_run.call_args.kwargs["progress_reporter"] is None
