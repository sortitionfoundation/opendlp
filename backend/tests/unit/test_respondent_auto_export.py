# ABOUTME: Unit tests for scheduling and running the automatic respondent export
# ABOUTME: Fake UnitOfWork, an in-memory Redis stand-in and the recording task runner

import uuid
from unittest.mock import patch

import pytest
import structlog

from opendlp.adapters.tabular_export import ExportTargetError
from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet
from opendlp.domain.events import RespondentsChanged, RespondentSchemaChanged
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import GSheetExportKind, RespondentStatus
from opendlp.service_layer import handlers, respondent_auto_export
from opendlp.service_layer.respondent_auto_export import (
    AUTO_EXPORT_DELAY_SECONDS,
    handle_respondents_changed,
    pending_key,
    run_auto_export,
    schedule_auto_export,
)
from tests.fakes import FakeGSheetExportTarget, FakeRedis, FakeStore, FakeUnitOfWork, SubmittedTask

_SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"


class _BrokenRedis:
    def set(self, *args, **kwargs):
        raise ConnectionError("redis is down")


def _assembly_with_config(uow: FakeUnitOfWork, *, auto_export: bool, status_filter: str = "") -> Assembly:
    assembly = Assembly(title="Test Assembly")
    uow.assemblies.add(assembly)
    uow.assembly_export_gsheets.add(
        AssemblyExportGSheet(
            assembly_id=assembly.id,
            export_kind=GSheetExportKind.RESPONDENTS,
            url=_SHEET_URL,
            worksheet_name="Auto tab",
            auto_export=auto_export,
            auto_export_status_filter=status_filter,
        )
    )
    return assembly


def _add_respondent(uow: FakeUnitOfWork, assembly: Assembly, external_id: str, status: RespondentStatus) -> None:
    uow.respondents.add(Respondent(assembly_id=assembly.id, external_id=external_id, selection_status=status))


@pytest.fixture
def scheduling(task_runner):
    """Redis replaced by a fresh in-memory fake; yields the task runner the export is sent to."""
    with patch.object(respondent_auto_export, "_get_redis", return_value=FakeRedis()):
        yield task_runner


class TestHandleRespondentsChanged:
    """Called directly with a fake UnitOfWork, whose after-commit callbacks run on commit()."""

    @pytest.mark.parametrize("event_class", [RespondentsChanged, RespondentSchemaChanged])
    def test_schedules_the_export_once_the_work_commits(self, uow, scheduling, event_class):
        assembly = _assembly_with_config(uow, auto_export=True)

        handle_respondents_changed(event_class(assembly.id), uow, task_runner=scheduling)

        assert scheduling.submitted == []
        uow.commit()
        assert len(scheduling.submitted) == 1
        assert scheduling.submitted[0].kwargs == {"assembly_id": assembly.id}

    def test_schedules_nothing_when_the_work_rolls_back(self, scheduling):
        uow = FakeUnitOfWork(FakeStore())
        with uow:
            assembly = _assembly_with_config(uow, auto_export=True)
            uow.commit()
            handle_respondents_changed(RespondentsChanged(assembly.id), uow, task_runner=scheduling)
            uow.rollback()
            uow.commit()

        assert scheduling.submitted == []

    def test_no_config_schedules_nothing(self, uow, scheduling):
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)

        handle_respondents_changed(RespondentsChanged(assembly.id), uow, task_runner=scheduling)
        uow.commit()

        assert scheduling.submitted == []

    def test_auto_export_off_schedules_nothing(self, uow, scheduling):
        assembly = _assembly_with_config(uow, auto_export=False)

        handle_respondents_changed(RespondentsChanged(assembly.id), uow, task_runner=scheduling)
        uow.commit()

        assert scheduling.submitted == []

    def test_several_changes_in_one_unit_of_work_schedule_one_export(self, uow, scheduling):
        assembly = _assembly_with_config(uow, auto_export=True)

        handle_respondents_changed(RespondentsChanged(assembly.id), uow, task_runner=scheduling)
        handle_respondents_changed(RespondentSchemaChanged(assembly.id), uow, task_runner=scheduling)
        uow.commit()

        assert len(scheduling.submitted) == 1

    @pytest.mark.parametrize("event_class", [RespondentsChanged, RespondentSchemaChanged])
    def test_is_registered_for_the_event(self, task_runner, event_class):
        (handler,) = handlers.build_event_handlers(task_runner)[event_class]
        assert handler.func is handle_respondents_changed
        assert handler.keywords == {"task_runner": task_runner}

    def test_recording_the_event_with_the_application_handlers_schedules_the_export(self, scheduling):
        uow = FakeUnitOfWork(event_handlers=handlers.build_event_handlers(scheduling))

        with uow:
            assembly = _assembly_with_config(uow, auto_export=True)
            uow.record(RespondentsChanged(assembly.id))
            assert scheduling.submitted == []

        assert len(scheduling.submitted) == 1


class TestScheduleAutoExport:
    def test_queues_the_task_with_a_delay_and_marks_it_pending(self, task_runner):
        assembly_id = uuid.uuid4()
        redis = FakeRedis()

        assert schedule_auto_export(assembly_id, task_runner, redis_client=redis) is True

        assert task_runner.submitted == [
            SubmittedTask(
                name="auto_export_respondents",
                kwargs={"assembly_id": assembly_id},
                options={"countdown": AUTO_EXPORT_DELAY_SECONDS},
            )
        ]
        assert redis.get(pending_key(assembly_id)) is not None

    def test_a_second_request_while_one_is_pending_queues_nothing(self, task_runner):
        assembly_id = uuid.uuid4()
        redis = FakeRedis()

        schedule_auto_export(assembly_id, task_runner, redis_client=redis)
        assert schedule_auto_export(assembly_id, task_runner, redis_client=redis) is False

        assert len(task_runner.submitted) == 1

    def test_assemblies_are_debounced_separately(self, task_runner):
        redis = FakeRedis()

        schedule_auto_export(uuid.uuid4(), task_runner, redis_client=redis)
        schedule_auto_export(uuid.uuid4(), task_runner, redis_client=redis)

        assert len(task_runner.submitted) == 2

    def test_redis_failure_is_logged_and_swallowed(self, task_runner):
        with structlog.testing.capture_logs() as logs:
            assert schedule_auto_export(uuid.uuid4(), task_runner, redis_client=_BrokenRedis()) is False

        assert task_runner.submitted == []
        assert [(log["event"], log["error"]) for log in logs] == [
            ("Could not schedule automatic export", "redis is down")
        ]

    def test_broker_failure_is_logged_and_swallowed(self, task_runner):
        task_runner.fail_dispatch = OSError("broker unreachable")

        with structlog.testing.capture_logs() as logs:
            assert schedule_auto_export(uuid.uuid4(), task_runner, redis_client=FakeRedis()) is False

        assert [(log["event"], log["error"]) for log in logs] == [
            ("Could not schedule automatic export", "broker unreachable")
        ]

    def test_uses_the_configured_redis_when_none_is_given(self, task_runner):
        assembly_id = uuid.uuid4()
        redis = FakeRedis()

        with patch.object(respondent_auto_export, "_get_redis", return_value=redis):
            assert schedule_auto_export(assembly_id, task_runner) is True

        assert redis.get(pending_key(assembly_id)) is not None


class TestRunAutoExport:
    def test_writes_the_saved_tab_with_the_saved_filter(self, uow):
        """The background export honours the status filter chosen when auto-export was enabled."""
        assembly = _assembly_with_config(uow, auto_export=True, status_filter="selected_or_confirmed")
        _add_respondent(uow, assembly, "R1", RespondentStatus.POOL)
        _add_respondent(uow, assembly, "R2", RespondentStatus.SELECTED)
        _add_respondent(uow, assembly, "R3", RespondentStatus.CONFIRMED)
        targets: list[tuple[str, FakeGSheetExportTarget]] = []

        def factory(url: str) -> FakeGSheetExportTarget:
            target = FakeGSheetExportTarget(result_title="Live Data", result_url=_SHEET_URL + "#gid=9")
            targets.append((url, target))
            return target

        assert run_auto_export(uow, assembly.id, factory) is True

        (url, target), *_ = targets
        assert url == _SHEET_URL
        title, table = target.writes[0]
        assert title == "Auto tab"
        assert {row[0] for row in table.rows} == {"R2", "R3"}

    def test_records_the_sheet_details_from_the_target(self, uow):
        assembly = _assembly_with_config(uow, auto_export=True)

        run_auto_export(
            uow,
            assembly.id,
            lambda url: FakeGSheetExportTarget(result_title="Live Data", result_url=_SHEET_URL + "#gid=9"),
        )

        config = uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly.id, GSheetExportKind.RESPONDENTS)
        assert config is not None
        assert config.spreadsheet_title == "Live Data"
        assert config.worksheet_url == _SHEET_URL + "#gid=9"

    def test_switched_off_since_queued_writes_nothing(self, uow):
        assembly = _assembly_with_config(uow, auto_export=False)
        targets: list[FakeGSheetExportTarget] = []

        def factory(url: str) -> FakeGSheetExportTarget:
            targets.append(FakeGSheetExportTarget())
            return targets[-1]

        assert run_auto_export(uow, assembly.id, factory) is False
        assert targets == []

    def test_unknown_assembly_writes_nothing(self, uow):
        assert run_auto_export(uow, uuid.uuid4(), lambda url: FakeGSheetExportTarget()) is False

    def test_export_target_error_propagates_for_the_task_to_retry(self, uow):
        assembly = _assembly_with_config(uow, auto_export=True)
        with pytest.raises(ExportTargetError):
            run_auto_export(uow, assembly.id, lambda url: FakeGSheetExportTarget(error=ExportTargetError("quota")))
