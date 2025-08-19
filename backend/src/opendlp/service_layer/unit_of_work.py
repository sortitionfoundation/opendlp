"""ABOUTME: Unit of Work pattern implementation for transaction management
ABOUTME: Coordinates repository operations within database transactions"""

from __future__ import annotations

import abc
from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from opendlp.adapters.database import create_session_factory
from opendlp.adapters.sql_repository import (
    SqlAlchemyAssemblyRepository,
    SqlAlchemyUserAssemblyRoleRepository,
    SqlAlchemyUserInviteRepository,
    SqlAlchemyUserRepository,
)
from opendlp.service_layer.repositories import (
    AssemblyRepository,
    UserAssemblyRoleRepository,
    UserInviteRepository,
    UserRepository,
)


class AbstractUnitOfWork(abc.ABC):
    """Abstract Unit of Work interface."""

    users: UserRepository
    assemblies: AssemblyRepository
    user_invites: UserInviteRepository
    user_assembly_roles: UserAssemblyRoleRepository

    def __enter__(self) -> AbstractUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()

    @abc.abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""
        raise NotImplementedError

    @abc.abstractmethod
    def rollback(self) -> None:
        """Rollback the current transaction."""
        raise NotImplementedError


DEFAULT_SESSION_FACTORY = create_session_factory()


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """SQLAlchemy implementation of Unit of Work pattern."""

    def __init__(self, session_factory: sessionmaker | None = None) -> None:
        self.session_factory = session_factory or DEFAULT_SESSION_FACTORY
        self._session: Session | None = None

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = self.session_factory()
        assert isinstance(self._session, Session)
        return self._session

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        # Initialize repositories with the session
        self.users = SqlAlchemyUserRepository(self.session)
        self.assemblies = SqlAlchemyAssemblyRepository(self.session)
        self.user_invites = SqlAlchemyUserInviteRepository(self.session)
        self.user_assembly_roles = SqlAlchemyUserAssemblyRoleRepository(self.session)

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()

        self.session.close()

    def commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.session.rollback()

    def flush(self) -> None:
        """Flush pending changes to the database without committing."""
        self.session.flush()


class UnitOfWorkError(Exception):
    """Exception raised when Unit of Work operations fail."""

    pass
