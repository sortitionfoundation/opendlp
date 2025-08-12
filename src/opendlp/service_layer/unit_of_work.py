"""ABOUTME: Unit of Work pattern implementation for transaction management
ABOUTME: Coordinates repository operations within database transactions"""

from __future__ import annotations

import abc
from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from opendlp.adapters.sql_repository import (
    SqlAlchemyAssemblyRepository,
    SqlAlchemyUserAssemblyRoleRepository,
    SqlAlchemyUserInviteRepository,
    SqlAlchemyUserRepository,
)


class AbstractUnitOfWork(abc.ABC):
    """Abstract Unit of Work interface."""

    users: SqlAlchemyUserRepository
    assemblies: SqlAlchemyAssemblyRepository
    user_invites: SqlAlchemyUserInviteRepository
    user_assembly_roles: SqlAlchemyUserAssemblyRoleRepository

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


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """SQLAlchemy implementation of Unit of Work pattern."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory
        self.session: Session | None = None

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self.session_factory()

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

        if self.session:
            self.session.close()

    def commit(self) -> None:
        """Commit the current transaction."""
        if self.session:
            self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        if self.session:
            self.session.rollback()

    def flush(self) -> None:
        """Flush pending changes to the database without committing."""
        if self.session:
            self.session.flush()


class UnitOfWorkError(Exception):
    """Exception raised when Unit of Work operations fail."""

    pass
