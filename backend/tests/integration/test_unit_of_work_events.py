"""ABOUTME: Integration tests for events and after-commit callbacks against PostgreSQL
ABOUTME: Proves callbacks see committed data, and that handler writes share the caller's transaction"""

import uuid
from dataclasses import dataclass

import pytest

from opendlp.domain.events import Event
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork, UnitOfWorkError


@dataclass(frozen=True)
class UserWanted(Event):
    """An event of the tests' own: a handler answers it by adding a user."""

    user_id: uuid.UUID


def _user(user_id=None):
    return User(
        user_id=user_id,
        email=f"events-{uuid.uuid4()}@example.com",
        global_role=GlobalRole.USER,
        password_hash="hash",  # pragma: allowlist secret
    )


def _add_user(event, uow):
    uow.users.add(_user(event.user_id))


def _exists(session_factory, user_id):
    with SqlAlchemyUnitOfWork(session_factory) as other:
        return other.users.get(user_id) is not None


class TestAfterCommitAgainstPostgres:
    def test_a_callback_sees_the_work_as_committed(self, postgres_session_factory):
        user = _user()
        seen = []

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.users.add(user)
            uow.after_commit(lambda: seen.append(_exists(postgres_session_factory, user.id)))
            assert seen == []

        assert seen == [True]

    def test_a_callback_runs_at_a_commit_in_the_middle_of_the_block(self, postgres_session_factory):
        user = _user()
        seen = []

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.users.add(user)
            uow.after_commit(lambda: seen.append(_exists(postgres_session_factory, user.id)))
            uow.commit()
            assert seen == [True]

        assert seen == [True]

    def test_no_callback_runs_when_the_block_raises(self, postgres_session_factory):
        user = _user()
        calls = []

        with pytest.raises(ValueError, match="boom"), SqlAlchemyUnitOfWork(postgres_session_factory) as uow:  # noqa: PT012
            uow.users.add(user)
            uow.after_commit(lambda: calls.append("ran"))
            raise ValueError("boom")

        assert calls == []
        assert not _exists(postgres_session_factory, user.id)

    def test_a_callback_that_writes_through_the_session_is_refused_and_its_write_is_lost(
        self, postgres_session_factory
    ):
        user_id, stray_id = uuid.uuid4(), uuid.uuid4()
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)

        with pytest.raises(UnitOfWorkError, match="must not touch the database"), uow:  # noqa: PT012
            uow.users.add(_user(user_id))
            uow.after_commit(lambda: uow.users.add(_user(stray_id)))

        assert _exists(postgres_session_factory, user_id)
        assert not _exists(postgres_session_factory, stray_id)


class TestHandlersAgainstPostgres:
    def test_a_handler_write_commits_with_the_work_that_recorded_the_event(self, postgres_session_factory):
        user_id = uuid.uuid4()

        with SqlAlchemyUnitOfWork(postgres_session_factory, event_handlers={UserWanted: [_add_user]}) as uow:
            uow.record(UserWanted(user_id))
            assert not _exists(postgres_session_factory, user_id)

        assert _exists(postgres_session_factory, user_id)

    def test_a_handler_write_rolls_back_with_the_work_that_recorded_the_event(self, postgres_session_factory):
        user_id = uuid.uuid4()
        uow = SqlAlchemyUnitOfWork(postgres_session_factory, event_handlers={UserWanted: [_add_user]})

        with pytest.raises(ValueError, match="boom"), uow:  # noqa: PT012
            uow.record(UserWanted(user_id))
            raise ValueError("boom")

        assert not _exists(postgres_session_factory, user_id)

    def test_a_failing_handler_rolls_back_the_work_that_recorded_the_event(self, postgres_session_factory):
        user = _user()

        def broken(event, uow):
            raise RuntimeError("handler failed")

        uow = SqlAlchemyUnitOfWork(postgres_session_factory, event_handlers={UserWanted: [broken]})

        with pytest.raises(RuntimeError, match="handler failed"), uow:  # noqa: PT012
            uow.users.add(user)
            uow.record(UserWanted(user.id))

        assert not _exists(postgres_session_factory, user.id)
