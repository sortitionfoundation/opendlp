"""ABOUTME: Integration tests for scheduling the automatic export from recorded events, against PostgreSQL
ABOUTME: The export is queued once the change commits and never for a change that rolls back"""

import uuid
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet
from opendlp.domain.events import RespondentsChanged, RespondentSchemaChanged
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import GSheetExportKind
from opendlp.service_layer import respondent_auto_export
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.fakes import FakeRedis, RecordingTaskRunner

_SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"


@pytest.fixture
def dispatch(task_runner: RecordingTaskRunner) -> Iterator[RecordingTaskRunner]:
    """The task runner the export is sent to, with Redis replaced by a fresh in-memory fake."""
    with patch.object(respondent_auto_export, "_get_redis", return_value=FakeRedis()):
        yield task_runner


def _assembly(session_factory, *, auto_export: bool) -> uuid.UUID:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assembly = Assembly(title="Auto export events")
        uow.assemblies.add(assembly)
        uow.flush()
        uow.assembly_export_gsheets.add(
            AssemblyExportGSheet(
                assembly_id=assembly.id,
                export_kind=GSheetExportKind.RESPONDENTS,
                url=_SHEET_URL,
                auto_export=auto_export,
            )
        )
        return assembly.id


def _respondent_count(session_factory, assembly_id: uuid.UUID) -> int:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        return uow.respondents.count_by_assembly_id(assembly_id)


class TestRecordedEventsScheduleTheExport:
    @pytest.mark.parametrize("event_class", [RespondentsChanged, RespondentSchemaChanged])
    def test_the_export_is_queued_when_the_block_commits(self, postgres_session_factory, dispatch, event_class):
        assembly_id = _assembly(postgres_session_factory, auto_export=True)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.record(event_class(assembly_id))
            assert dispatch.submitted == []

        assert len(dispatch.submitted) == 1
        assert dispatch.submitted[0].kwargs == {"assembly_id": assembly_id}

    def test_the_change_is_committed_by_the_time_the_export_is_queued(self, postgres_session_factory, dispatch):
        assembly_id = _assembly(postgres_session_factory, auto_export=True)
        seen = []

        dispatch.on_dispatch = lambda task: seen.append(_respondent_count(postgres_session_factory, assembly_id))

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="R1"))
            uow.record(RespondentsChanged(assembly_id))

        assert seen == [1]

    def test_nothing_is_queued_when_the_block_raises(self, postgres_session_factory, dispatch):
        assembly_id = _assembly(postgres_session_factory, auto_export=True)

        with pytest.raises(ValueError, match="boom"), SqlAlchemyUnitOfWork(postgres_session_factory) as uow:  # noqa: PT012
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id="R1"))
            uow.record(RespondentsChanged(assembly_id))
            raise ValueError("boom")

        assert dispatch.submitted == []
        assert _respondent_count(postgres_session_factory, assembly_id) == 0

    def test_nothing_is_queued_when_auto_export_is_off(self, postgres_session_factory, dispatch):
        assembly_id = _assembly(postgres_session_factory, auto_export=False)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.record(RespondentsChanged(assembly_id))

        assert dispatch.submitted == []

    def test_several_changes_in_one_block_queue_one_export(self, postgres_session_factory, dispatch):
        assembly_id = _assembly(postgres_session_factory, auto_export=True)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.record(RespondentsChanged(assembly_id))
            uow.record(RespondentSchemaChanged(assembly_id))

        assert len(dispatch.submitted) == 1
