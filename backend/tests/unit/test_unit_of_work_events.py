"""ABOUTME: Unit tests for recording domain events on a UnitOfWork
ABOUTME: Covers handler dispatch, after-commit callbacks and the guards around both"""

import subprocess
import sys
import uuid
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
import structlog
from sqlalchemy.orm import Session, sessionmaker

from opendlp.domain.events import Event, RespondentsChanged, RespondentSchemaChanged
from opendlp.service_layer import handlers
from opendlp.service_layer.unit_of_work import MAX_EVENT_CHAIN_DEPTH, SqlAlchemyUnitOfWork, UnitOfWorkError
from tests.fakes import FakeUnitOfWork


@dataclass(frozen=True)
class Ping(Event):
    """An event of the tests' own, so no real handler is ever registered for it."""

    number: int = 0


def _sql_uow(event_handlers=None, pending=False):
    """A SqlAlchemyUnitOfWork over a mock session that reports nothing pending unless asked to."""
    mock_session = MagicMock(spec=Session)
    mock_session.new = [object()] if pending else []
    mock_session.dirty = []
    mock_session.deleted = []
    mock_session_factory = MagicMock(spec=sessionmaker)
    mock_session_factory.return_value = mock_session
    return SqlAlchemyUnitOfWork(mock_session_factory, event_handlers=event_handlers), mock_session


def _both_kinds(event_handlers=None):
    return [_sql_uow(event_handlers)[0], FakeUnitOfWork(event_handlers=event_handlers)]


class TestRecord:
    @pytest.mark.parametrize("uow", _both_kinds({}), ids=["sql", "fake"])
    def test_a_recorded_event_is_kept_on_the_unit_of_work(self, uow):
        event = RespondentsChanged(uuid.uuid4())

        with uow:
            uow.record(event)

        assert uow.events == [event]

    def test_handlers_are_called_with_the_event_and_the_unit_of_work(self):
        calls = []
        uow = FakeUnitOfWork(event_handlers={Ping: [lambda event, uow: calls.append((event, uow))]})

        with uow:
            uow.record(Ping(1))

        assert calls == [(Ping(1), uow)]

    def test_a_handler_runs_inside_the_open_context(self):
        seen = []
        uow = FakeUnitOfWork(event_handlers={Ping: [lambda event, uow: seen.append(uow.users.all())]})

        with uow:
            uow.record(Ping())

        assert seen == [[]]

    def test_every_handler_for_the_event_is_called_in_order(self):
        calls = []
        uow = FakeUnitOfWork(
            event_handlers={Ping: [lambda event, uow: calls.append("first"), lambda event, uow: calls.append("second")]}
        )

        with uow:
            uow.record(Ping())

        assert calls == ["first", "second"]

    def test_dispatch_is_by_exact_type(self):
        calls = []
        uow = FakeUnitOfWork(event_handlers={Event: [lambda event, uow: calls.append(event)]})

        with uow:
            uow.record(Ping())

        assert calls == []

    def test_an_event_with_no_handlers_is_still_recorded(self):
        uow = FakeUnitOfWork(event_handlers={RespondentSchemaChanged: [lambda event, uow: None]})

        with uow:
            uow.record(Ping())

        assert uow.events == [Ping()]

    def test_a_handler_exception_reaches_the_caller(self):
        def broken(event, uow):
            raise ValueError("handler failed")

        uow, session = _sql_uow({Ping: [broken]})

        with pytest.raises(ValueError, match="handler failed"), uow:
            uow.record(Ping())

        session.rollback.assert_called_once()
        session.commit.assert_not_called()

    def test_a_handler_may_record_an_event_of_its_own(self):
        calls = []
        uow = FakeUnitOfWork(
            event_handlers={
                Ping: [lambda event, uow: uow.record(RespondentsChanged(assembly_id))],
                RespondentsChanged: [lambda event, uow: calls.append(event)],
            }
        )
        assembly_id = uuid.uuid4()

        with uow:
            uow.record(Ping())

        assert calls == [RespondentsChanged(assembly_id)]
        assert uow.events == [Ping(), RespondentsChanged(assembly_id)]

    def test_handlers_recording_in_a_cycle_are_stopped(self):
        uow = FakeUnitOfWork(event_handlers={Ping: [lambda event, uow: uow.record(Ping(event.number + 1))]})

        with uow, pytest.raises(UnitOfWorkError, match="cycle"):
            uow.record(Ping())

        assert len(uow.events) == MAX_EVENT_CHAIN_DEPTH + 1

    def test_the_depth_guard_does_not_outlive_the_chain_that_tripped_it(self):
        uow = FakeUnitOfWork(event_handlers={Ping: [lambda event, uow: uow.record(Ping(event.number + 1))]})

        with uow:
            with pytest.raises(UnitOfWorkError):
                uow.record(Ping())
            uow.record(RespondentsChanged(uuid.uuid4()))

    @pytest.mark.parametrize("uow", _both_kinds({}), ids=["sql", "fake"])
    def test_entering_the_context_again_starts_with_no_events(self, uow):
        with uow:
            uow.record(Ping(1))
        with uow:
            uow.record(Ping(2))

        assert uow.events == [Ping(2)]

    def test_the_fake_runs_no_handlers_unless_given_some(self, monkeypatch):
        calls = []
        monkeypatch.setitem(handlers.EVENT_HANDLERS, Ping, [lambda event, uow: calls.append(event)])
        uow = FakeUnitOfWork()

        with uow:
            uow.record(Ping())

        assert calls == []

    def test_the_real_unit_of_work_uses_the_application_registry_by_default(self, monkeypatch):
        calls = []
        monkeypatch.setitem(handlers.EVENT_HANDLERS, Ping, [lambda event, uow: calls.append(event)])
        uow, _session = _sql_uow()

        with uow:
            uow.record(Ping())

        assert calls == [Ping()]


class TestAfterCommit:
    @pytest.mark.parametrize("uow", _both_kinds({}), ids=["sql", "fake"])
    def test_a_callback_does_not_run_before_the_commit(self, uow):
        calls = []

        with uow:
            uow.after_commit(lambda: calls.append("ran"))
            assert calls == []
            uow.commit()
            assert calls == ["ran"]

    def test_a_callback_runs_when_the_block_exits_cleanly(self):
        calls = []
        uow, session = _sql_uow()
        session.commit.side_effect = lambda: calls.append("commit")

        with uow:
            uow.after_commit(lambda: calls.append("callback"))

        assert calls == ["commit", "callback"]

    @pytest.mark.parametrize("uow", _both_kinds({}), ids=["sql", "fake"])
    def test_a_callback_runs_once_however_many_commits_follow(self, uow):
        calls = []

        with uow:
            uow.after_commit(lambda: calls.append("ran"))
            uow.commit()
            uow.commit()

        assert calls == ["ran"]

    @pytest.mark.parametrize("uow", _both_kinds({}), ids=["sql", "fake"])
    def test_commit_and_reset_runs_the_callbacks(self, uow):
        calls = []

        with uow:
            uow.after_commit(lambda: calls.append("ran"))
            uow.commit_and_reset()
            assert calls == ["ran"]

    @pytest.mark.parametrize("uow", _both_kinds({}), ids=["sql", "fake"])
    def test_a_callback_is_dropped_when_the_block_raises(self, uow):
        calls = []

        with pytest.raises(ValueError, match="boom"), uow:  # noqa: PT012
            uow.after_commit(lambda: calls.append("ran"))
            raise ValueError("boom")

        assert calls == []

    @pytest.mark.parametrize("uow", _both_kinds({}), ids=["sql", "fake"])
    def test_a_callback_is_dropped_by_an_explicit_rollback(self, uow):
        calls = []

        with uow:
            uow.after_commit(lambda: calls.append("ran"))
            uow.rollback()
            uow.commit()

        assert calls == []

    def test_a_callback_is_dropped_when_the_commit_fails(self):
        calls = []
        uow, session = _sql_uow()
        session.commit.side_effect = RuntimeError("commit failed")

        with pytest.raises(RuntimeError, match="commit failed"), uow:
            uow.after_commit(lambda: calls.append("ran"))

        session.commit.side_effect = None
        with uow:
            pass

        assert calls == []

    @pytest.mark.parametrize("uow", _both_kinds({}), ids=["sql", "fake"])
    def test_a_failing_callback_is_logged_and_the_rest_still_run(self, uow):
        calls = []

        def broken():
            raise RuntimeError("redis is down")

        with structlog.testing.capture_logs() as logs, uow:
            uow.after_commit(broken)
            uow.after_commit(lambda: calls.append("ran"))
            uow.commit()

        assert calls == ["ran"]
        assert [(log["event"], log["log_level"], log["error"]) for log in logs] == [
            ("After-commit callback failed", "error", "redis is down")
        ]

    def test_a_handler_can_register_a_callback(self):
        calls = []
        uow = FakeUnitOfWork(
            event_handlers={Ping: [lambda event, uow: uow.after_commit(lambda: calls.append(event.number))]}
        )

        with uow:
            uow.record(Ping(7))
            assert calls == []
            uow.commit()

        assert calls == [7]

    def test_a_callback_that_leaves_work_in_the_session_is_refused(self):
        uow, session = _sql_uow(pending=True)

        with pytest.raises(UnitOfWorkError, match="must not touch the database"), uow:
            uow.after_commit(lambda: None)

        session.commit.assert_called_once()

    def test_the_session_is_not_inspected_when_there_were_no_callbacks(self):
        uow, session = _sql_uow(pending=True)

        with uow:
            uow.commit()

        assert session.commit.call_count == 2


class TestImportOrder:
    """The handler registry reaches modules that import the UnitOfWork, so it is resolved late."""

    @pytest.mark.parametrize(
        "module",
        ["opendlp.service_layer.unit_of_work", "opendlp.service_layer.handlers", "opendlp.domain.events"],
    )
    def test_module_imports_first_in_a_fresh_interpreter(self, module):
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", f"import {module}"], capture_output=True, text=True, check=False
        )

        assert result.returncode == 0, result.stderr
