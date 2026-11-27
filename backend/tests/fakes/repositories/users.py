"""ABOUTME: In-memory repositories for users, invites, roles and account security records
ABOUTME: Part of the tests.fakes package of in-memory test doubles"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from opendlp.domain.email_confirmation import EmailConfirmationToken
from opendlp.domain.password_reset import PasswordResetToken
from opendlp.domain.totp_attempts import TotpVerificationAttempt
from opendlp.domain.two_factor_audit import TwoFactorAuditLog
from opendlp.domain.user_backup_codes import UserBackupCode
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.user_signup_surveys import UserSignupSurvey
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import (
    GlobalRole,
)
from opendlp.service_layer.repositories import (
    EmailConfirmationTokenRepository,
    PasswordResetTokenRepository,
    TotpVerificationAttemptRepository,
    TwoFactorAuditLogRepository,
    UserAssemblyRoleRepository,
    UserBackupCodeRepository,
    UserInviteRepository,
    UserRepository,
    UserSignupSurveyRepository,
)
from tests.fakes.repositories.base import FakeRepository


def _parse_role_filter(role: str | None) -> GlobalRole | None:
    """Mirror the SQL repository: an unknown role filter means no filter, not an error."""
    if not role:
        return None
    try:
        return GlobalRole(role.lower())
    except ValueError:
        return None


class FakeUserRepository(FakeRepository, UserRepository):
    """Fake implementation of UserRepository."""

    def filter(self, role: str | None = None, active: bool | None = None) -> Iterable[User]:
        """List users filtered by criteria."""
        users = list(self._items)
        role_enum = _parse_role_filter(role)
        if role_enum:
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
        return [user for user in self._items if any(role.assembly_id == assembly_id for role in user.assembly_roles)]

    def get_users_not_in_assembly(self, assembly_id: uuid.UUID) -> Iterable[User]:
        """Get all users who do NOT have any role in the given assembly."""
        users_with_roles = {user.id for user in self.get_users_for_assembly(assembly_id)}
        return [user for user in self._items if user.id not in users_with_roles]

    def get_by_email_not_in_assembly(self, assembly_id: uuid.UUID, email: str) -> User | None:
        """Find the user with exactly this email, if they have no role in the assembly."""
        if not email:
            return None
        wanted = email.strip().lower()
        for user in self.get_users_not_in_assembly(assembly_id):
            if user.email.lower() == wanted:
                return user
        return None

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


class FakeUserSignupSurveyRepository(FakeRepository, UserSignupSurveyRepository):
    """Fake implementation of UserSignupSurveyRepository."""

    def get_by_user_id(self, user_id: uuid.UUID) -> UserSignupSurvey | None:
        """Get the signup survey for a user, or None if they have none."""
        for survey in self._items:
            if survey.user_id == user_id:
                return survey
        return None


class FakeUserAssemblyRoleRepository(FakeRepository, UserAssemblyRoleRepository):
    """Fake implementation for UserAssemblyRole repository.

    A role can arrive two ways: added here, or appended to ``user.assembly_roles``
    (which is what ``assign_assembly_role`` does). In SQLAlchemy those are the
    same rows, so both are visible to both. Here they are separate lists, and a
    fake that only read its own would report no members for every assembly
    created through the service - so every query reads the union.
    """

    def __init__(self, users: FakeUserRepository, items: list[Any] | None = None) -> None:
        super().__init__(items)
        self._users = users

    def _all_roles(self) -> list[UserAssemblyRole]:
        """Every role, however it was recorded, one per (user, assembly)."""
        roles: dict[tuple[uuid.UUID, uuid.UUID], UserAssemblyRole] = {}
        for role in self._items:
            roles[(role.user_id, role.assembly_id)] = role
        for user in self._users.all():
            for role in user.assembly_roles:
                roles.setdefault((role.user_id, role.assembly_id), role)
        return list(roles.values())

    def get_by_user_and_assembly(self, user_id: uuid.UUID, assembly_id: uuid.UUID) -> UserAssemblyRole | None:
        """Get role for user in specific assembly."""
        for role in self._all_roles():
            if role.user_id == user_id and role.assembly_id == assembly_id:
                return role
        return None

    def get_roles_for_user(self, user_id: uuid.UUID) -> Iterable[UserAssemblyRole]:
        """Get all roles for a user."""
        return [role for role in self._all_roles() if role.user_id == user_id]

    def get_roles_for_assembly(self, assembly_id: uuid.UUID) -> Iterable[UserAssemblyRole]:
        """Get all roles for an assembly."""
        return [role for role in self._all_roles() if role.assembly_id == assembly_id]

    def get_users_with_roles_for_assembly(self, assembly_id: uuid.UUID) -> list[tuple[User, UserAssemblyRole]]:
        """Get all users with their roles for a specific assembly.

        In production this is a single SQL join; here it is a lookup per role.
        """
        results = []
        for role in self.get_roles_for_assembly(assembly_id):
            user = self._users.get(role.user_id)
            if user:
                results.append((user, role))
        return results

    def remove_role(self, user_id: uuid.UUID, assembly_id: uuid.UUID) -> bool:
        """Remove a user's role from an assembly. Returns True if role was found and removed."""
        role = self.get_by_user_and_assembly(user_id, assembly_id)
        if not role:
            return False
        self._items = [r for r in self._items if r != role]
        # Also detach it from the user, or the union above would hand it straight back.
        user = self._users.get(user_id)
        if user:
            user.assembly_roles = [r for r in user.assembly_roles if r.assembly_id != assembly_id]
        return True


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
