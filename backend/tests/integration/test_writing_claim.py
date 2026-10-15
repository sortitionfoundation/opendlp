"""ABOUTME: Integration tests for the worker-side claim that a writing task makes before touching data.
ABOUTME: A task whose assembly is held by another writing run fails itself and changes nothing."""

import uuid
from unittest.mock import patch

import pytest
from sortition_algorithms import RunReport
from sortition_algorithms.settings import Settings

from opendlp import config
from opendlp.bootstrap import bootstrap
from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, RespondentStatus, SelectionRunStatus, SelectionTaskType
from opendlp.entrypoints.celery.tasks import (
    _claim_assembly_for_writing,
    manage_old_tabs,
    run_select,
    run_select_from_db,
)
from opendlp.service_layer.exceptions import SelectionRunRecordNotFoundError

BLOCKED_MESSAGE = "Another task was already writing to this assembly when this one started"


@pytest.fixture
def test_settings():
    return Settings(
        id_column="external_id",
        check_same_address=False,
        columns_to_keep=[],
        solver_backend=config.get_solver_backend(),
    )


def _add_assembly(session_factory, number_to_select=0) -> uuid.UUID:
    assembly_id = uuid.uuid4()
    with bootstrap(session_factory=session_factory) as uow:
        uow.assemblies.add(Assembly(assembly_id=assembly_id, title="Claim Test", number_to_select=number_to_select))
        uow.commit()
    return assembly_id


def _add_record(session_factory, assembly_id, task_type, status, with_user=False) -> uuid.UUID:
    """A run record; ``with_user`` gives it the user id the database write stage insists on."""
    task_id = uuid.uuid4()
    with bootstrap(session_factory=session_factory) as uow:
        user_id = None
        if with_user:
            user = User(
                email=f"runner-{uuid.uuid4().hex[:6]}@example.com",
                global_role=GlobalRole.ADMIN,
                password_hash="hash",  # pragma: allowlist secret
            )
            uow.users.add(user)
            uow.flush()
            user_id = user.id
        uow.selection_run_records.add(
            SelectionRunRecord(
                assembly_id=assembly_id, task_id=task_id, task_type=task_type, status=status, user_id=user_id
            )
        )
        uow.commit()
    return task_id


def _record(session_factory, task_id) -> dict:
    """The fields of the record the tests look at, read in a session of their own."""
    with bootstrap(session_factory=session_factory) as uow:
        record = uow.selection_run_records.get_by_task_id(task_id)
        assert record is not None
        return {
            "status": record.status,
            "error_message": record.error_message,
            "log_messages": list(record.log_messages),
            "completed_at": record.completed_at,
        }


def _add_pool(session_factory, assembly_id) -> None:
    """A Gender category and four pool respondents, enough for a two-person selection."""
    with bootstrap(session_factory=session_factory) as uow:
        cat = TargetCategory(assembly_id=assembly_id, name="Gender")
        cat.add_value(TargetValue(value="Male", min=1, max=1))
        cat.add_value(TargetValue(value="Female", min=1, max=1))
        uow.target_categories.add(cat)
        for ext_id, gender in [("NB001", "Male"), ("NB002", "Male"), ("NB003", "Female"), ("NB004", "Female")]:
            uow.respondents.add(
                Respondent(
                    assembly_id=assembly_id,
                    external_id=ext_id,
                    attributes={"Gender": gender},
                    eligible=True,
                    can_attend=True,
                    selection_status=RespondentStatus.POOL,
                )
            )
        uow.commit()


class TestClaimAssemblyForWriting:
    def test_claim_moves_a_free_assembly_to_running(self, postgres_session_factory):
        """With nothing else unfinished the record goes PENDING to RUNNING and the claim succeeds."""
        assembly_id = _add_assembly(postgres_session_factory)
        task_id = _add_record(
            postgres_session_factory, assembly_id, SelectionTaskType.SELECT_FROM_DB, SelectionRunStatus.PENDING
        )
        report = RunReport()

        assert _claim_assembly_for_writing(task_id, report, session_factory=postgres_session_factory) is True
        assert _record(postgres_session_factory, task_id)["status"] == SelectionRunStatus.RUNNING

    def test_claim_fails_the_run_when_another_writer_is_unfinished(self, postgres_session_factory):
        """A held assembly fails this run with a message naming the task that holds it."""
        assembly_id = _add_assembly(postgres_session_factory)
        _add_record(
            postgres_session_factory, assembly_id, SelectionTaskType.DELETE_OLD_TABS, SelectionRunStatus.RUNNING
        )
        task_id = _add_record(
            postgres_session_factory, assembly_id, SelectionTaskType.SELECT_GSHEET, SelectionRunStatus.PENDING
        )
        report = RunReport()

        assert _claim_assembly_for_writing(task_id, report, session_factory=postgres_session_factory) is False

        record = _record(postgres_session_factory, task_id)
        assert record["status"] == SelectionRunStatus.FAILED
        assert record["completed_at"] is not None
        assert BLOCKED_MESSAGE in record["error_message"]
        assert "Delete old tabs" in record["error_message"]
        assert any(BLOCKED_MESSAGE in msg for msg in record["log_messages"])
        assert any(BLOCKED_MESSAGE in line for line in report.as_text().splitlines())

    def test_claim_ignores_read_only_and_finished_runs(self, postgres_session_factory):
        """A pending tab listing and a finished selection do not hold the assembly."""
        assembly_id = _add_assembly(postgres_session_factory)
        _add_record(postgres_session_factory, assembly_id, SelectionTaskType.LIST_OLD_TABS, SelectionRunStatus.PENDING)
        _add_record(postgres_session_factory, assembly_id, SelectionTaskType.SELECT_FROM_DB, SelectionRunStatus.FAILED)
        task_id = _add_record(
            postgres_session_factory, assembly_id, SelectionTaskType.SELECT_FROM_DB, SelectionRunStatus.PENDING
        )

        assert _claim_assembly_for_writing(task_id, RunReport(), session_factory=postgres_session_factory) is True

    def test_claim_ignores_another_assembly(self, postgres_session_factory):
        """A running selection elsewhere is not this assembly's business."""
        other = _add_assembly(postgres_session_factory)
        _add_record(postgres_session_factory, other, SelectionTaskType.SELECT_FROM_DB, SelectionRunStatus.RUNNING)
        assembly_id = _add_assembly(postgres_session_factory)
        task_id = _add_record(
            postgres_session_factory, assembly_id, SelectionTaskType.SELECT_FROM_DB, SelectionRunStatus.PENDING
        )

        assert _claim_assembly_for_writing(task_id, RunReport(), session_factory=postgres_session_factory) is True

    def test_claim_leaves_a_record_that_is_no_longer_pending_alone(self, postgres_session_factory):
        """A record the cleanup job failed as stuck, or the user cancelled, is not brought back to RUNNING."""
        assembly_id = _add_assembly(postgres_session_factory)
        for status in (SelectionRunStatus.FAILED, SelectionRunStatus.CANCELLED):
            task_id = _add_record(postgres_session_factory, assembly_id, SelectionTaskType.SELECT_FROM_DB, status)
            report = RunReport()

            assert _claim_assembly_for_writing(task_id, report, session_factory=postgres_session_factory) is False

            record = _record(postgres_session_factory, task_id)
            assert record["status"] == status
            assert record["error_message"] == ""
            assert "cancelled or failed before it started" in report.as_text()

    def test_claim_without_a_record_raises(self, postgres_session_factory):
        with pytest.raises(SelectionRunRecordNotFoundError):
            _claim_assembly_for_writing(uuid.uuid4(), RunReport(), session_factory=postgres_session_factory)


class TestRunSelectFromDbRefusesAHeldAssembly:
    def test_held_assembly_fails_the_run_and_selects_nobody(self, postgres_session_factory, test_settings):
        """The task returns its failure tuple and no respondent leaves the pool."""
        assembly_id = _add_assembly(postgres_session_factory, number_to_select=2)
        _add_pool(postgres_session_factory, assembly_id)
        _add_record(
            postgres_session_factory,
            assembly_id,
            SelectionTaskType.SELECT_REPLACEMENT_FROM_DB,
            SelectionRunStatus.RUNNING,
        )
        task_id = _add_record(
            postgres_session_factory, assembly_id, SelectionTaskType.SELECT_FROM_DB, SelectionRunStatus.PENDING
        )

        with patch.object(run_select_from_db, "update_state"):
            success, panels, report = run_select_from_db(
                task_id=task_id,
                assembly_id=assembly_id,
                number_people_wanted=2,
                settings=test_settings,
                session_factory=postgres_session_factory,
            )

        assert success is False
        assert panels == []
        assert BLOCKED_MESSAGE in report.as_text()
        assert _record(postgres_session_factory, task_id)["status"] == SelectionRunStatus.FAILED
        with bootstrap(session_factory=postgres_session_factory) as uow:
            statuses = {r.selection_status for r in uow.respondents.get_by_assembly_id(assembly_id)}
        assert statuses == {RespondentStatus.POOL}

    def test_free_assembly_runs_as_before(self, postgres_session_factory, test_settings):
        """A finished earlier run does not get in the way of a new selection."""
        assembly_id = _add_assembly(postgres_session_factory, number_to_select=2)
        _add_pool(postgres_session_factory, assembly_id)
        _add_record(
            postgres_session_factory, assembly_id, SelectionTaskType.SELECT_FROM_DB, SelectionRunStatus.COMPLETED
        )
        task_id = _add_record(
            postgres_session_factory,
            assembly_id,
            SelectionTaskType.SELECT_FROM_DB,
            SelectionRunStatus.PENDING,
            with_user=True,
        )

        with patch.object(run_select_from_db, "update_state"):
            success, panels, _report = run_select_from_db(
                task_id=task_id,
                assembly_id=assembly_id,
                number_people_wanted=2,
                settings=test_settings,
                session_factory=postgres_session_factory,
            )

        assert success is True, _report.as_text()
        assert len(panels[0]) == 2
        assert _record(postgres_session_factory, task_id)["status"] == SelectionRunStatus.COMPLETED


class TestGsheetTasksRefuseAHeldAssembly:
    def test_run_select_held_assembly_writes_no_tabs(
        self, postgres_session_factory, csv_gsheet_data_source, test_settings, csv_files
    ):
        """The spreadsheet-backed selection fails before reading, and the output files never appear."""
        assembly_id = _add_assembly(postgres_session_factory)
        _add_record(postgres_session_factory, assembly_id, SelectionTaskType.SELECT_GSHEET, SelectionRunStatus.PENDING)
        task_id = _add_record(
            postgres_session_factory, assembly_id, SelectionTaskType.TEST_SELECT_GSHEET, SelectionRunStatus.PENDING
        )

        with patch.object(run_select, "update_state"):
            success, panels, report = run_select(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                number_people_wanted=22,
                settings=test_settings,
                test_selection=True,
                session_factory=postgres_session_factory,
            )

        assert success is False
        assert panels == []
        assert BLOCKED_MESSAGE in report.as_text()
        assert _record(postgres_session_factory, task_id)["status"] == SelectionRunStatus.FAILED
        assert not csv_files["selected"].exists()

    def test_delete_old_tabs_held_assembly_deletes_nothing(self, postgres_session_factory, csv_gsheet_data_source):
        """Deleting tabs is refused while a selection is running, and the old tabs survive."""
        csv_gsheet_data_source.add_simulated_old_tab("Original Selected - output - 2024-01-01")
        assembly_id = _add_assembly(postgres_session_factory)
        _add_record(postgres_session_factory, assembly_id, SelectionTaskType.SELECT_GSHEET, SelectionRunStatus.RUNNING)
        task_id = _add_record(
            postgres_session_factory, assembly_id, SelectionTaskType.DELETE_OLD_TABS, SelectionRunStatus.PENDING
        )

        with patch.object(manage_old_tabs, "update_state"):
            success, tab_names, _report = manage_old_tabs(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                dry_run=False,
                session_factory=postgres_session_factory,
            )

        assert success is False
        assert tab_names == []
        assert len(csv_gsheet_data_source._simulated_old_tabs) == 1
        assert _record(postgres_session_factory, task_id)["status"] == SelectionRunStatus.FAILED

    def test_list_old_tabs_is_not_blocked(self, postgres_session_factory, csv_gsheet_data_source):
        """Listing only reads the spreadsheet, so a running selection does not stop it."""
        csv_gsheet_data_source.add_simulated_old_tab("Original Selected - output - 2024-01-01")
        assembly_id = _add_assembly(postgres_session_factory)
        _add_record(postgres_session_factory, assembly_id, SelectionTaskType.SELECT_GSHEET, SelectionRunStatus.RUNNING)
        task_id = _add_record(
            postgres_session_factory, assembly_id, SelectionTaskType.LIST_OLD_TABS, SelectionRunStatus.PENDING
        )

        with patch.object(manage_old_tabs, "update_state"):
            success, tab_names, _report = manage_old_tabs(
                task_id=task_id,
                data_source=csv_gsheet_data_source,
                dry_run=True,
                session_factory=postgres_session_factory,
            )

        assert success is True
        assert tab_names == ["Original Selected - output - 2024-01-01"]
        assert _record(postgres_session_factory, task_id)["status"] == SelectionRunStatus.COMPLETED
