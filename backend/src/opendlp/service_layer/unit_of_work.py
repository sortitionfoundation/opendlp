"""ABOUTME: Unit of Work pattern implementation for transaction management
ABOUTME: Coordinates repository operations within database transactions"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, Self

from opendlp.adapters.sql_repository import (
    SqlAlchemyAssemblyGSheetRepository,
    SqlAlchemyAssemblyRepository,
    SqlAlchemyAssemblyRespondentGSheetRepository,
    SqlAlchemyEmailConfirmationTokenRepository,
    SqlAlchemyEmailTemplateRepository,
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemyRegistrationDocumentRepository,
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

if TYPE_CHECKING:
    from types import TracebackType

    from sqlalchemy.orm import Session, sessionmaker

    from opendlp.service_layer.repositories import (
        AssemblyGSheetRepository,
        AssemblyRepository,
        AssemblyRespondentGSheetRepository,
        EmailConfirmationTokenRepository,
        EmailTemplateRepository,
        PasswordResetTokenRepository,
        RegistrationDocumentRepository,
        RegistrationImageRepository,
        RegistrationPageHtmlRepository,
        RegistrationPageRepository,
        RespondentEmailSendRecordRepository,
        RespondentFieldDefinitionRepository,
        RespondentRepository,
        SelectionRunRecordRepository,
        TargetCategoryRepository,
        TotpVerificationAttemptRepository,
        TwoFactorAuditLogRepository,
        UserAssemblyRoleRepository,
        UserBackupCodeRepository,
        UserInviteRepository,
        UserRepository,
    )


class AbstractUnitOfWork(abc.ABC):
    """Abstract Unit of Work interface."""

    users: UserRepository
    assemblies: AssemblyRepository
    assembly_gsheets: AssemblyGSheetRepository
    assembly_respondent_gsheets: AssemblyRespondentGSheetRepository
    user_invites: UserInviteRepository
    user_assembly_roles: UserAssemblyRoleRepository
    selection_run_records: SelectionRunRecordRepository
    password_reset_tokens: PasswordResetTokenRepository
    email_confirmation_tokens: EmailConfirmationTokenRepository
    user_backup_codes: UserBackupCodeRepository
    two_factor_audit_logs: TwoFactorAuditLogRepository
    totp_attempts: TotpVerificationAttemptRepository
    target_categories: TargetCategoryRepository
    respondents: RespondentRepository
    respondent_field_definitions: RespondentFieldDefinitionRepository
    registration_pages: RegistrationPageRepository
    registration_page_html_sources: RegistrationPageHtmlRepository
    registration_images: RegistrationImageRepository
    registration_documents: RegistrationDocumentRepository
    email_templates: EmailTemplateRepository
    respondent_email_send_records: RespondentEmailSendRecordRepository

    def __enter__(self) -> Self:
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
    def commit_and_reset(self) -> None:
        """Commit the work so far, then keep using the same UnitOfWork.

        Lets a single ``with uow:`` block contain more than one logical unit of
        work without opening a second context: the first unit is made durable,
        then work continues against the same UnitOfWork. Replaces the older
        pattern of opening ``uow``/``uow2``/``uow3`` in one request.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def rollback(self) -> None:
        """Rollback the current transaction."""
        raise NotImplementedError

    @abc.abstractmethod
    def expire_all(self) -> None:
        """Drop cached attributes on all loaded objects.

        The next attribute access on any previously-loaded instance will
        re-fetch from the database. Use this when polling for changes made
        by another process (e.g. a Celery worker updating a run record).
        """
        raise NotImplementedError


class UnitOfWorkError(Exception):
    """Exception raised when Unit of Work operations fail."""


class ClosedRepository:
    """Stand-in bound to a UnitOfWork's repository names outside its block.

    Repositories hold their own session reference, so guarding the ``session``
    property alone would still let ``uow.users.get(...)`` run on a closed
    session. Any attribute access here raises instead.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, attr: str) -> Any:
        raise UnitOfWorkError(f"uow.{self._name} is only available inside `with uow: ...`")


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """SQLAlchemy implementation of Unit of Work pattern.

    The session exists only for the duration of the ``with`` block. Outside it
    both ``session`` and the repositories raise: a closed SQLAlchemy session is
    still usable and silently autobegins a new transaction, so work done through
    a leaked UnitOfWork would belong to a transaction nobody commits while its
    connection sits ``idle in transaction`` holding locks.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory
        self._session: Session | None = None
        self._close_repositories()

    def _close_repositories(self) -> None:
        for name in AbstractUnitOfWork.__annotations__:
            setattr(self, name, ClosedRepository(name))

    @property
    def session(self) -> Session:
        if self._session is None:
            raise UnitOfWorkError("uow.session is only available inside `with uow: ...`")
        return self._session

    def __enter__(self) -> Self:
        self._session = self.session_factory()

        # Initialize repositories with the session
        self.users = SqlAlchemyUserRepository(self.session)
        self.assemblies = SqlAlchemyAssemblyRepository(self.session)
        self.assembly_gsheets = SqlAlchemyAssemblyGSheetRepository(self.session)
        self.assembly_respondent_gsheets = SqlAlchemyAssemblyRespondentGSheetRepository(self.session)
        self.user_invites = SqlAlchemyUserInviteRepository(self.session)
        self.user_assembly_roles = SqlAlchemyUserAssemblyRoleRepository(self.session)
        self.selection_run_records = SqlAlchemySelectionRunRecordRepository(self.session)
        self.password_reset_tokens = SqlAlchemyPasswordResetTokenRepository(self.session)
        self.email_confirmation_tokens = SqlAlchemyEmailConfirmationTokenRepository(self.session)
        self.user_backup_codes = SqlAlchemyUserBackupCodeRepository(self.session)
        self.two_factor_audit_logs = SqlAlchemyTwoFactorAuditLogRepository(self.session)
        self.totp_attempts = SqlAlchemyTotpVerificationAttemptRepository(self.session)
        self.target_categories = SqlAlchemyTargetCategoryRepository(self.session)
        self.respondents = SqlAlchemyRespondentRepository(self.session)
        self.respondent_field_definitions = SqlAlchemyRespondentFieldDefinitionRepository(self.session)
        self.registration_pages = SqlAlchemyRegistrationPageRepository(self.session)
        self.registration_page_html_sources = SqlAlchemyRegistrationPageHtmlRepository(self.session)
        self.registration_images = SqlAlchemyRegistrationImageRepository(self.session)
        self.registration_documents = SqlAlchemyRegistrationDocumentRepository(self.session)
        self.email_templates = SqlAlchemyEmailTemplateRepository(self.session)
        self.respondent_email_send_records = SqlAlchemyRespondentEmailSendRecordRepository(self.session)

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        session = self.session
        try:
            if exc_type is not None:
                self.rollback()
            else:
                self.commit()
        finally:
            # try/finally so a failing commit still releases the connection, and
            # clearing _session so the closed session can never be resurrected.
            session.close()
            self._session = None
            self._close_repositories()

    def commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()

    def commit_and_reset(self) -> None:
        """Commit the work so far, then keep using the same session.

        The session remains usable after ``commit()`` because the session
        factory is built with ``expire_on_commit=False``, so subsequent work in
        the same ``with`` block runs against the same session and repositories.
        """
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.session.rollback()

    def flush(self) -> None:
        """
        Flush pending changes to the database without committing.
        This allows new objects to get an ID that can be referenced by other objects.
        """
        self.session.flush()

    def expire_all(self) -> None:
        """Expire all instances in the session's identity map.

        Required because the session factory uses ``expire_on_commit=False``,
        so cached instances would otherwise hide writes made by other
        processes (notably Celery workers updating SelectionRunRecord rows).
        """
        self.session.expire_all()
