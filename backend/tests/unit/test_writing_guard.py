"""ABOUTME: Unit tests for the one-writing-task-per-assembly guard over the fake unit of work.
ABOUTME: Every writing start and the reset refuse while a writing run is unfinished, and take the lock."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from opendlp.domain.assembly import Assembly, AssemblyGSheet, SelectionRunRecord
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.users import User
from opendlp.domain.value_objects import (
    WRITING_TASK_TYPES,
    GlobalRole,
    RespondentStatus,
    SelectionRunStatus,
    SelectionTaskType,
)
from opendlp.service_layer import respondent_service, sortition
from opendlp.service_layer.exceptions import InvalidSelection
from opendlp.service_layer.writing_guard import (
    SelectionAlreadyRunning,
    refuse_if_writing_run_unfinished,
    running_task_query_param,
)
from tests.data import VALID_GSHEET_URL
from tests.fakes import FakeUnitOfWork

READ_ONLY_TASK_TYPES = frozenset(SelectionTaskType) - WRITING_TASK_TYPES - {SelectionTaskType.RESET_TO_POOL}
FINISHED = (SelectionRunStatus.COMPLETED, SelectionRunStatus.FAILED, SelectionRunStatus.CANCELLED)
UNFINISHED = (SelectionRunStatus.PENDING, SelectionRunStatus.RUNNING)

SNAPSHOT = [
    {
        "name": "Gender",
        "sort_order": 0,
        "comment": "",
        "source_url": "",
        "values": [{"value": "Male", "min": 2, "max": 3, "overall_min": 5, "overall_max": 6, "held": 3}],
    }
]
INFO = {"number_to_select_overall": 10, "held_total": 6, "calculated_number": 4, "number_to_select_used": 4}


def _setup(uow: FakeUnitOfWork) -> tuple[User, Assembly]:
    """An admin and an assembly configured for both Google Sheets and database selection."""
    admin = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.fake_users.add(admin)
    assembly = Assembly(title="Test Assembly", number_to_select=10)
    assembly.csv = AssemblyCSV(assembly_id=assembly.id)
    assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
    uow.fake_assemblies.add(assembly)
    uow.fake_assembly_gsheets.add(AssemblyGSheet(assembly_id=assembly.id, url=VALID_GSHEET_URL))
    return admin, assembly


def _add_record(uow: FakeUnitOfWork, assembly_id, task_type, status, minutes_ago=5) -> SelectionRunRecord:
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=uuid.uuid4(),
        task_type=task_type,
        status=status,
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    uow.fake_selection_run_records.add(record)
    return record


# Each writing start: a label, the call, and the Celery entry point it dispatches through.
STARTS = [
    pytest.param(
        lambda uow, admin, assembly: sortition.start_gsheet_select_task(uow, admin.id, assembly.id),
        "opendlp.service_layer.sortition.tasks.run_select.apply_async",
        id="gsheet_select",
    ),
    pytest.param(
        lambda uow, admin, assembly: sortition.start_gsheet_select_task(uow, admin.id, assembly.id, True),
        "opendlp.service_layer.sortition.tasks.run_select.apply_async",
        id="gsheet_test_select",
    ),
    pytest.param(
        lambda uow, admin, assembly: sortition.start_gsheet_replace_task(uow, admin.id, assembly.id, 3),
        "opendlp.service_layer.sortition.tasks.run_select.delay",
        id="gsheet_replace",
    ),
    pytest.param(
        lambda uow, admin, assembly: sortition.start_gsheet_manage_tabs_task(uow, admin.id, assembly.id, False),
        "opendlp.service_layer.sortition.tasks.manage_old_tabs.delay",
        id="gsheet_delete_tabs",
    ),
    pytest.param(
        lambda uow, admin, assembly: sortition.start_db_select_task(uow, admin.id, assembly.id),
        "opendlp.service_layer.sortition.tasks.run_select_from_db.delay",
        id="db_select",
    ),
    pytest.param(
        lambda uow, admin, assembly: sortition.start_db_select_task(uow, admin.id, assembly.id, True),
        "opendlp.service_layer.sortition.tasks.run_select_from_db.delay",
        id="db_test_select",
    ),
    pytest.param(
        lambda uow, admin, assembly: sortition.start_db_replace_task(uow, admin.id, assembly.id, 4, SNAPSHOT, INFO),
        "opendlp.service_layer.sortition.tasks.run_select_from_db.delay",
        id="db_replace",
    ),
]


@pytest.mark.parametrize(("start", "dispatch"), STARTS)
class TestWritingStartsRefuseWhileAWritingRunIsUnfinished:
    @pytest.mark.parametrize("blocking_type", sorted(WRITING_TASK_TYPES, key=lambda t: t.value))
    @pytest.mark.parametrize("blocking_status", UNFINISHED)
    def test_refused_adds_no_record_and_dispatches_nothing(self, uow, start, dispatch, blocking_type, blocking_status):
        """Any unfinished writing run on the assembly refuses the start, and nothing else happens."""
        admin, assembly = _setup(uow)
        blocking = _add_record(uow, assembly.id, blocking_type, blocking_status)

        with patch(dispatch) as mock_dispatch, pytest.raises(SelectionAlreadyRunning) as exc_info:
            start(uow, admin, assembly)

        mock_dispatch.assert_not_called()
        assert len(uow.fake_selection_run_records._items) == 1
        assert exc_info.value.task_id == blocking.task_id
        assert exc_info.value.task_type == blocking_type
        assert blocking.task_type_verbose in str(exc_info.value)
        assert uow.locked_assembly_ids == [assembly.id]

    @pytest.mark.parametrize("blocking_type", sorted(READ_ONLY_TASK_TYPES, key=lambda t: t.value))
    def test_runs_alongside_a_read_only_task(self, uow, start, dispatch, blocking_type):
        """A pending read-only task on the assembly never blocks a writer."""
        admin, assembly = _setup(uow)
        _add_record(uow, assembly.id, blocking_type, SelectionRunStatus.RUNNING)

        with patch(dispatch) as mock_dispatch:
            mock_dispatch.return_value = Mock(id="celery-id")
            start(uow, admin, assembly)

        mock_dispatch.assert_called_once()

    @pytest.mark.parametrize("blocking_status", FINISHED)
    def test_runs_after_a_writing_run_has_finished(self, uow, start, dispatch, blocking_status):
        """A finished writing run, whatever its outcome, no longer holds the assembly."""
        admin, assembly = _setup(uow)
        _add_record(uow, assembly.id, SelectionTaskType.SELECT_FROM_DB, blocking_status)

        with patch(dispatch) as mock_dispatch:
            mock_dispatch.return_value = Mock(id="celery-id")
            start(uow, admin, assembly)

        mock_dispatch.assert_called_once()

    def test_runs_while_another_assembly_is_writing(self, uow, start, dispatch):
        """A running selection on a different assembly is not this assembly's business."""
        admin, assembly = _setup(uow)
        _add_record(uow, uuid.uuid4(), SelectionTaskType.SELECT_FROM_DB, SelectionRunStatus.RUNNING)

        with patch(dispatch) as mock_dispatch:
            mock_dispatch.return_value = Mock(id="celery-id")
            start(uow, admin, assembly)

        mock_dispatch.assert_called_once()
        assert uow.locked_assembly_ids == [assembly.id]


class TestListingOldTabsIsNeverRefused:
    def test_dry_run_list_runs_during_a_selection(self, uow):
        """Listing old tabs only reads the spreadsheet, so a running selection does not stop it."""
        admin, assembly = _setup(uow)
        _add_record(uow, assembly.id, SelectionTaskType.SELECT_GSHEET, SelectionRunStatus.RUNNING)

        with patch("opendlp.service_layer.sortition.tasks.manage_old_tabs.delay") as mock_dispatch:
            mock_dispatch.return_value = Mock(id="celery-id")
            sortition.start_gsheet_manage_tabs_task(uow, admin.id, assembly.id, dry_run=True)

        mock_dispatch.assert_called_once()
        assert uow.locked_assembly_ids == []


class TestResetToPoolIsRefusedDuringASelection:
    def _respondent(self, uow, assembly_id):
        respondent = Respondent(
            assembly_id=assembly_id,
            external_id="R1",
            attributes={},
            selection_status=RespondentStatus.SELECTED,
        )
        uow.fake_respondents.add(respondent)
        return respondent

    @pytest.mark.parametrize("blocking_status", UNFINISHED)
    def test_refused_changes_nothing(self, uow, blocking_status):
        """A reset during a database selection is refused, leaving respondents and history untouched."""
        admin, assembly = _setup(uow)
        respondent = self._respondent(uow, assembly.id)
        _add_record(uow, assembly.id, SelectionTaskType.SELECT_FROM_DB, blocking_status)

        with pytest.raises(SelectionAlreadyRunning):
            respondent_service.reset_selection_status(uow, admin.id, assembly.id)

        assert respondent.selection_status == RespondentStatus.SELECTED
        assert len(uow.fake_selection_run_records._items) == 1
        assert uow.locked_assembly_ids == [assembly.id]

    def test_runs_once_the_selection_has_finished(self, uow):
        """After the selection completes the reset goes ahead and records itself."""
        admin, assembly = _setup(uow)
        respondent = self._respondent(uow, assembly.id)
        _add_record(uow, assembly.id, SelectionTaskType.SELECT_FROM_DB, SelectionRunStatus.COMPLETED)

        count = respondent_service.reset_selection_status(uow, admin.id, assembly.id)

        assert count == 1
        assert respondent.selection_status == RespondentStatus.POOL
        assert [r.task_type for r in uow.fake_selection_run_records._items] == [
            SelectionTaskType.SELECT_FROM_DB,
            SelectionTaskType.RESET_TO_POOL,
        ]


class TestRefuseIfWritingRunUnfinished:
    def test_names_the_oldest_unfinished_writer(self, uow):
        """With two unfinished writers the exception carries the one that started first."""
        assembly_id = uuid.uuid4()
        older = _add_record(uow, assembly_id, SelectionTaskType.DELETE_OLD_TABS, SelectionRunStatus.RUNNING, 30)
        _add_record(uow, assembly_id, SelectionTaskType.SELECT_GSHEET, SelectionRunStatus.PENDING, 1)

        with uow, pytest.raises(SelectionAlreadyRunning) as exc_info:
            refuse_if_writing_run_unfinished(uow, assembly_id)

        assert exc_info.value.task_id == older.task_id

    def test_is_an_invalid_selection(self, uow):
        """Existing `except InvalidSelection` handlers keep catching the refusal."""
        assembly_id = uuid.uuid4()
        _add_record(uow, assembly_id, SelectionTaskType.SELECT_GSHEET, SelectionRunStatus.PENDING)
        with uow, pytest.raises(InvalidSelection):
            refuse_if_writing_run_unfinished(uow, assembly_id)

    def test_nothing_unfinished_passes_but_still_locks(self, uow):
        """The lock is taken even when nothing blocks, so the insert that follows is serialised."""
        assembly_id = uuid.uuid4()
        with uow:
            refuse_if_writing_run_unfinished(uow, assembly_id)
        assert uow.locked_assembly_ids == [assembly_id]


class TestActiveInitialSelectionSeesPastNewerReadOnlyRecords:
    def test_running_selection_found_behind_a_newer_tab_listing(self, uow):
        """A read-only task started after the selection no longer hides the running selection."""
        assembly = Assembly(title="Test Assembly")
        uow.fake_assemblies.add(assembly)
        selection = _add_record(uow, assembly.id, SelectionTaskType.SELECT_GSHEET, SelectionRunStatus.RUNNING, 10)
        _add_record(uow, assembly.id, SelectionTaskType.LIST_OLD_TABS, SelectionRunStatus.PENDING, 1)

        with uow:
            assert sortition.get_active_initial_selection_run_id(uow, assembly.id) == selection.task_id

    def test_running_selection_found_behind_a_newer_finished_run(self, uow):
        """An older run still going is found even when a newer one has already finished."""
        assembly = Assembly(title="Test Assembly")
        uow.fake_assemblies.add(assembly)
        selection = _add_record(uow, assembly.id, SelectionTaskType.SELECT_FROM_DB, SelectionRunStatus.RUNNING, 10)
        _add_record(uow, assembly.id, SelectionTaskType.SELECT_FROM_DB, SelectionRunStatus.FAILED, 1)

        with uow:
            assert sortition.get_active_initial_selection_run_id(uow, assembly.id) == selection.task_id


class TestRunningTaskQueryParam:
    @pytest.mark.parametrize("task_type", sorted(WRITING_TASK_TYPES, key=lambda t: t.value))
    def test_every_writing_task_type_opens_a_modal(self, task_type):
        """A writing task type added without a modal parameter fails here, not in a user's browser."""
        assert running_task_query_param(task_type) in {
            "current_selection",
            "current_replacement",
            "current_manage_tabs",
        }

    def test_known_mappings(self):
        assert running_task_query_param(SelectionTaskType.SELECT_REPLACEMENT_GSHEET) == "current_replacement"
        assert running_task_query_param(SelectionTaskType.DELETE_OLD_TABS) == "current_manage_tabs"
        assert running_task_query_param(SelectionTaskType.SELECT_REPLACEMENT_FROM_DB) == "current_selection"
