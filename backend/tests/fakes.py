"""ABOUTME: Fake repository implementations for testing
ABOUTME: In-memory repositories that implement the same interfaces as real ones"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from opendlp.adapters.tabular_export import AbstractTabularExportTarget, TabularData
from opendlp.domain.assembly import Assembly, AssemblyGSheet, SelectionRunRecord
from opendlp.domain.assembly_respondent_gsheet import AssemblyRespondentGSheet
from opendlp.domain.email_confirmation import EmailConfirmationToken
from opendlp.domain.email_send_record import RespondentEmailSendRecord
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.password_reset import PasswordResetToken
from opendlp.domain.registration_image import RegistrationImage
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageHtml
from opendlp.domain.respondent_field_schema import (
    GROUP_DISPLAY_ORDER,
    RespondentFieldDefinition,
)
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory
from opendlp.domain.totp_attempts import TotpVerificationAttempt
from opendlp.domain.two_factor_audit import TwoFactorAuditLog
from opendlp.domain.user_backup_codes import UserBackupCode
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import (
    AssemblyStatus,
    GlobalRole,
    RespondentAction,
    RespondentStatus,
    SelectionTaskType,
)
from opendlp.service_layer.repositories import (
    AbstractRepository,
    AssemblyGSheetRepository,
    AssemblyRepository,
    AssemblyRespondentGSheetRepository,
    EmailConfirmationTokenRepository,
    EmailTemplateRepository,
    PasswordResetTokenRepository,
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
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


class FakeRepository(AbstractRepository):
    """Base fake repository with in-memory storage."""

    def __init__(self, items: list[Any] | None = None):
        self._items = list(items) if items else []

    def add(self, item: Any) -> None:
        """Add an item to the repository."""
        self._items.append(item)

    def get(self, item_id: uuid.UUID) -> Any | None:
        """Get an item by its ID."""
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def all(self) -> Iterable[Any]:
        """Get all items in the repository."""
        return list(self._items)


class FakeUserRepository(FakeRepository, UserRepository):
    """Fake implementation of UserRepository."""

    def filter(self, role: str | None = None, active: bool | None = None) -> Iterable[User]:
        """List users filtered by criteria."""
        users = list(self._items)
        if role:
            role_enum = GlobalRole(role.lower())
            users = [user for user in users if user.global_role == role_enum]
        if active is not None:
            users = [user for user in users if user.is_active == active]
        return users

    def filter_paginated(
        self,
        role: str | None = None,
        active: bool | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """List users filtered by criteria with pagination."""
        users = list(self._items)

        # Apply role filter
        if role:
            users = [user for user in users if user.global_role.value == role.lower()]

        # Apply active filter
        if active is not None:
            users = [user for user in users if user.is_active == active]

        # Apply search filter (case-insensitive search across email, first_name, last_name)
        if search:
            search_lower = search.lower()
            users = [
                user
                for user in users
                if search_lower in user.email.lower()
                or (user.first_name and search_lower in user.first_name.lower())
                or (user.last_name and search_lower in user.last_name.lower())
            ]

        # Get total count before pagination
        total_count = len(users)

        # Apply ordering (by created_at desc) and pagination
        users_sorted = sorted(users, key=lambda u: u.created_at, reverse=True)
        paginated_users = users_sorted[offset : offset + limit]

        return list(paginated_users), total_count

    def get_by_email(self, email: str) -> User | None:
        """Get a user by their email address."""
        for user in self._items:
            if user.email == email:
                return user
        return None

    def get_users_for_assembly(self, assembly_id: uuid.UUID) -> Iterable[User]:
        """Get all users who have roles in the given assembly."""
        users_with_roles = []
        for user in self._items:
            if any(role.assembly_id == assembly_id for role in user.assembly_roles):
                users_with_roles.append(user)
        return users_with_roles

    def get_users_not_in_assembly(self, assembly_id: uuid.UUID) -> Iterable[User]:
        """Get all users who do NOT have any role in the given assembly."""
        users_with_roles = {user.id for user in self.get_users_for_assembly(assembly_id)}
        return [user for user in self._items if user.id not in users_with_roles]

    def search_users_not_in_assembly(self, assembly_id: uuid.UUID, search_term: str) -> Iterable[User]:
        """Search users not in assembly by email (prioritized) and name fields.

        Supports space-separated search fragments. All fragments must match
        (AND logic between fragments, OR logic within a fragment's field matches).
        Example: "gm to" matches "tom.jones@gmail.com" (gm matches email, to matches name).
        """
        # Return empty list if search term is empty
        if not search_term:
            return []

        # Get users not in assembly
        users = self.get_users_not_in_assembly(assembly_id)

        # Split search term into fragments (space-separated)
        search_fragments = search_term.strip().split()

        # Filter: all fragments must match (AND logic between fragments)
        matching_users = []
        for user in users:
            all_fragments_match = True
            for fragment in search_fragments:
                fragment_lower = fragment.lower()
                # Fragment can match email, first_name, or last_name (OR logic within fragment)
                fragment_matches = (
                    fragment_lower in user.email.lower()
                    or (user.first_name and fragment_lower in user.first_name.lower())
                    or (user.last_name and fragment_lower in user.last_name.lower())
                )
                if not fragment_matches:
                    all_fragments_match = False
                    break

            if all_fragments_match:
                matching_users.append(user)

        # Sort: email matches on first fragment first, then by email alphabetically
        first_fragment_lower = search_fragments[0].lower()
        email_matches = [u for u in matching_users if first_fragment_lower in u.email.lower()]
        name_only_matches = [u for u in matching_users if u not in email_matches]
        email_matches.sort(key=lambda u: u.email)
        name_only_matches.sort(key=lambda u: u.email)

        return email_matches + name_only_matches

    def get_by_oauth_credentials(self, provider: str, oauth_id: str) -> User | None:
        """Get a user by their OAuth provider and ID."""
        for user in self._items:
            if user.oauth_provider == provider and user.oauth_id == oauth_id:
                return user
        return None


class FakeAssemblyRepository(FakeRepository, AssemblyRepository):
    """Fake implementation of AssemblyRepository."""

    def get_active_assemblies(self) -> Iterable[Assembly]:
        """Get all assemblies that are currently active."""
        return [assembly for assembly in self._items if assembly.is_active()]

    def get_assemblies_for_user(self, user_id: uuid.UUID) -> Iterable[Assembly]:
        """Get all assemblies that a user has access to."""
        # This would typically involve checking UserAssemblyRole records
        # For simplicity, returning all active assemblies
        return self.get_active_assemblies()

    def get_assemblies_by_status(self, status: AssemblyStatus) -> Iterable[Assembly]:
        """Get assemblies by their status."""
        return [assembly for assembly in self._items if assembly.status == status]

    def search_by_title(self, search_term: str) -> Iterable[Assembly]:
        """Search assemblies by title (case-insensitive partial match)."""
        search_term = search_term.lower()
        return [assembly for assembly in self._items if search_term in assembly.title.lower()]


class FakeUserInviteRepository(FakeRepository, UserInviteRepository):
    """Fake implementation of UserInviteRepository."""

    def get_by_code(self, code: str) -> UserInvite | None:
        """Get an invite by its code."""
        for invite in self._items:
            if invite.code == code:
                return invite
        return None

    def get_valid_invites(self) -> Iterable[UserInvite]:
        """Get all invites that are valid (not expired and not used)."""
        return [invite for invite in self._items if invite.is_valid()]

    def get_invites_created_by(self, user_id: uuid.UUID) -> Iterable[UserInvite]:
        """Get all invites created by a specific user."""
        return [invite for invite in self._items if invite.created_by == user_id]

    def get_expired_invites(self) -> Iterable[UserInvite]:
        """Get all invites that have expired."""
        return [invite for invite in self._items if not invite.is_valid()]

    def get_used_invites(self) -> Iterable[UserInvite]:
        """Get all invites that have been used."""
        return [invite for invite in self._items if invite.used_by is not None]

    def delete(self, item: UserInvite) -> None:
        """Delete an invite from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeUserAssemblyRoleRepository(FakeRepository, UserAssemblyRoleRepository):
    """Fake implementation for UserAssemblyRole repository."""

    def get_by_user_and_assembly(self, user_id: uuid.UUID, assembly_id: uuid.UUID) -> UserAssemblyRole | None:
        """Get role for user in specific assembly."""
        for role in self._items:
            if role.user_id == user_id and role.assembly_id == assembly_id:
                return role
        return None

    def get_roles_for_user(self, user_id: uuid.UUID) -> Iterable[UserAssemblyRole]:
        """Get all roles for a user."""
        return [role for role in self._items if role.user_id == user_id]

    def get_roles_for_assembly(self, assembly_id: uuid.UUID) -> Iterable[UserAssemblyRole]:
        """Get all roles for an assembly."""
        return [role for role in self._items if role.assembly_id == assembly_id]

    def get_users_with_roles_for_assembly(self, assembly_id: uuid.UUID) -> list[tuple[User, UserAssemblyRole]]:
        """Get all users with their roles for a specific assembly.

        Note: This is a simplified implementation for testing.
        In production, this would be a single SQL join query.
        We need to access users from the UoW to pair them with roles.
        """
        # This method needs access to the users repository
        # For the fake implementation, we'll store a reference to the UoW
        # This will be set by the FakeUnitOfWork
        results = []
        roles = self.get_roles_for_assembly(assembly_id)
        if hasattr(self, "_uow"):
            for role in roles:
                user = self._uow.users.get(role.user_id)
                if user:
                    results.append((user, role))
        return results

    def remove_role(self, user_id: uuid.UUID, assembly_id: uuid.UUID) -> bool:
        """Remove a user's role from an assembly. Returns True if role was found and removed."""
        role = self.get_by_user_and_assembly(user_id, assembly_id)
        if not role:
            return False
        self._items = [r for r in self._items if r != role]
        return True


class FakeAssemblyGSheetRepository(FakeRepository, AssemblyGSheetRepository):
    """Fake implementation of AssemblyGSheetRepository."""

    def get(self, item_id: uuid.UUID) -> AssemblyGSheet | None:
        """Get an AssemblyGSheet by its ID."""
        for item in self._items:
            if item.assembly_gsheet_id == item_id:
                return item
        return None

    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> AssemblyGSheet | None:
        """Get an AssemblyGSheet by its assembly ID."""
        for item in self._items:
            if item.assembly_id == assembly_id:
                return item
        return None

    def delete(self, item: AssemblyGSheet) -> None:
        """Delete an AssemblyGSheet from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeAssemblyRespondentGSheetRepository(FakeRepository, AssemblyRespondentGSheetRepository):
    """Fake implementation of AssemblyRespondentGSheetRepository."""

    def get(self, item_id: uuid.UUID) -> AssemblyRespondentGSheet | None:
        """Get an AssemblyRespondentGSheet by its ID."""
        for item in self._items:
            if item.assembly_respondent_gsheet_id == item_id:
                return item
        return None

    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> AssemblyRespondentGSheet | None:
        """Get an AssemblyRespondentGSheet by its assembly ID."""
        for item in self._items:
            if item.assembly_id == assembly_id:
                return item
        return None

    def delete(self, item: AssemblyRespondentGSheet) -> None:
        """Delete an AssemblyRespondentGSheet from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeRegistrationPageRepository(FakeRepository, RegistrationPageRepository):
    """Fake implementation of RegistrationPageRepository."""

    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> RegistrationPage | None:
        """Get the registration page for an assembly, or None if it has none."""
        for item in self._items:
            if item.assembly_id == assembly_id:
                return item
        return None

    def get_by_url_slug(self, url_slug: str) -> RegistrationPage | None:
        """Get a registration page by its url_slug. Empty input returns None."""
        if not url_slug:
            return None
        for item in self._items:
            if item.url_slug == url_slug:
                return item
        return None

    def get_by_short_url_slug(self, short_url_slug: str) -> RegistrationPage | None:
        """Get a registration page by its short_url_slug. Empty input returns None."""
        if not short_url_slug:
            return None
        for item in self._items:
            if item.short_url_slug == short_url_slug:
                return item
        return None

    def delete(self, item: RegistrationPage) -> None:
        """Delete a RegistrationPage from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeRegistrationPageHtmlRepository(FakeRepository, RegistrationPageHtmlRepository):
    """Fake implementation of RegistrationPageHtmlRepository."""

    def get_by_page_id(self, registration_page_id: uuid.UUID) -> RegistrationPageHtml | None:
        """Get the HTML source for a registration page, or None if it has none."""
        for item in self._items:
            if item.registration_page_id == registration_page_id:
                return item
        return None

    def delete(self, item: RegistrationPageHtml) -> None:
        """Delete a RegistrationPageHtml from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeRegistrationImageRepository(FakeRepository, RegistrationImageRepository):
    """Fake implementation of RegistrationImageRepository."""

    def get_by_page_and_sha(self, registration_page_id: uuid.UUID, sha256: str) -> RegistrationImage | None:
        """Get an image for a page by its content hash, or None."""
        for item in self._items:
            if item.registration_page_id == registration_page_id and item.sha256 == sha256:
                return item
        return None

    def list_by_page_id(self, registration_page_id: uuid.UUID) -> list[RegistrationImage]:
        """Get all images for a registration page, oldest first."""
        items = [item for item in self._items if item.registration_page_id == registration_page_id]
        return sorted(items, key=lambda item: item.created_at)

    def count_by_page_id(self, registration_page_id: uuid.UUID) -> int:
        """Count images for a registration page."""
        return sum(1 for item in self._items if item.registration_page_id == registration_page_id)

    def delete(self, item: RegistrationImage) -> None:
        """Delete a RegistrationImage from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeSelectionRunRecordRepository(FakeRepository, SelectionRunRecordRepository):
    """Fake implementation of SelectionRunRecordRepository."""

    def get(self, item_id: uuid.UUID) -> SelectionRunRecord | None:
        """Get a SelectionRunRecord by its ID."""
        # SelectionRunRecord doesn't have an id field, only task_id
        return self.get_by_task_id(item_id)

    def get_by_task_id(self, task_id: uuid.UUID) -> SelectionRunRecord | None:
        """Get a SelectionRunRecord by its task ID."""
        for item in self._items:
            if item.task_id == task_id:
                return item
        return None

    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> Iterable[SelectionRunRecord]:
        """Get all SelectionRunRecords for a specific assembly."""
        return [item for item in self._items if item.assembly_id == assembly_id]

    def get_latest_for_assembly(
        self,
        assembly_id: uuid.UUID,
        task_type: SelectionTaskType | None = None,
    ) -> SelectionRunRecord | None:
        """Get the most recent SelectionRunRecord for an assembly, optionally filtered by task_type."""
        assembly_records = list(self.get_by_assembly_id(assembly_id))
        if task_type is not None:
            assembly_records = [r for r in assembly_records if r.task_type == task_type]
        if not assembly_records:
            return None
        return max(assembly_records, key=lambda r: r.created_at or datetime.min)

    def get_recent_for_assembly(
        self,
        assembly_id: uuid.UUID,
        task_type: SelectionTaskType = SelectionTaskType.SELECT_GSHEET,
        limit: int = 3,
    ) -> list[SelectionRunRecord]:
        """Get up to ``limit`` most recent records of a task type for an assembly, newest first."""
        matching = [r for r in self._items if r.assembly_id == assembly_id and r.task_type == task_type]
        matching.sort(key=lambda r: r.created_at or datetime.min, reverse=True)
        return matching[:limit]

    def prune_by_status(self, assembly_id: uuid.UUID, keep_successful: int = 500, keep_failed: int = 40) -> int:
        """Prune records for an assembly, keeping the newest ``keep_successful`` completed and
        ``keep_failed`` failed/cancelled runs. In-flight (pending/running) records are always
        kept. Returns count deleted."""

        def newest(predicate: Any, limit: int) -> list[SelectionRunRecord]:
            if limit <= 0:
                return []
            matching = sorted(
                [r for r in self._items if r.assembly_id == assembly_id and predicate(r)],
                key=lambda r: r.created_at or datetime.min,
                reverse=True,
            )
            return matching[:limit]

        keep_ids = {r.task_id for r in newest(lambda r: r.is_completed, keep_successful)}
        keep_ids.update(r.task_id for r in newest(lambda r: r.is_failed or r.is_cancelled, keep_failed))
        keep_ids.update(
            r.task_id for r in self._items if r.assembly_id == assembly_id and (r.is_pending or r.is_running)
        )

        before = len(self._items)
        self._items = [r for r in self._items if r.assembly_id != assembly_id or r.task_id in keep_ids]
        return before - len(self._items)

    def get_running_tasks(self) -> Iterable[SelectionRunRecord]:
        """Get all currently running selection tasks."""
        return [item for item in self._items if item.is_running]

    def get_all_unfinished(self) -> list[SelectionRunRecord]:
        """Get all SelectionRunRecords that are PENDING or RUNNING."""
        return [item for item in self._items if item.is_pending or item.is_running]

    def get_by_assembly_id_paginated(
        self, assembly_id: uuid.UUID, page: int = 1, per_page: int = 50
    ) -> tuple[list[tuple[SelectionRunRecord, None]], int]:
        """Get paginated SelectionRunRecords for an assembly with user information.

        Note: Fake implementation returns None for user in each tuple.
        """
        # Get all records for the assembly
        all_records = sorted(
            [item for item in self._items if item.assembly_id == assembly_id],
            key=lambda r: r.created_at or datetime.min,
            reverse=True,  # Newest first
        )

        total_count = len(all_records)

        # Apply pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_records = all_records[start_idx:end_idx]

        # Return tuples of (record, None) to match the real repository signature
        return [(record, None) for record in page_records], total_count


class FakeUserBackupCodeRepository(FakeRepository, UserBackupCodeRepository):
    """Fake implementation of UserBackupCodeRepository."""

    def get_codes_for_user(self, user_id: uuid.UUID) -> Iterable[UserBackupCode]:
        """Get all backup codes for a user."""
        return [code for code in self._items if code.user_id == user_id]

    def get_unused_codes_for_user(self, user_id: uuid.UUID) -> Iterable[UserBackupCode]:
        """Get all unused backup codes for a user."""
        return [code for code in self._items if code.user_id == user_id and not code.is_used()]

    def delete_codes_for_user(self, user_id: uuid.UUID) -> int:
        """Delete all backup codes for a user. Returns count deleted."""
        codes_to_delete = [code for code in self._items if code.user_id == user_id]
        count = len(codes_to_delete)
        self._items = [code for code in self._items if code.user_id != user_id]
        return count


class FakeTwoFactorAuditLogRepository(FakeRepository, TwoFactorAuditLogRepository):
    """Fake implementation of TwoFactorAuditLogRepository."""

    def get_logs_for_user(self, user_id: uuid.UUID, limit: int = 100) -> Iterable[TwoFactorAuditLog]:
        """Get audit logs for a user, most recent first."""
        user_logs = [log for log in self._items if log.user_id == user_id]
        # Sort by timestamp desc
        user_logs.sort(key=lambda log: log.timestamp, reverse=True)
        return user_logs[:limit]


class FakeTotpVerificationAttemptRepository(FakeRepository, TotpVerificationAttemptRepository):
    """Fake implementation of TotpVerificationAttemptRepository."""

    def get_attempts_since(self, user_id: uuid.UUID, since: datetime) -> Iterable[TotpVerificationAttempt]:
        """Get all verification attempts for a user since a given datetime."""
        user_attempts = [
            attempt for attempt in self._items if attempt.user_id == user_id and attempt.attempted_at >= since
        ]
        # Sort by attempted_at desc
        user_attempts.sort(key=lambda attempt: attempt.attempted_at, reverse=True)
        return user_attempts


class FakePasswordResetTokenRepository(FakeRepository, PasswordResetTokenRepository):
    """Fake implementation of PasswordResetTokenRepository."""

    def get_by_token(self, token: str) -> PasswordResetToken | None:
        """Get a password reset token by its token string."""
        for item in self._items:
            if item.token == token:
                return item
        return None

    def get_active_tokens_for_user(self, user_id: uuid.UUID) -> Iterable[PasswordResetToken]:
        """Get all active (not expired and not used) tokens for a user."""
        return [item for item in self._items if item.user_id == user_id and item.is_valid()]

    def count_recent_requests(self, user_id: uuid.UUID, since: datetime) -> int:
        """Count password reset requests for a user since a given datetime."""
        return sum(1 for item in self._items if item.user_id == user_id and item.created_at >= since)

    def delete_old_tokens(self, before: datetime) -> int:
        """Delete tokens created before a given datetime. Returns count deleted."""
        to_delete = [item for item in self._items if item.created_at < before]
        for item in to_delete:
            self._items.remove(item)
        return len(to_delete)

    def invalidate_user_tokens(self, user_id: uuid.UUID) -> int:
        """Mark all active tokens for a user as used. Returns count invalidated."""
        count = 0
        for item in self._items:
            if item.user_id == user_id and item.is_valid():
                item.use()
                count += 1
        return count

    def delete(self, item: PasswordResetToken) -> None:
        """Delete a token from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeEmailConfirmationTokenRepository(FakeRepository, EmailConfirmationTokenRepository):
    """Fake implementation of EmailConfirmationTokenRepository."""

    def get_by_token(self, token: str) -> EmailConfirmationToken | None:
        """Get an email confirmation token by its token string."""
        for item in self._items:
            if item.token == token:
                return item
        return None

    def count_recent_requests(self, user_id: uuid.UUID, since: datetime) -> int:
        """Count email confirmation requests for a user since a given datetime."""
        return sum(1 for item in self._items if item.user_id == user_id and item.created_at >= since)

    def delete_old_tokens(self, before: datetime) -> int:
        """Delete tokens created before a given datetime. Returns count deleted."""
        to_delete = [item for item in self._items if item.created_at < before]
        for item in to_delete:
            self._items.remove(item)
        return len(to_delete)

    def invalidate_user_tokens(self, user_id: uuid.UUID) -> int:
        """Mark all active tokens for a user as used. Returns count invalidated."""
        count = 0
        for item in self._items:
            if item.user_id == user_id and item.is_valid():
                item.use()
                count += 1
        return count


class FakeTargetCategoryRepository(FakeRepository, TargetCategoryRepository):
    """Fake in-memory TargetCategoryRepository."""

    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> list[TargetCategory]:
        return sorted(
            [c for c in self._items if c.assembly_id == assembly_id],
            key=lambda c: c.sort_order,
        )

    def count_by_assembly_id(self, assembly_id: uuid.UUID) -> int:
        return sum(1 for c in self._items if c.assembly_id == assembly_id)

    def delete(self, item: TargetCategory) -> None:
        self._items = [c for c in self._items if c.id != item.id]

    def delete_all_for_assembly(self, assembly_id: uuid.UUID) -> int:
        before = len(self._items)
        self._items = [c for c in self._items if c.assembly_id != assembly_id]
        return before - len(self._items)


class FakeRespondentRepository(FakeRepository, RespondentRepository):
    """Fake in-memory RespondentRepository."""

    def get_by_assembly_id(
        self,
        assembly_id: uuid.UUID,
        status: RespondentStatus | None = None,
        eligible_only: bool = False,
        include_deleted: bool = False,
    ) -> list[Respondent]:
        results = [r for r in self._items if r.assembly_id == assembly_id]
        if status:
            results = [r for r in results if r.selection_status == status]
        elif not include_deleted:
            results = [r for r in results if r.selection_status != RespondentStatus.DELETED]
        if eligible_only:
            results = [r for r in results if r.eligible is not False and r.can_attend is not False]
        return results

    def get_by_assembly_id_statuses(
        self,
        assembly_id: uuid.UUID,
        statuses: list[RespondentStatus] | None = None,
    ) -> list[Respondent]:
        results = [r for r in self._items if r.assembly_id == assembly_id]
        if statuses is None:
            results = [r for r in results if r.selection_status != RespondentStatus.DELETED]
        else:
            results = [r for r in results if r.selection_status in statuses]
        return sorted(results, key=lambda r: r.created_at)

    def get_by_assembly_id_paginated(
        self,
        assembly_id: uuid.UUID,
        page: int = 1,
        per_page: int = 50,
        status: RespondentStatus | None = None,
        eligible_only: bool = False,
        include_deleted: bool = False,
    ) -> tuple[list[Respondent], int]:
        results = [r for r in self._items if r.assembly_id == assembly_id]
        if status:
            results = [r for r in results if r.selection_status == status]
        elif not include_deleted:
            results = [r for r in results if r.selection_status != RespondentStatus.DELETED]
        if eligible_only:
            results = [r for r in results if r.eligible is not False and r.can_attend is not False]
        total_count = len(results)
        offset = (page - 1) * per_page
        paginated = results[offset : offset + per_page]
        return paginated, total_count

    def get_by_external_id(self, assembly_id: uuid.UUID, external_id: str) -> Respondent | None:
        for r in self._items:
            if r.assembly_id == assembly_id and r.external_id == external_id:
                return r
        return None

    def count_by_assembly_id(self, assembly_id: uuid.UUID, include_deleted: bool = False) -> int:
        return sum(
            1
            for r in self._items
            if r.assembly_id == assembly_id and (include_deleted or r.selection_status != RespondentStatus.DELETED)
        )

    def count_available_for_selection(self, assembly_id: uuid.UUID) -> int:
        return sum(
            1
            for r in self._items
            if r.assembly_id == assembly_id
            and r.selection_status == RespondentStatus.POOL
            and r.eligible is not False
            and r.can_attend is not False
        )

    def delete(self, item: Respondent) -> None:
        self._items = [r for r in self._items if r.id != item.id]

    def bulk_add(self, items: list[Respondent]) -> None:
        self._items.extend(items)

    def delete_all_for_assembly(self, assembly_id: uuid.UUID) -> int:
        before = len(self._items)
        self._items = [r for r in self._items if r.assembly_id != assembly_id]
        return before - len(self._items)

    def bulk_mark_as_selected(
        self,
        assembly_id: uuid.UUID,
        external_ids: list[str],
        selection_run_id: uuid.UUID,
        author_id: uuid.UUID,
    ) -> None:
        for r in self._items:
            if r.assembly_id == assembly_id and r.external_id in external_ids:
                r.mark_as_selected(selection_run_id)
                r.add_comment(
                    text="Selected in run",
                    author_id=author_id,
                    action=RespondentAction.SELECT,
                    selection_run_id=selection_run_id,
                )

    def reset_all_to_pool(self, assembly_id: uuid.UUID) -> int:
        count = 0
        for r in self._items:
            if r.assembly_id == assembly_id and r.selection_status != RespondentStatus.DELETED:
                r.reset_to_pool()
                count += 1
        return count

    def count_non_pool(self, assembly_id: uuid.UUID) -> int:
        return sum(
            1
            for r in self._items
            if r.assembly_id == assembly_id
            and r.selection_status != RespondentStatus.POOL
            and r.selection_status != RespondentStatus.DELETED
        )

    def get_attribute_columns(self, assembly_id: uuid.UUID) -> list[str]:
        for r in self._items:
            if r.assembly_id == assembly_id and r.selection_status != RespondentStatus.DELETED and r.attributes:
                return sorted(r.attributes.keys())
        return []

    def get_attribute_value_counts(self, assembly_id: uuid.UUID, attribute_name: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._items:
            if r.assembly_id == assembly_id and r.selection_status != RespondentStatus.DELETED and r.attributes:
                val = r.attributes.get(attribute_name)
                if val is not None:
                    counts[val] = counts.get(val, 0) + 1
        return counts

    def get_selected_attribute_value_counts(self, assembly_id: uuid.UUID, attribute_name: str) -> dict[str, int]:
        selected_statuses = {RespondentStatus.SELECTED, RespondentStatus.CONFIRMED}
        counts: dict[str, int] = {}
        for r in self._items:
            if r.assembly_id == assembly_id and r.selection_status in selected_statuses and r.attributes:
                val = r.attributes.get(attribute_name)
                if val is not None:
                    counts[val] = counts.get(val, 0) + 1
        return counts


class FakeRespondentFieldDefinitionRepository(FakeRepository, RespondentFieldDefinitionRepository):
    """Fake in-memory RespondentFieldDefinitionRepository."""

    def bulk_add(self, items: list[RespondentFieldDefinition]) -> None:
        self._items.extend(items)

    def get_by_assembly_and_key(self, assembly_id: uuid.UUID, field_key: str) -> RespondentFieldDefinition | None:
        for f in self._items:
            if f.assembly_id == assembly_id and f.field_key == field_key:
                return f
        return None

    def list_by_assembly(self, assembly_id: uuid.UUID) -> list[RespondentFieldDefinition]:
        group_index = {group: i for i, group in enumerate(GROUP_DISPLAY_ORDER)}
        fields = [f for f in self._items if f.assembly_id == assembly_id]
        return sorted(
            fields,
            key=lambda f: (group_index.get(f.group, len(GROUP_DISPLAY_ORDER)), f.sort_order, f.field_key),
        )

    def count_by_assembly_id(self, assembly_id: uuid.UUID) -> int:
        return sum(1 for f in self._items if f.assembly_id == assembly_id)

    def delete(self, item: RespondentFieldDefinition) -> None:
        self._items = [f for f in self._items if f.id != item.id]

    def delete_all_for_assembly(self, assembly_id: uuid.UUID) -> int:
        before = len(self._items)
        self._items = [f for f in self._items if f.assembly_id != assembly_id]
        return before - len(self._items)


class FakeEmailTemplateRepository(FakeRepository, EmailTemplateRepository):
    """Fake implementation of EmailTemplateRepository."""

    def list_by_assembly(self, assembly_id: uuid.UUID) -> list[EmailTemplate]:
        templates = [t for t in self._items if t.assembly_id == assembly_id]
        return sorted(templates, key=lambda t: t.created_at)

    def delete(self, item: EmailTemplate) -> None:
        self._items = [t for t in self._items if t.id != item.id]


class FakeRespondentEmailSendRecordRepository(FakeRepository, RespondentEmailSendRecordRepository):
    """Fake implementation of RespondentEmailSendRecordRepository."""

    def list_by_respondent(self, respondent_id: uuid.UUID) -> list[RespondentEmailSendRecord]:
        records = [r for r in self._items if r.respondent_id == respondent_id]
        return sorted(records, key=lambda r: r.created_at)


# The repository attribute names a FakeUnitOfWork exposes, in one place so the
# store, the aliases and the snapshot/rollback logic stay in sync.
_REPO_NAMES = (
    "users",
    "assemblies",
    "assembly_gsheets",
    "assembly_respondent_gsheets",
    "user_invites",
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
    "registration_pages",
    "registration_page_html_sources",
    "registration_images",
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
        self.assemblies = FakeAssemblyRepository()
        self.assembly_gsheets = FakeAssemblyGSheetRepository()
        self.assembly_respondent_gsheets = FakeAssemblyRespondentGSheetRepository()
        self.user_invites = FakeUserInviteRepository()
        self.user_assembly_roles = FakeUserAssemblyRoleRepository()
        self.selection_run_records = FakeSelectionRunRecordRepository()
        self.user_backup_codes = FakeUserBackupCodeRepository()
        self.two_factor_audit_logs = FakeTwoFactorAuditLogRepository()
        self.totp_attempts = FakeTotpVerificationAttemptRepository()
        self.password_reset_tokens = FakePasswordResetTokenRepository()
        self.email_confirmation_tokens = FakeEmailConfirmationTokenRepository()
        self.target_categories = FakeTargetCategoryRepository()
        self.respondents = FakeRespondentRepository()
        self.respondent_field_definitions = FakeRespondentFieldDefinitionRepository()
        self.registration_pages = FakeRegistrationPageRepository()
        self.registration_page_html_sources = FakeRegistrationPageHtmlRepository()
        self.registration_images = FakeRegistrationImageRepository()
        self.email_templates = FakeEmailTemplateRepository()
        self.respondent_email_send_records = FakeRespondentEmailSendRecordRepository()


class FakeUnitOfWork(AbstractUnitOfWork):
    """Fake Unit of Work implementation for testing.

    With no ``store`` it owns a private FakeStore (the long-standing behaviour
    used by unit tests). With a shared ``store`` it behaves like a real UoW over
    a shared database: every instance sees the same data, and the ``with`` block
    rolls back on exception via a snapshot of each repository.
    """

    def __init__(self, store: FakeStore | None = None) -> None:
        self._shared = store is not None
        self._store = store if store is not None else FakeStore()
        # Expose each repository both as ``uow.users`` and the legacy ``uow.fake_users``.
        for name in _REPO_NAMES:
            repo = getattr(self._store, name)
            setattr(self, name, repo)
            setattr(self, f"fake_{name}", repo)
        # Store reference to UoW in user_assembly_roles for get_users_with_roles_for_assembly.
        # All instances sharing a store share repositories, so pointing at the latest is fine.
        self.user_assembly_roles._uow = self
        self.committed = False
        self.expire_all_calls = 0
        self._snapshot: dict[str, list[Any]] | None = None

    def __enter__(self) -> AbstractUnitOfWork:
        if self._shared:
            self._take_snapshot()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        # Match SqlAlchemyUnitOfWork: roll back the shared store on exception.
        if self._shared and exc_type is not None:
            self.rollback()

    def _take_snapshot(self) -> None:
        self._snapshot = {name: list(getattr(self._store, name)._items) for name in _REPO_NAMES}

    def commit(self) -> None:
        """Mark as committed; for a shared store the committed state is the new baseline."""
        self.committed = True
        if self._shared and self._snapshot is not None:
            self._take_snapshot()

    def commit_and_reset(self) -> None:
        """Commit the work so far, then carry on against the same in-memory store.

        Nothing needs flushing for the fake; the repositories already hold the
        data, so this just records the commit and continues.
        """
        self.commit()

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

    def expire_all(self) -> None:
        """No-op for in-memory repositories — record the call for assertions."""
        self.expire_all_calls += 1


class FakeTemplateRenderer:
    """Fake template renderer for testing without Flask."""

    def __init__(self, templates: dict[str, str] | None = None):
        """
        Initialize with optional template strings.

        Args:
            templates: Dict mapping template names to template strings
        """
        self.templates = templates or {}
        self.rendered_templates: list[tuple[str, dict[str, Any]]] = []

    def render_template(self, template_name: str, **context: Any) -> str:
        """
        Render a template by simple string formatting.

        Args:
            template_name: Name of template to render
            **context: Template context variables

        Returns:
            Rendered template string
        """
        # Track what was rendered for test assertions
        self.rendered_templates.append((template_name, context))

        # If we have a template string, use it; otherwise return a simple format
        if template_name in self.templates:
            return self.templates[template_name].format(**context)

        # Default: return a simple formatted string for testing
        return f"Rendered {template_name} with context: {context}"


class FakeURLGenerator:
    """Fake URL generator for testing without Flask."""

    def __init__(self, url_map: dict[str, str] | None = None):
        """
        Initialize with optional URL mappings.

        Args:
            url_map: Dict mapping endpoint names to URL patterns
        """
        self.url_map = url_map or {
            "auth.confirm_email": "http://localhost/auth/confirm-email/{token}",
            "auth.reset_password": "http://localhost/auth/reset-password/{token}",  # pragma: allowlist secret
        }
        self.generated_urls: list[tuple[str, dict[str, Any]]] = []

    def generate_url(self, endpoint: str, _external: bool = False, **values: Any) -> str:
        """
        Generate a URL by looking up endpoint and formatting with values.

        Args:
            endpoint: Endpoint name (e.g., "auth.confirm_email")
            _external: Whether to generate absolute URL (always absolute in fake)
            **values: URL parameters

        Returns:
            Generated URL string
        """
        # Track what was generated for test assertions
        self.generated_urls.append((endpoint, {"_external": _external, **values}))

        # Look up URL pattern and format with values
        if endpoint in self.url_map:
            url_pattern = self.url_map[endpoint]
            return url_pattern.format(**values)

        # Default: return a simple URL for testing
        return f"http://localhost/{endpoint.replace('.', '/')}"


class FakeGSheetExportTarget(AbstractTabularExportTarget):
    """In-memory fake Google Sheets export target for tests.

    Records each ``write_sheet`` call and exposes a fixed result URL, so
    component and unit tests can drive the export flow without gspread.
    """

    def __init__(
        self,
        result_url: str = "https://docs.google.com/spreadsheets/d/fake",
        error: Exception | None = None,
    ) -> None:
        self.writes: list[tuple[str, TabularData]] = []
        self.result_url = result_url
        # When set, write_sheet raises this instead of recording the write, so
        # tests can drive the "sheet could not be written" failure path.
        self._error = error

    def write_sheet(self, title: str, table: TabularData) -> None:
        if self._error is not None:
            raise self._error
        self.writes.append((title, table))
