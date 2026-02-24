"""ABOUTME: Abstract repository interfaces for domain objects
ABOUTME: Defines repository contracts to abstract database operations from business logic"""

from __future__ import annotations

import abc
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from opendlp.domain.assembly import Assembly, AssemblyGSheet, SelectionRunRecord
from opendlp.domain.email_confirmation import EmailConfirmationToken
from opendlp.domain.password_reset import PasswordResetToken
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory
from opendlp.domain.totp_attempts import TotpVerificationAttempt
from opendlp.domain.two_factor_audit import TwoFactorAuditLog
from opendlp.domain.user_backup_codes import UserBackupCode
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import RespondentStatus


class AbstractRepository(abc.ABC):
    """Base repository interface providing common operations."""

    @abc.abstractmethod
    def add(self, item: Any) -> None:
        """Add an item to the repository."""
        raise NotImplementedError

    @abc.abstractmethod
    def get(self, item_id: uuid.UUID) -> Any | None:
        """Get an item by its ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def all(self) -> Iterable[Any]:
        """Get all items in the repository."""
        raise NotImplementedError


class UserRepository(AbstractRepository):
    """Repository interface for User domain objects."""

    @abc.abstractmethod
    def filter(self, role: str | None = None, active: bool | None = None) -> Iterable[User]:
        """List users filtered by criteria."""
        raise NotImplementedError

    @abc.abstractmethod
    def filter_paginated(
        self,
        role: str | None = None,
        active: bool | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """List users filtered by criteria with pagination.

        Args:
            role: Filter by global role
            active: Filter by active status
            search: Search term for email, first_name, last_name (case-insensitive)
            limit: Maximum number of results to return
            offset: Number of results to skip

        Returns:
            Tuple of (users list, total count)
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_by_email(self, email: str) -> User | None:
        """Get a user by their email address."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_users_for_assembly(self, assembly_id: uuid.UUID) -> Iterable[User]:
        """Get all users who have roles in the given assembly."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_users_not_in_assembly(self, assembly_id: uuid.UUID) -> Iterable[User]:
        """Get all users who do NOT have any role in the given assembly."""
        raise NotImplementedError

    @abc.abstractmethod
    def search_users_not_in_assembly(self, assembly_id: uuid.UUID, search_term: str) -> Iterable[User]:
        """Search users not in assembly by email (prioritized) and display_name.

        Args:
            assembly_id: The assembly to exclude users from
            search_term: The search term to match against email and display_name (case-insensitive)

        Returns:
            List of matching users who do NOT have any role in the assembly, ordered by relevance
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_by_oauth_credentials(self, provider: str, oauth_id: str) -> User | None:
        """Get a user by their OAuth provider and ID."""
        raise NotImplementedError


class AssemblyRepository(AbstractRepository):
    """Repository interface for Assembly domain objects."""

    @abc.abstractmethod
    def get_active_assemblies(self) -> Iterable[Assembly]:
        """Get all assemblies that are currently active."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_assemblies_for_user(self, user_id: uuid.UUID) -> Iterable[Assembly]:
        """Get all assemblies that a user has access to."""
        raise NotImplementedError

    @abc.abstractmethod
    def search_by_title(self, search_term: str) -> Iterable[Assembly]:
        """Search assemblies by title (case-insensitive partial match)."""
        raise NotImplementedError


class UserInviteRepository(AbstractRepository):
    """Repository interface for UserInvite domain objects."""

    @abc.abstractmethod
    def get_by_code(self, code: str) -> UserInvite | None:
        """Get an invite by its code."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_valid_invites(self) -> Iterable[UserInvite]:
        """Get all invites that are valid (not expired and not used)."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_invites_created_by(self, user_id: uuid.UUID) -> Iterable[UserInvite]:
        """Get all invites created by a specific user."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_expired_invites(self) -> Iterable[UserInvite]:
        """Get all invites that have expired."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, item: UserInvite) -> None:
        """Delete an invite from the repository."""
        raise NotImplementedError


class UserAssemblyRoleRepository(AbstractRepository):
    """Repository interface for UserAssemblyRole domain objects."""

    @abc.abstractmethod
    def get_by_user_and_assembly(self, user_id: uuid.UUID, assembly_id: uuid.UUID) -> UserAssemblyRole | None:
        """Get a user's role for a specific assembly."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_roles_for_user(self, user_id: uuid.UUID) -> Iterable[UserAssemblyRole]:
        """Get all assembly roles for a user."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_roles_for_assembly(self, assembly_id: uuid.UUID) -> Iterable[UserAssemblyRole]:
        """Get all user roles for an assembly."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_users_with_roles_for_assembly(self, assembly_id: uuid.UUID) -> list[tuple[User, UserAssemblyRole]]:
        """Get all users with their roles for a specific assembly.

        Returns a list of tuples containing (User, UserAssemblyRole) for all users with roles in the assembly.
        This should be implemented with a single SQL join query for efficiency.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def remove_role(self, user_id: uuid.UUID, assembly_id: uuid.UUID) -> bool:
        """Remove a user's role from an assembly. Returns True if role was found and removed."""
        raise NotImplementedError


class AssemblyGSheetRepository(AbstractRepository):
    """Repository interface for AssemblyGSheet domain objects."""

    @abc.abstractmethod
    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> AssemblyGSheet | None:
        """Get an AssemblyGSheet by its assembly ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, item: AssemblyGSheet) -> None:
        """Delete an AssemblyGSheet from the repository."""
        raise NotImplementedError


class SelectionRunRecordRepository(AbstractRepository):
    """Repository interface for SelectionRunRecord domain objects."""

    @abc.abstractmethod
    def get_by_task_id(self, task_id: uuid.UUID) -> SelectionRunRecord | None:
        """Get a SelectionRunRecord by its task ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> Iterable[SelectionRunRecord]:
        """Get all SelectionRunRecords for a specific assembly."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_latest_for_assembly(self, assembly_id: uuid.UUID) -> SelectionRunRecord | None:
        """Get the most recent SelectionRunRecord for an assembly."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_running_tasks(self) -> Iterable[SelectionRunRecord]:
        """Get all currently running selection tasks."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_all_unfinished(self) -> list[SelectionRunRecord]:
        """Get all SelectionRunRecords that are PENDING or RUNNING."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_by_assembly_id_paginated(
        self, assembly_id: uuid.UUID, page: int = 1, per_page: int = 50
    ) -> tuple[list[tuple[SelectionRunRecord, User | None]], int]:
        """Get paginated SelectionRunRecords for an assembly with user information.

        Returns: (list of (SelectionRunRecord, User or None), total_count)
        """
        raise NotImplementedError


class PasswordResetTokenRepository(AbstractRepository):
    """Repository interface for PasswordResetToken domain objects."""

    @abc.abstractmethod
    def get_by_token(self, token: str) -> PasswordResetToken | None:
        """Get a password reset token by its token string."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_active_tokens_for_user(self, user_id: uuid.UUID) -> Iterable[PasswordResetToken]:
        """Get all active (not expired and not used) tokens for a user."""
        raise NotImplementedError

    @abc.abstractmethod
    def count_recent_requests(self, user_id: uuid.UUID, since: datetime) -> int:
        """Count password reset requests for a user since a given datetime."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete_old_tokens(self, before: datetime) -> int:
        """Delete tokens created before a given datetime. Returns count deleted."""
        raise NotImplementedError

    @abc.abstractmethod
    def invalidate_user_tokens(self, user_id: uuid.UUID) -> int:
        """Mark all active tokens for a user as used. Returns count invalidated."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, item: PasswordResetToken) -> None:
        """Delete a token from the repository."""
        raise NotImplementedError


class EmailConfirmationTokenRepository(AbstractRepository):
    """Repository interface for EmailConfirmationToken domain objects."""

    @abc.abstractmethod
    def get_by_token(self, token: str) -> EmailConfirmationToken | None:
        """Get an email confirmation token by its token string."""
        raise NotImplementedError

    @abc.abstractmethod
    def count_recent_requests(self, user_id: uuid.UUID, since: datetime) -> int:
        """Count email confirmation requests for a user since a given datetime."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete_old_tokens(self, before: datetime) -> int:
        """Delete tokens created before a given datetime. Returns count deleted."""
        raise NotImplementedError

    @abc.abstractmethod
    def invalidate_user_tokens(self, user_id: uuid.UUID) -> int:
        """Mark all active tokens for a user as used. Returns count invalidated."""
        raise NotImplementedError


class UserBackupCodeRepository(AbstractRepository):
    """Repository interface for UserBackupCode domain objects."""

    @abc.abstractmethod
    def get_codes_for_user(self, user_id: uuid.UUID) -> Iterable[UserBackupCode]:
        """Get all backup codes for a user."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_unused_codes_for_user(self, user_id: uuid.UUID) -> Iterable[UserBackupCode]:
        """Get all unused backup codes for a user."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete_codes_for_user(self, user_id: uuid.UUID) -> int:
        """Delete all backup codes for a user. Returns count deleted."""
        raise NotImplementedError


class TwoFactorAuditLogRepository(AbstractRepository):
    """Repository interface for TwoFactorAuditLog domain objects."""

    @abc.abstractmethod
    def get_logs_for_user(self, user_id: uuid.UUID, limit: int = 100) -> Iterable[TwoFactorAuditLog]:
        """Get audit logs for a user, most recent first."""
        raise NotImplementedError


class TotpVerificationAttemptRepository(AbstractRepository):
    """Repository interface for TotpVerificationAttempt domain objects."""

    @abc.abstractmethod
    def get_attempts_since(self, user_id: uuid.UUID, since: datetime) -> Iterable[TotpVerificationAttempt]:
        """Get all verification attempts for a user since a given datetime."""
        raise NotImplementedError


class TargetCategoryRepository(AbstractRepository):
    """Repository interface for TargetCategory domain objects."""

    @abc.abstractmethod
    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> list[TargetCategory]:
        """Get all target categories for an assembly, ordered by sort_order."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, item: TargetCategory) -> None:
        """Delete a target category from the repository."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete_all_for_assembly(self, assembly_id: uuid.UUID) -> int:
        """Delete all target categories for an assembly. Returns count deleted."""
        raise NotImplementedError


class RespondentRepository(AbstractRepository):
    """Repository interface for Respondent domain objects."""

    @abc.abstractmethod
    def get_by_assembly_id(
        self,
        assembly_id: uuid.UUID,
        status: RespondentStatus | None = None,
        eligible_only: bool = False,
    ) -> list[Respondent]:
        """Get respondents for an assembly, optionally filtered."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_by_external_id(self, assembly_id: uuid.UUID, external_id: str) -> Respondent | None:
        """Get a respondent by assembly and external ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def count_available_for_selection(self, assembly_id: uuid.UUID) -> int:
        """Count respondents available for selection."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, item: Respondent) -> None:
        """Delete a respondent."""
        raise NotImplementedError

    @abc.abstractmethod
    def bulk_add(self, items: list[Respondent]) -> None:
        """Add multiple respondents in bulk."""
        raise NotImplementedError
