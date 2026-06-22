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
    SqlAlchemyEmailTemplateRepository,
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemyRegistrationImageRepository,
    SqlAlchemyRegistrationPageHtmlRepository,
    SqlAlchemyRegistrationPageRepository,
    SqlAlchemyRespondentEmailSendRecordRepository,
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
from opendlp.domain.email_send_record import EmailSendOutcome, RespondentEmailSendRecord
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.registration_image import RegistrationImage
from opendlp.domain.registration_page import RegistrationPage
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
    FakeEmailTemplateRepository,
    FakePasswordResetTokenRepository,
    FakeRegistrationImageRepository,
    FakeRegistrationPageHtmlRepository,
    FakeRegistrationPageRepository,
    FakeRespondentEmailSendRecordRepository,
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


def make_registration_page(assembly_id: uuid.UUID | None = None, **kwargs: Any) -> RegistrationPage:
    """Create a RegistrationPage domain object with sensible defaults."""
    if assembly_id is None:
        assembly_id = uuid.uuid4()
    return RegistrationPage(assembly_id=assembly_id, **kwargs)


def make_registration_image(registration_page_id: uuid.UUID, sha256: str = "", **kwargs: Any) -> RegistrationImage:
    """Create a RegistrationImage domain object with sensible defaults."""
    if not sha256:
        sha256 = uuid.uuid4().hex + uuid.uuid4().hex[:32]
    defaults: dict[str, Any] = {"byte_size": 8, "width": 10, "height": 10, "data": b"pngbytes"}
    defaults.update(kwargs)
    return RegistrationImage(registration_page_id=registration_page_id, sha256=sha256, **defaults)


def make_respondent(assembly_id: uuid.UUID | None = None, **kwargs: Any) -> Respondent:
    """Create a Respondent domain object with sensible defaults."""
    if assembly_id is None:
        assembly_id = uuid.uuid4()
    defaults: dict[str, Any] = {"external_id": _next_id(), "email": "respondent@example.com"}
    defaults.update(kwargs)
    return Respondent(assembly_id=assembly_id, **defaults)


def make_email_template(assembly_id: uuid.UUID | None = None, **kwargs: Any) -> EmailTemplate:
    """Create an EmailTemplate domain object with sensible defaults."""
    if assembly_id is None:
        assembly_id = uuid.uuid4()
    defaults: dict[str, Any] = {"name": "Auto-reply", "subject": "Thanks", "body_html": "<p>Hi</p>"}
    defaults.update(kwargs)
    return EmailTemplate(assembly_id=assembly_id, **defaults)


def make_respondent_email_send_record(respondent_id: uuid.UUID, **kwargs: Any) -> RespondentEmailSendRecord:
    """Create a RespondentEmailSendRecord domain object with sensible defaults."""
    defaults: dict[str, Any] = {
        "to_email": "respondent@example.com",
        "subject": "Thanks",
        "outcome": EmailSendOutcome.SENT,
    }
    defaults.update(kwargs)
    return RespondentEmailSendRecord(respondent_id=respondent_id, **defaults)


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

    def fresh_get_field_definition(self, field_id: uuid.UUID) -> Any:
        """Fetch a field definition from storage without any instance-cache effects."""
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

    def make_registration_page(self, assembly_id: uuid.UUID | None = None, **kwargs: Any) -> RegistrationPage:
        if assembly_id is None:
            assembly_id = self.make_assembly().id
        page = make_registration_page(assembly_id=assembly_id, **kwargs)
        self.persist(page)
        self.commit()
        return page

    def make_registration_image(
        self, registration_page_id: uuid.UUID | None = None, **kwargs: Any
    ) -> RegistrationImage:
        if registration_page_id is None:
            registration_page_id = self.make_registration_page().id
        image = make_registration_image(registration_page_id=registration_page_id, **kwargs)
        self.repo.add(image)
        self.commit()
        return image

    def make_respondent(self, assembly_id: uuid.UUID | None = None, **kwargs: Any) -> Respondent:
        if assembly_id is None:
            assembly_id = self.make_assembly().id
        respondent = make_respondent(assembly_id=assembly_id, **kwargs)
        self.persist(respondent)
        self.commit()
        return respondent

    def make_email_template(self, assembly_id: uuid.UUID | None = None, **kwargs: Any) -> EmailTemplate:
        if assembly_id is None:
            assembly_id = self.make_assembly().id
        template = make_email_template(assembly_id=assembly_id, **kwargs)
        self.repo.add(template)
        self.commit()
        return template


class FakeContractBackend(ContractBackend):
    """Backend using in-memory fake repositories."""

    def persist(self, *items: Any) -> None:
        pass  # fakes don't need FK objects persisted

    def fresh_get_respondent(self, respondent_id: uuid.UUID) -> Respondent | None:
        return self.repo.get(respondent_id)  # type: ignore[no-any-return]

    def fresh_get_field_definition(self, field_id: uuid.UUID) -> Any:
        return self.repo.get(field_id)


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

    def fresh_get_field_definition(self, field_id: uuid.UUID) -> Any:
        assert self._session_factory is not None, "session_factory required for fresh reads"
        with self._session_factory() as fresh_session:
            return SqlAlchemyRespondentFieldDefinitionRepository(fresh_session).get(field_id)


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
def respondent_field_definition_backend(request, postgres_session, postgres_session_factory) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeRespondentFieldDefinitionRepository(), commit=lambda: None)
    return SqlContractBackend(
        repo=SqlAlchemyRespondentFieldDefinitionRepository(postgres_session),
        session=postgres_session,
        session_factory=postgres_session_factory,
    )


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def registration_page_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeRegistrationPageRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyRegistrationPageRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def registration_page_html_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeRegistrationPageHtmlRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyRegistrationPageHtmlRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def registration_image_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeRegistrationImageRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyRegistrationImageRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def email_template_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeEmailTemplateRepository(), commit=lambda: None)
    return SqlContractBackend(repo=SqlAlchemyEmailTemplateRepository(postgres_session), session=postgres_session)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def respondent_email_send_record_backend(request, postgres_session) -> ContractBackend:
    if request.param == "fake":
        return FakeContractBackend(repo=FakeRespondentEmailSendRecordRepository(), commit=lambda: None)
    return SqlContractBackend(
        repo=SqlAlchemyRespondentEmailSendRecordRepository(postgres_session), session=postgres_session
    )
