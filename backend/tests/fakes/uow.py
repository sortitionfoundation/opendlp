"""ABOUTME: FakeUnitOfWork and the FakeStore of repositories it shares between instances
ABOUTME: Part of the tests.fakes package of in-memory test doubles"""

import uuid
from typing import TYPE_CHECKING, Any

from opendlp.service_layer.unit_of_work import AbstractUnitOfWork, UnitOfWorkError
from opendlp.service_layer.unit_of_work_events import UnitOfWorkEvents
from tests.fakes.repositories.assemblies import (
    FakeAssemblyExportGSheetRepository,
    FakeAssemblyGSheetRepository,
    FakeAssemblyRepository,
    FakeSelectionRunRecordRepository,
    FakeTargetCategoryRepository,
)
from tests.fakes.repositories.registration import (
    FakeEmailTemplateRepository,
    FakeRegistrationContentBlockRepository,
    FakeRegistrationDocumentRepository,
    FakeRegistrationImageRepository,
    FakeRegistrationPageHtmlRepository,
    FakeRegistrationPageRepository,
    FakeRespondentEmailSendRecordRepository,
)
from tests.fakes.repositories.respondents import (
    FakeRespondentFieldDefinitionRepository,
    FakeRespondentFieldMappingEntryRepository,
    FakeRespondentRepository,
)
from tests.fakes.repositories.users import (
    FakeEmailConfirmationTokenRepository,
    FakePasswordResetTokenRepository,
    FakeTotpVerificationAttemptRepository,
    FakeTwoFactorAuditLogRepository,
    FakeUserAssemblyRoleRepository,
    FakeUserBackupCodeRepository,
    FakeUserInviteRepository,
    FakeUserRepository,
    FakeUserSignupSurveyRepository,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from opendlp.domain.events import Event
    from opendlp.service_layer.unit_of_work_events import EventHandlers


# The repository attribute names a FakeUnitOfWork exposes, in one place so the
# store, the aliases and the snapshot/rollback logic stay in sync.
_REPO_NAMES = (
    "users",
    "assemblies",
    "assembly_gsheets",
    "assembly_export_gsheets",
    "user_invites",
    "user_signup_surveys",
    "user_assembly_roles",
    "selection_run_records",
    "user_backup_codes",
    "two_factor_audit_logs",
    "totp_attempts",
    "password_reset_tokens",
    "email_confirmation_tokens",
    "target_categories",
    "respondents",
    "respondent_field_definitions",
    "respondent_field_mapping_entries",
    "registration_content_blocks",
    "registration_pages",
    "registration_page_html_sources",
    "registration_images",
    "registration_documents",
    "email_templates",
    "respondent_email_send_records",
)


class FakeStore:
    """In-memory repositories shared across FakeUnitOfWork instances.

    A single FakeStore lets several FakeUnitOfWork instances created within one
    request (``load_user``, a permission decorator, the route's own UoW) see the
    same data, and lets data persist across requests within a test. This is what
    makes fake-backed e2e tests possible.
    """

    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.assemblies = FakeAssemblyRepository(users=self.users)
        self.assembly_gsheets = FakeAssemblyGSheetRepository()
        self.assembly_export_gsheets = FakeAssemblyExportGSheetRepository()
        self.user_invites = FakeUserInviteRepository()
        self.user_signup_surveys = FakeUserSignupSurveyRepository()
        self.user_assembly_roles = FakeUserAssemblyRoleRepository(users=self.users)
        self.selection_run_records = FakeSelectionRunRecordRepository()
        self.user_backup_codes = FakeUserBackupCodeRepository()
        self.two_factor_audit_logs = FakeTwoFactorAuditLogRepository()
        self.totp_attempts = FakeTotpVerificationAttemptRepository()
        self.password_reset_tokens = FakePasswordResetTokenRepository()
        self.email_confirmation_tokens = FakeEmailConfirmationTokenRepository()
        self.target_categories = FakeTargetCategoryRepository()
        self.respondents = FakeRespondentRepository()
        self.respondent_field_definitions = FakeRespondentFieldDefinitionRepository()
        self.respondent_field_mapping_entries = FakeRespondentFieldMappingEntryRepository()
        self.registration_content_blocks = FakeRegistrationContentBlockRepository()
        self.registration_pages = FakeRegistrationPageRepository()
        self.registration_page_html_sources = FakeRegistrationPageHtmlRepository()
        self.registration_images = FakeRegistrationImageRepository()
        self.registration_documents = FakeRegistrationDocumentRepository()
        self.email_templates = FakeEmailTemplateRepository()
        self.respondent_email_send_records = FakeRespondentEmailSendRecordRepository()


class ClosedRepository:
    """Stand-in bound to a strict FakeUnitOfWork's repository names outside its block.

    Any attribute access raises, so a test that reaches for ``uow.users`` without
    an open context fails at the point of the mistake rather than silently
    working in a way the real UnitOfWork will not.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, attr: str) -> Any:
        raise UnitOfWorkError(
            f"uow.{self._name} is only available inside `with uow:`. "
            f"To arrange or inspect data outside the context, use uow.fake_{self._name}."
        )


class FakeUnitOfWork(AbstractUnitOfWork):
    """Fake Unit of Work implementation for testing.

    With no ``store`` it owns a private FakeStore (the long-standing behaviour
    used by unit tests). With a shared ``store`` it behaves like a real UoW over
    a shared database: every instance sees the same data, and the ``with`` block
    rolls back on exception via a snapshot of each repository.

    The repositories are only bound inside the ``with`` block, as they are on the
    real UnitOfWork. The ``fake_<name>`` aliases are unaffected and stay usable
    throughout as the arrange/inspect seam.

    With no ``event_handlers`` it runs none: a recorded event lands on
    ``uow.events`` for the test to assert on and nothing else happens. Pass
    ``handlers.build_event_handlers(task_runner)`` to run the application's handlers.
    """

    def __init__(self, store: FakeStore | None = None, event_handlers: EventHandlers | None = None) -> None:
        self._events = UnitOfWorkEvents(event_handlers if event_handlers is not None else {})
        self._shared = store is not None
        self._store = store if store is not None else FakeStore()
        # The legacy ``uow.fake_users`` alias is bound once and never withdrawn.
        for name in _REPO_NAMES:
            setattr(self, f"fake_{name}", getattr(self._store, name))
        self._bind_repositories(open_context=False)
        self.committed = False
        self.expire_all_calls = 0
        self.locked_assembly_ids: list[uuid.UUID] = []
        self._snapshot: dict[str, list[Any]] | None = None

    @property
    def store(self) -> FakeStore:
        """The backing store, for tests that need to reach a sibling repository directly."""
        return self._store

    def _bind_repositories(self, open_context: bool) -> None:
        self._in_context = open_context
        for name in _REPO_NAMES:
            repo = getattr(self._store, name) if open_context else ClosedRepository(name)
            setattr(self, name, repo)

    def __enter__(self) -> AbstractUnitOfWork:
        self._bind_repositories(open_context=True)
        self._events.start()
        if self._shared:
            self._take_snapshot()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        # Match SqlAlchemyUnitOfWork: roll back the shared store on exception.
        if self._shared and exc_type is not None:
            self.rollback()
        # Match SqlAlchemyUnitOfWork: a clean exit is a commit as far as the
        # after-commit callbacks go, and any other exit drops them. ``committed``
        # is left alone - it records an explicit commit() by the code under test.
        if exc_type is None:
            self._events.run_callbacks()
        else:
            self._events.discard_callbacks()
        self._bind_repositories(open_context=False)

    @property
    def events(self) -> list[Event]:
        return self._events.events

    def record(self, event: Event) -> None:
        self._events.record(event, self)

    def after_commit(self, callback: Callable[[], object]) -> None:
        self._events.after_commit(callback)

    def _take_snapshot(self) -> None:
        self._snapshot = {name: list(getattr(self._store, name)._items) for name in _REPO_NAMES}

    def commit(self) -> None:
        """Mark as committed; for a shared store the committed state is the new baseline."""
        self.committed = True
        if self._shared and self._snapshot is not None:
            self._take_snapshot()
        self._events.run_callbacks()

    def commit_and_reset(self) -> None:
        """Commit the work so far, then carry on against the same in-memory store.

        Nothing needs flushing for the fake; the repositories already hold the
        data, so this just records the commit and continues.
        """
        self.commit()

    def flush(self) -> None:
        """Nothing to send anywhere: the fake store has no write ordering to get wrong."""

    def rollback(self) -> None:
        """Undo uncommitted changes.

        For a shared store, restore each repository to the snapshot taken on
        ``__enter__`` (or the last commit). For a private store, clear everything
        (the long-standing behaviour relied on by existing unit tests).
        """
        if self._shared:
            if self._snapshot is not None:
                for name, items in self._snapshot.items():
                    getattr(self._store, name)._items[:] = items
        else:
            for name in _REPO_NAMES:
                getattr(self._store, name)._items.clear()
        self.committed = False
        self._events.discard_callbacks()

    def expire_all(self) -> None:
        """No-op for in-memory repositories — record the call for assertions."""
        self.expire_all_calls += 1

    def lock_assembly_for_write(self, assembly_id: uuid.UUID) -> None:
        """Nothing to lock in memory — record the call so tests can assert a guard took the lock.

        Refuses outside ``with uow:`` as the real one does, since the real
        lock is tied to the transaction the context opens.
        """
        if not self._in_context:
            raise UnitOfWorkError("lock_assembly_for_write is only available inside `with uow:`")
        self.locked_assembly_ids.append(assembly_id)
