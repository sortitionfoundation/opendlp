"""ABOUTME: Unit tests for the Unit of Work pattern
ABOUTME: Tests transaction management and repository coordination"""

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session, sessionmaker

from opendlp.adapters.sql_repository import (
    SqlAlchemyAssemblyRepository,
    SqlAlchemyUserAssemblyRoleRepository,
    SqlAlchemyUserInviteRepository,
    SqlAlchemyUserRepository,
)
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork, UnitOfWorkError
from tests.fakes import FakeStore, FakeUnitOfWork


class TestSqlAlchemyUnitOfWork:
    def test_unit_of_work_context_manager_commit(self):
        """Test Unit of Work commits on successful context exit."""
        # Create mock session factory
        mock_session = MagicMock(spec=Session)
        mock_session_factory = MagicMock(spec=sessionmaker)
        mock_session_factory.return_value = mock_session

        # Use Unit of Work
        with SqlAlchemyUnitOfWork(mock_session_factory) as uow:
            # Session should be created
            assert uow.session is mock_session
            mock_session_factory.assert_called_once()

            # Repositories should be initialized
            assert isinstance(uow.users, SqlAlchemyUserRepository)
            assert isinstance(uow.assemblies, SqlAlchemyAssemblyRepository)
            assert isinstance(uow.user_invites, SqlAlchemyUserInviteRepository)
            assert isinstance(uow.user_assembly_roles, SqlAlchemyUserAssemblyRoleRepository)

            # All repositories should use the same session
            assert uow.users.session is mock_session
            assert uow.assemblies.session is mock_session
            assert uow.user_invites.session is mock_session
            assert uow.user_assembly_roles.session is mock_session

        # Should commit and close on successful exit
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()
        mock_session.rollback.assert_not_called()

    def test_unit_of_work_context_manager_rollback(self):
        """Test Unit of Work rolls back on exception."""
        mock_session = MagicMock(spec=Session)
        mock_session_factory = MagicMock(spec=sessionmaker)
        mock_session_factory.return_value = mock_session

        with pytest.raises(ValueError), SqlAlchemyUnitOfWork(mock_session_factory) as uow:  # noqa: PT012
            assert uow.session is mock_session
            raise ValueError("Test exception")

        # Should rollback and close on exception
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
        mock_session.commit.assert_not_called()

    def test_manual_commit(self):
        """Test manual commit operation."""
        mock_session = MagicMock(spec=Session)
        mock_session_factory = MagicMock(spec=sessionmaker)
        mock_session_factory.return_value = mock_session

        uow = SqlAlchemyUnitOfWork(mock_session_factory)

        with uow:
            uow.commit()

        # Should call commit twice - once manually, once on exit
        assert mock_session.commit.call_count == 2

    def test_manual_rollback(self):
        """Test manual rollback operation."""
        mock_session = MagicMock(spec=Session)
        mock_session_factory = MagicMock(spec=sessionmaker)
        mock_session_factory.return_value = mock_session

        uow = SqlAlchemyUnitOfWork(mock_session_factory)

        with uow:
            uow.rollback()

        # Should call rollback once manually, then commit on successful exit
        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_commit_and_reset_commits_without_closing(self):
        """commit_and_reset commits the work so far but keeps the session usable."""
        mock_session = MagicMock(spec=Session)
        mock_session_factory = MagicMock(spec=sessionmaker)
        mock_session_factory.return_value = mock_session

        with SqlAlchemyUnitOfWork(mock_session_factory) as uow:
            uow.commit_and_reset()

            # Committed mid-context, but the session must not be closed yet so
            # work can continue against the same session and repositories.
            mock_session.commit.assert_called_once()
            mock_session.close.assert_not_called()
            assert uow.session is mock_session

        # The context exit then commits again and closes.
        assert mock_session.commit.call_count == 2
        mock_session.close.assert_called_once()

    def test_flush_operation(self):
        """Test flush operation."""
        mock_session = MagicMock(spec=Session)
        mock_session_factory = MagicMock(spec=sessionmaker)
        mock_session_factory.return_value = mock_session

        with SqlAlchemyUnitOfWork(mock_session_factory) as uow:
            uow.flush()

        mock_session.flush.assert_called_once()

    def test_repository_initialization(self):
        """Test that repositories are properly initialized with the session."""
        mock_session = MagicMock(spec=Session)
        mock_session_factory = MagicMock(spec=sessionmaker)
        mock_session_factory.return_value = mock_session

        with SqlAlchemyUnitOfWork(mock_session_factory) as uow:
            # All repositories should be initialized
            assert uow.users is not None
            assert uow.assemblies is not None
            assert uow.user_invites is not None
            assert uow.user_assembly_roles is not None
            assert uow.registration_pages is not None
            assert uow.registration_page_html_sources is not None

            # All repositories should use the same session
            assert uow.users.session is mock_session
            assert uow.assemblies.session is mock_session
            assert uow.user_invites.session is mock_session
            assert uow.user_assembly_roles.session is mock_session


class TestFakeUnitOfWorkCommitAndReset:
    def test_commit_and_reset_keeps_data(self):
        """commit_and_reset marks committed and carries on against the same store."""
        uow = FakeUnitOfWork()
        sentinel = object()
        uow.fake_users._items.append(sentinel)

        uow.commit_and_reset()

        assert uow.committed is True
        # Unlike rollback (which clears the store), the data carries on.
        assert sentinel in uow.fake_users._items


class TestSqlAlchemyUnitOfWorkStrictness:
    """Outside its block a UnitOfWork must be inert.

    The original bug: `__exit__` closed the session but left it attached, and a
    closed SQLAlchemy session silently autobegins a new transaction on next use.
    Work done through it then belonged to a transaction nobody would commit, and
    the connection sat `idle in transaction` holding locks.
    """

    def _uow(self):
        mock_session = MagicMock(spec=Session)
        mock_session_factory = MagicMock(spec=sessionmaker)
        mock_session_factory.return_value = mock_session
        return SqlAlchemyUnitOfWork(mock_session_factory), mock_session

    def test_session_is_not_available_before_the_block(self):
        uow, _ = self._uow()

        with pytest.raises(UnitOfWorkError):
            _ = uow.session

    def test_session_is_not_available_after_the_block(self):
        uow, _ = self._uow()
        with uow:
            pass

        with pytest.raises(UnitOfWorkError):
            _ = uow.session

    def test_repositories_are_not_available_after_the_block(self):
        """Repositories hold their own session reference, so guarding `session` is not enough."""
        uow, _ = self._uow()
        with uow:
            pass

        with pytest.raises(UnitOfWorkError, match="users"):
            uow.users.get(uuid.uuid4())

    def test_a_second_block_asks_the_factory_for_a_second_session(self):
        """A reused UnitOfWork must build a fresh session, not revive the closed one."""
        uow, _ = self._uow()
        with uow:
            pass
        with uow:
            pass

        assert uow.session_factory.call_count == 2

    def test_a_failing_commit_still_releases_the_connection(self):
        uow, mock_session = self._uow()
        mock_session.commit.side_effect = RuntimeError("commit failed")

        with pytest.raises(RuntimeError), uow:
            pass

        mock_session.close.assert_called_once()

    def test_a_failing_commit_still_closes_the_unit_of_work(self):
        uow, mock_session = self._uow()
        mock_session.commit.side_effect = RuntimeError("commit failed")

        with pytest.raises(RuntimeError), uow:
            pass

        with pytest.raises(UnitOfWorkError):
            _ = uow.session


class TestFakeUnitOfWorkStrictMode:
    """A strict fake mirrors the real UnitOfWork: repositories only work inside the block.

    This is what stops a test passing while the code under test relies on the
    resurrecting-session bug the convention work exists to remove.
    """

    def test_repository_access_before_the_block_raises(self):
        uow = FakeUnitOfWork(strict=True)

        with pytest.raises(UnitOfWorkError):
            uow.users.get(uuid.uuid4())

    def test_repository_access_inside_the_block_works(self):
        with FakeUnitOfWork(strict=True) as uow:
            assert uow.users.get(uuid.uuid4()) is None

    def test_repository_access_after_the_block_raises(self):
        with FakeUnitOfWork(strict=True) as uow:
            pass

        with pytest.raises(UnitOfWorkError):
            uow.users.get(uuid.uuid4())

    def test_the_block_can_be_re_entered(self):
        uow = FakeUnitOfWork(strict=True)
        with uow:
            pass

        with uow:
            assert uow.users.get(uuid.uuid4()) is None

    def test_fake_aliases_stay_usable_outside_the_block(self):
        """The `fake_` aliases are the deliberate arrange/inspect seam."""
        uow = FakeUnitOfWork(strict=True)
        user = User(email="strict@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.fake_users.add(user)

        with uow:
            assert uow.users.get(user.id) is user

        assert uow.fake_users.get(user.id) is user

    def test_non_strict_is_the_default_and_needs_no_block(self):
        uow = FakeUnitOfWork()

        assert uow.users.get(uuid.uuid4()) is None

    def test_strict_error_names_the_repository(self):
        uow = FakeUnitOfWork(strict=True)

        with pytest.raises(UnitOfWorkError, match="assemblies"):
            uow.assemblies.get(uuid.uuid4())

    def test_a_shared_store_still_rolls_back_when_strict(self):
        store = FakeStore()
        user = User(email="rollback@example.com", global_role=GlobalRole.USER, password_hash="hash")

        with pytest.raises(ValueError), FakeUnitOfWork(store, strict=True) as uow:  # noqa: PT012
            uow.users.add(user)
            raise ValueError("boom")

        assert store.users.get(user.id) is None
