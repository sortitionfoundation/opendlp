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


class TestInternalLoadGsheetEmitsReadPhase:
    def _seed(self, session_factory):
        task_id = uuid.uuid4()
        assembly_id = uuid.uuid4()
        with bootstrap_uow(session_factory=session_factory) as uow:
            uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Test Assembly"))
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_id,
                    task_id=task_id,
                    task_type=SelectionTaskType.LOAD_GSHEET,
                    status=SelectionRunStatus.PENDING,
                )
            )
            uow.commit()
        return task_id

    def test_load_gsheet_emits_read_gsheet_phase(self, postgres_session_factory):
        task_id = self._seed(postgres_session_factory)
        reporter = RecordingReporter()

        select_data = MagicMock(name="SelectionData")
        select_data.data_source = MagicMock(spec=tasks.adapters.GSheetDataSource)
        select_data.data_source.spreadsheet.title = "Fake Spreadsheet"
        select_data.data_source.feature_tab_name = "Features"
        select_data.data_source.people_tab_name = "People"
        select_data.data_source.already_selected_tab_name = ""

        features = MagicMock(name="features")
        features.__len__.return_value = 0
        features.values.return_value = []
        people_loaded = MagicMock(name="people")
        people_loaded.count = 0
        already_selected = MagicMock(name="already_selected")
        already_selected.count = 0

        select_data.load_features.return_value = (features, RunReport())
        select_data.load_people.return_value = (people_loaded, RunReport())
        select_data.load_already_selected.return_value = (already_selected, RunReport())

        task_obj = MagicMock(name="task")

        with (
            patch("opendlp.entrypoints.celery.tasks.minimum_selection", return_value=0),
            patch("opendlp.entrypoints.celery.tasks.maximum_selection", return_value=0),
        ):
            tasks._internal_load_gsheet(
                task_obj=task_obj,
                task_id=task_id,
                select_data=select_data,
                settings=_empty_settings(),
                final_task=False,
                session_factory=postgres_session_factory,
                progress_reporter=reporter,
            )

        read_phase_events = [e for e in reporter.events if e[0] == "start_phase" and e[1][0] == "read_gsheet"]
        assert read_phase_events, f"expected a read_gsheet start_phase, got: {reporter.events}"
        assert read_phase_events[0][2]["total"] is None
