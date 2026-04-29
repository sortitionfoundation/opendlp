"""ABOUTME: Shared fixtures for contract tests that run against both fake and SQL repositories.
ABOUTME: Provides a parameterized backend abstraction so each test suite runs with both implementations."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from opendlp.adapters.sql_repository import (
    SqlAlchemyAssemblyGSheetRepository,
    SqlAlchemyAssemblyRepository,
    SqlAlchemyEmailConfirmationTokenRepository,
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemyRespondentFieldDefinitionRepository,
    SqlAlchemyRespondentRepository,
    SqlAlchemySelectionRunRecordRepository,
    SqlAlchemyTargetCategoryRepository,
    SqlAlchemyTotpVerificationAttemptRepository,
    SqlAlchemyTwoFactorAuditLogRepository,
    SqlAlchemyUserAssemblyRoleRepository,
    SqlAlchemyUserBackupCodeRepository,
    SqlAlchemyUserInviteRepository,
    SqlAlchemyUserRepository,
)
from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User
from opendlp.domain.value_objects import (
    AssemblyStatus,
    GlobalRole,
)
from tests.fakes import (
    FakeAssemblyGSheetRepository,
    FakeAssemblyRepository,
    FakeEmailConfirmationTokenRepository,
    FakePasswordResetTokenRepository,
    FakeRespondentFieldDefinitionRepository,
    FakeRespondentRepository,
    FakeSelectionRunRecordRepository,
    FakeTargetCategoryRepository,
    FakeTotpVerificationAttemptRepository,
    FakeTwoFactorAuditLogRepository,
    FakeUnitOfWork,
    FakeUserBackupCodeRepository,
    FakeUserInviteRepository,
    FakeUserRepository,
)

# ---------------------------------------------------------------------------
# Helpers to generate unique domain objects
# ---------------------------------------------------------------------------

_counter = 0


def _next_id() -> str:
    global _counter
    _counter += 1
    return f"{_counter:04d}-{uuid.uuid4().hex[:6]}"


def make_user(
    email: str = "",
    global_role: GlobalRole = GlobalRole.USER,
    first_name: str = "",
    last_name: str = "",
    is_active: bool = True,
    **kwargs: Any,
) -> User:
    """Create a User domain object with sensible defaults."""
    if not email:
        email = f"user-{_next_id()}@example.com"
    return User(
        email=email,
        global_role=global_role,
        first_name=first_name,
        last_name=last_name,
        is_active=is_active,
        password_hash="hash",  # pragma: allowlist secret
        **kwargs,
    )


def make_assembly(
    title: str = "",
    status: AssemblyStatus = AssemblyStatus.ACTIVE,
    **kwargs: Any,
) -> Assembly:
    """Create an Assembly domain object with sensible defaults."""
    if not title:
        title = f"Assembly {_next_id()}"
    return Assembly(
        title=title,
        question="Test question?",
        first_assembly_date=date.today() + timedelta(days=30),
        status=status,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Backend abstraction
# ---------------------------------------------------------------------------


@dataclass
class ContractBackend:
    """Wraps a repository and a commit callable so tests work with both backends.

    Subclasses override persist() to handle SQL session.add() vs no-op for fakes.
    """

    repo: Any
    commit: Callable[[], None]

    def persist(self, *items: Any) -> None:
        """Persist domain objects that the repo under test depends on (e.g. Users for FK)."""
        raise NotImplementedError

    def fresh_get_respondent(self, respondent_id: uuid.UUID) -> Respondent | None:
        """Fetch a respondent from storage without any instance-cache effects."""
        raise NotImplementedError

    def make_user(self, **kwargs: Any) -> User:
        user = make_user(**kwargs)
        self.persist(user)
        self.commit()
        return user

    def make_assembly(self, **kwargs: Any) -> Assembly:
        assembly = make_assembly(**kwargs)
        self.persist(assembly)
        self.commit()
        return assembly


class FakeContractBackend(ContractBackend):
    """Backend using in-memory fake repositories."""

    def persist(self, *items: Any) -> None:
        pass  # fakes don't need FK objects persisted

    def fresh_get_respondent(self, respondent_id: uuid.UUID) -> Respondent | None:
        return self.repo.get(respondent_id)  # type: ignore[no-any-return]


class SqlContractBackend(ContractBackend):
    """Backend using real SqlAlchemy repositories with a Postgres session."""

    def __init__(self, repo: Any, session: Session, session_factory: Any = None) -> None:
        self._session = session
        self._session_factory = session_factory
        super().__init__(repo=repo, commit=session.commit)

    def persist(self, *items: Any) -> None:
        for item in items:
            self._session.add(item)
        self._session.flush()

    def fresh_get_respondent(self, respondent_id: uuid.UUID) -> Respondent | None:
        assert self._session_factory is not None, "session_factory required for fresh reads"
        with self._session_factory() as fresh_session:
            return SqlAlchemyRespondentRepository(fresh_session).get(respondent_id)


# ---------------------------------------------------------------------------
# Parameterized fixtures for each repository
# ---------------------------------------------------------------------------


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def password_reset_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakePasswordResetTokenRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyPasswordResetTokenRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def email_confirmation_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeEmailConfirmationTokenRepository(), commit=lambda: None)
    return SqlContractBackend(
        repo=SqlAlchemyEmailConfirmationTokenRepository(postgres_session), session=postgres_session
    )


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def user_backup_code_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeUserBackupCodeRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyUserBackupCodeRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def two_factor_audit_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeTwoFactorAuditLogRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyTwoFactorAuditLogRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def totp_attempt_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeTotpVerificationAttemptRepository(), commit=lambda: None)
    return SqlContractBackend(
        repo=SqlAlchemyTotpVerificationAttemptRepository(postgres_session), session=postgres_session
    )


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def user_invite_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeUserInviteRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyUserInviteRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def user_assembly_role_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        uow = FakeUnitOfWork()
        return FakeContractBackend(repo=uow.user_assembly_roles, commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyUserAssemblyRoleRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def user_repo_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeUserRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyUserRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def assembly_repo_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeAssemblyRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyAssemblyRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def selection_run_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeSelectionRunRecordRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemySelectionRunRecordRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def target_category_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeTargetCategoryRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyTargetCategoryRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def respondent_backend(request, postgres_session, postgres_session_factory) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeRespondentRepository(), commit=lambda: None)
    return SqlContractBackend(
        repo=SqlAlchemyRespondentRepository(postgres_session),
        session=postgres_session,
        session_factory=postgres_session_factory,
    )


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def assembly_gsheet_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeAssemblyGSheetRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyAssemblyGSheetRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def respondent_field_definition_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeRespondentFieldDefinitionRepository(), commit=lambda: None)
    return SqlContractBackend(
        repo=SqlAlchemyRespondentFieldDefinitionRepository(postgres_session), session=postgres_session
    )
