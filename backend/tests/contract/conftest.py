"""ABOUTME: Shared fixtures for contract tests that run against both fake and SQL repositories.
ABOUTME: Provides a parameterized backend abstraction so each test suite runs with both implementations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from opendlp.adapters.sql_repository import (
    SqlAlchemyPasswordResetTokenRepository,
)
from opendlp.domain.password_reset import PasswordResetToken
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from tests.fakes import FakePasswordResetTokenRepository


@dataclass
class RepoBackend:
    """Wraps a repository and a commit function so tests can work with both backends."""

    repo: Any
    commit: Any  # callable to flush/commit changes to the backend

    def make_user(self) -> User:
        """Create a User domain object. SQL backend needs to persist it separately."""
        raise NotImplementedError

    def make_token(
        self,
        user_id: uuid.UUID,
        expires_in_hours: int = 1,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
        used_at: datetime | None = None,
    ) -> PasswordResetToken:
        """Create and persist a PasswordResetToken."""
        token = PasswordResetToken(
            user_id=user_id,
            expires_in_hours=expires_in_hours,
            created_at=created_at,
            expires_at=expires_at,
            used_at=used_at,
        )
        self.repo.add(token)
        self.commit()
        return token


class FakeBackend(RepoBackend):
    """Backend backed by the in-memory FakePasswordResetTokenRepository."""

    def __init__(self) -> None:
        repo = FakePasswordResetTokenRepository()
        super().__init__(repo=repo, commit=lambda: None)

    def make_user(self) -> User:
        return User(
            email=f"user-{uuid.uuid4().hex[:8]}@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )


class SqlBackend(RepoBackend):
    """Backend backed by the real SqlAlchemy repository with a Postgres session."""

    def __init__(self, session: Session) -> None:
        repo = SqlAlchemyPasswordResetTokenRepository(session)
        self._session = session
        super().__init__(repo=repo, commit=session.commit)

    def make_user(self) -> User:
        user = User(
            email=f"user-{uuid.uuid4().hex[:8]}@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        self._session.add(user)
        self._session.commit()
        return user


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def password_reset_backend(request, postgres_session) -> RepoBackend:
    """Parameterized fixture that yields both fake and SQL backends."""
    if request.param == "fake":
        return FakeBackend()
    else:
        return SqlBackend(postgres_session)
