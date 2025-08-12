"""ABOUTME: Unit tests for the Unit of Work pattern
ABOUTME: Tests transaction management and repository coordination"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session, sessionmaker

from opendlp.adapters.sql_repository import (
    SqlAlchemyAssemblyRepository,
    SqlAlchemyUserAssemblyRoleRepository,
    SqlAlchemyUserInviteRepository,
    SqlAlchemyUserRepository,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


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

        with pytest.raises(ValueError), SqlAlchemyUnitOfWork(mock_session_factory) as uow:
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

    def test_flush_operation(self):
        """Test flush operation."""
        mock_session = MagicMock(spec=Session)
        mock_session_factory = MagicMock(spec=sessionmaker)
        mock_session_factory.return_value = mock_session

        with SqlAlchemyUnitOfWork(mock_session_factory) as uow:
            uow.flush()

        mock_session.flush.assert_called_once()

    def test_no_session_operations_when_session_is_none(self):
        """Test that operations are safe when session is None."""
        mock_session_factory = MagicMock(spec=sessionmaker)

        uow = SqlAlchemyUnitOfWork(mock_session_factory)
        # Don't enter context, so session remains None

        # These should not raise exceptions
        uow.commit()
        uow.rollback()
        uow.flush()

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

            # All repositories should use the same session
            assert uow.users.session is mock_session
            assert uow.assemblies.session is mock_session
            assert uow.user_invites.session is mock_session
            assert uow.user_assembly_roles.session is mock_session
