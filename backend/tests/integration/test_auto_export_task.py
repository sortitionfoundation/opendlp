# ABOUTME: Integration tests for the auto_export_respondents Celery task
# ABOUTME: Runs the task function against Postgres and the test Redis with a fake sheet target

import uuid
from unittest.mock import patch

import pytest

from opendlp.adapters.tabular_export import ExportTargetError
from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import GSheetExportKind, RespondentStatus
from opendlp.entrypoints.celery.tasks import AUTO_EXPORT_MAX_RETRIES, auto_export_respondents
from opendlp.service_layer.respondent_auto_export import lock_key, pending_key
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.fakes import FakeGSheetExportTarget

_SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"
_DISPATCH = "opendlp.service_layer.respondent_auto_export.tasks.auto_export_respondents.apply_async"


@pytest.fixture
def auto_export_assembly(postgres_session_factory) -> uuid.UUID:
    """An assembly with two respondents and auto-export switched on for "all"."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = Assembly(title="Auto export assembly")
        uow.assemblies.add(assembly)
        uow.respondents.add(Respondent(assembly_id=assembly.id, external_id="R1"))
        uow.respondents.add(
            Respondent(assembly_id=assembly.id, external_id="R2", selection_status=RespondentStatus.SELECTED)
        )
        uow.assembly_export_gsheets.add(
            AssemblyExportGSheet(
                assembly_id=assembly.id,
                export_kind=GSheetExportKind.RESPONDENTS,
                url=_SHEET_URL,
                worksheet_name="Live",
                auto_export=True,
            )
        )
        uow.commit()
        return assembly.id


@pytest.fixture
def redis(test_redis_client):
    test_redis_client.flushdb()
    yield test_redis_client
    test_redis_client.flushdb()


class TestAutoExportRespondentsTask:
    def test_writes_every_respondent_and_clears_the_pending_key(
        self, auto_export_assembly, postgres_session_factory, redis
    ):
        redis.set(pending_key(auto_export_assembly), "1")
        targets: list[FakeGSheetExportTarget] = []

        def factory(url: str) -> FakeGSheetExportTarget:
            targets.append(FakeGSheetExportTarget(result_title="Live Data"))
            return targets[-1]

        result = auto_export_respondents(
            assembly_id=auto_export_assembly,
            session_factory=postgres_session_factory,
            target_factory=factory,
            redis_client=redis,
        )

        assert result is True
        title, table = targets[0].writes[0]
        assert title == "Live"
        assert {row[0] for row in table.rows} == {"R1", "R2"}
        assert redis.get(pending_key(auto_export_assembly)) is None
        assert redis.get(lock_key(auto_export_assembly)) is None
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            config = uow.assembly_export_gsheets.get_by_assembly_and_kind(
                auto_export_assembly, GSheetExportKind.RESPONDENTS
            )
            assert config is not None
            assert config.spreadsheet_title == "Live Data"

    def test_lock_held_requests_another_run_instead_of_writing(
        self, auto_export_assembly, postgres_session_factory, redis
    ):
        """A second run for the same assembly re-queues itself rather than interleaving writes."""
        redis.set(lock_key(auto_export_assembly), "held")
        targets: list[FakeGSheetExportTarget] = []

        def factory(url: str) -> FakeGSheetExportTarget:
            targets.append(FakeGSheetExportTarget())
            return targets[-1]

        with patch(_DISPATCH) as dispatch:
            result = auto_export_respondents(
                assembly_id=auto_export_assembly,
                session_factory=postgres_session_factory,
                target_factory=factory,
                redis_client=redis,
            )

        assert result is False
        assert targets == []
        dispatch.assert_called_once()
        assert redis.get(pending_key(auto_export_assembly)) is not None
        # The lock belongs to the other run and is left alone.
        assert redis.get(lock_key(auto_export_assembly)) == "held"

    def test_switched_off_since_queued_writes_nothing(self, auto_export_assembly, postgres_session_factory, redis):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            config = uow.assembly_export_gsheets.get_by_assembly_and_kind(
                auto_export_assembly, GSheetExportKind.RESPONDENTS
            )
            assert config is not None
            config.update_values(auto_export=False)
            uow.commit()
        targets: list[FakeGSheetExportTarget] = []

        def factory(url: str) -> FakeGSheetExportTarget:
            targets.append(FakeGSheetExportTarget())
            return targets[-1]

        result = auto_export_respondents(
            assembly_id=auto_export_assembly,
            session_factory=postgres_session_factory,
            target_factory=factory,
            redis_client=redis,
        )

        assert result is False
        assert targets == []

    def test_write_failure_is_logged_and_raised_for_retry(
        self, auto_export_assembly, postgres_session_factory, redis, caplog
    ):
        """Called directly there is no worker to retry, so the error surfaces after the warning."""

        def factory(url: str) -> FakeGSheetExportTarget:
            return FakeGSheetExportTarget(error=ExportTargetError("quota exceeded"))

        with caplog.at_level("WARNING"), pytest.raises(ExportTargetError):
            auto_export_respondents(
                assembly_id=auto_export_assembly,
                session_factory=postgres_session_factory,
                target_factory=factory,
                redis_client=redis,
            )

        assert "Automatic export failed; will retry" in caplog.text
        assert "quota exceeded" in caplog.text
        assert redis.get(lock_key(auto_export_assembly)) is None

    def test_final_attempt_failure_is_logged_as_an_error_and_not_raised(
        self, auto_export_assembly, postgres_session_factory, redis, caplog
    ):
        def factory(url: str) -> FakeGSheetExportTarget:
            return FakeGSheetExportTarget(error=ExportTargetError("still not shared"))

        auto_export_respondents.push_request(retries=AUTO_EXPORT_MAX_RETRIES)
        try:
            with caplog.at_level("WARNING"):
                result = auto_export_respondents(
                    assembly_id=auto_export_assembly,
                    session_factory=postgres_session_factory,
                    target_factory=factory,
                    redis_client=redis,
                )
        finally:
            auto_export_respondents.pop_request()

        assert result is False
        assert "Automatic export failed and will not be retried" in caplog.text
        assert "still not shared" in caplog.text
