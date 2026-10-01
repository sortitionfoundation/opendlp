# ABOUTME: Unit tests for scheduling and running the automatic respondent export
# ABOUTME: Fake UnitOfWork, an in-memory Redis stand-in and a patched Celery dispatch

import uuid
from unittest.mock import patch

import pytest

from opendlp.adapters.tabular_export import ExportTargetError
from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import GSheetExportKind, RespondentStatus
from opendlp.service_layer import respondent_auto_export
from opendlp.service_layer.respondent_auto_export import (
    AUTO_EXPORT_DELAY_SECONDS,
    pending_key,
    request_auto_export,
    run_auto_export,
)
from tests.fakes import FakeGSheetExportTarget, FakeRedis, FakeUnitOfWork

_SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"
_DISPATCH = "opendlp.service_layer.respondent_auto_export.tasks.auto_export_respondents.apply_async"


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


class TestRequestAutoExport:
    def test_no_config_dispatches_nothing(self, uow):
        assembly = Assembly(title="Test Assembly")
        uow.assemblies.add(assembly)
        with patch(_DISPATCH) as dispatch:
            assert request_auto_export(uow, assembly.id, redis_client=FakeRedis()) is False
        dispatch.assert_not_called()

    def test_auto_export_off_dispatches_nothing(self, uow):
        assembly = _assembly_with_config(uow, auto_export=False)
        with patch(_DISPATCH) as dispatch:
            assert request_auto_export(uow, assembly.id, redis_client=FakeRedis()) is False
        dispatch.assert_not_called()

    def test_dispatches_one_task_with_the_delay(self, uow):
        """The first request marks the assembly pending and queues a delayed task."""
        assembly = _assembly_with_config(uow, auto_export=True)
        redis = FakeRedis()
        with patch(_DISPATCH) as dispatch:
            assert request_auto_export(uow, assembly.id, redis_client=redis) is True
        dispatch.assert_called_once_with(kwargs={"assembly_id": assembly.id}, countdown=AUTO_EXPORT_DELAY_SECONDS)
        assert redis.get(pending_key(assembly.id)) is not None

    def test_second_request_while_pending_is_folded_into_the_first(self, uow):
        assembly = _assembly_with_config(uow, auto_export=True)
        redis = FakeRedis()
        with patch(_DISPATCH) as dispatch:
            request_auto_export(uow, assembly.id, redis_client=redis)
            assert request_auto_export(uow, assembly.id, redis_client=redis) is False
        assert dispatch.call_count == 1

    def test_requests_for_different_assemblies_are_independent(self, uow):
        first = _assembly_with_config(uow, auto_export=True)
        second = _assembly_with_config(uow, auto_export=True)
        redis = FakeRedis()
        with patch(_DISPATCH) as dispatch:
            request_auto_export(uow, first.id, redis_client=redis)
            request_auto_export(uow, second.id, redis_client=redis)
        assert dispatch.call_count == 2

    def test_redis_failure_is_logged_and_swallowed(self, uow, caplog):
        """A broken Redis must not fail the change that asked for the export."""
        assembly = _assembly_with_config(uow, auto_export=True)
        with patch(_DISPATCH) as dispatch, caplog.at_level("WARNING"):
            assert request_auto_export(uow, assembly.id, redis_client=_BrokenRedis()) is False
        dispatch.assert_not_called()
        assert "Could not schedule automatic export" in caplog.text
        assert "redis is down" in caplog.text

    def test_broker_failure_is_logged_and_swallowed(self, uow, caplog):
        assembly = _assembly_with_config(uow, auto_export=True)
        with patch(_DISPATCH, side_effect=OSError("broker unreachable")), caplog.at_level("WARNING"):
            assert request_auto_export(uow, assembly.id, redis_client=FakeRedis()) is False
        assert "Could not schedule automatic export" in caplog.text

    def test_uses_the_configured_redis_when_none_is_given(self, uow):
        assembly = _assembly_with_config(uow, auto_export=True)
        redis = FakeRedis()
        with (
            patch.object(respondent_auto_export, "_get_redis", return_value=redis),
            patch(_DISPATCH),
        ):
            assert request_auto_export(uow, assembly.id) is True
        assert redis.get(pending_key(assembly.id)) is not None


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
