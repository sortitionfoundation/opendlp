"""ABOUTME: Fake repository implementations for testing
ABOUTME: In-memory repositories that implement the same interfaces as real ones"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from opendlp.domain.assembly import Assembly, AssemblyGSheet, SelectionRunRecord
from opendlp.domain.email_confirmation import EmailConfirmationToken
from opendlp.domain.totp_attempts import TotpVerificationAttempt
from opendlp.domain.two_factor_audit import TwoFactorAuditLog
from opendlp.domain.user_backup_codes import UserBackupCode
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.service_layer.repositories import (
    AbstractRepository,
    AssemblyGSheetRepository,
    AssemblyRepository,
    EmailConfirmationTokenRepository,
    SelectionRunRecordRepository,
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
            users = [user for user in users if user.role == role]
        if active is not None:
            users = [user for user in users if user.active == active]
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

    def get_latest_for_assembly(self, assembly_id: uuid.UUID) -> SelectionRunRecord | None:
        """Get the most recent SelectionRunRecord for an assembly."""
        assembly_records = list(self.get_by_assembly_id(assembly_id))
        if not assembly_records:
            return None
        # Sort by created_at, return the most recent
        return max(assembly_records, key=lambda r: r.created_at or "")

    def get_running_tasks(self) -> Iterable[SelectionRunRecord]:
        """Get all currently running selection tasks."""
        return [item for item in self._items if item.status in ["pending", "running"]]

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
            key=lambda r: r.created_at or "",
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
        count = 0
        for item in self._items:
            if item.user_id == user_id and item.created_at >= since:
                count += 1
        return count

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


class FakeUnitOfWork(AbstractUnitOfWork):
    """Fake Unit of Work implementation for testing."""

    def __init__(self) -> None:
        self.users = self.fake_users = FakeUserRepository()
        self.assemblies = self.fake_assemblies = FakeAssemblyRepository()
        self.assembly_gsheets = self.fake_assembly_gsheets = FakeAssemblyGSheetRepository()
        self.user_invites = self.fake_user_invites = FakeUserInviteRepository()
        self.user_assembly_roles = self.fake_user_assembly_roles = FakeUserAssemblyRoleRepository()
        self.selection_run_records = self.fake_selection_run_records = FakeSelectionRunRecordRepository()
        self.user_backup_codes = self.fake_user_backup_codes = FakeUserBackupCodeRepository()
        self.two_factor_audit_logs = self.fake_two_factor_audit_logs = FakeTwoFactorAuditLogRepository()
        self.totp_attempts = self.fake_totp_attempts = FakeTotpVerificationAttemptRepository()
        self.email_confirmation_tokens = self.fake_email_confirmation_tokens = FakeEmailConfirmationTokenRepository()
        # Store reference to UoW in user_assembly_roles for get_users_with_roles_for_assembly
        self.user_assembly_roles._uow = self
        self.committed = False

    def __enter__(self) -> AbstractUnitOfWork:
        return self

    def __exit__(self, *args) -> None:
        pass

    def commit(self) -> None:
        """Mark as committed."""
        self.committed = True

    def rollback(self) -> None:
        """Clear all repositories."""
        self.fake_users._items.clear()
        self.fake_assemblies._items.clear()
        self.fake_assembly_gsheets._items.clear()
        self.fake_user_invites._items.clear()
        self.fake_user_assembly_roles._items.clear()
        self.fake_selection_run_records._items.clear()
        self.fake_user_backup_codes._items.clear()
        self.fake_two_factor_audit_logs._items.clear()
        self.fake_totp_attempts._items.clear()
        self.fake_email_confirmation_tokens._items.clear()
        self.committed = False


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
