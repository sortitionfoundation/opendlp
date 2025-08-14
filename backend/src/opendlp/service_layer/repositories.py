"""ABOUTME: Abstract repository interfaces for domain objects
ABOUTME: Defines repository contracts to abstract database operations from business logic"""

from __future__ import annotations

import abc
import uuid
from collections.abc import Iterable
from typing import Any

from opendlp.domain.assembly import Assembly
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole


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
    def list(self) -> Iterable[Any]:
        """List all items in the repository."""
        raise NotImplementedError


class UserRepository(AbstractRepository):
    """Repository interface for User domain objects."""

    @abc.abstractmethod
    def get_by_email(self, email: str) -> User | None:
        """Get a user by their email address."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_users_for_assembly(self, assembly_id: uuid.UUID) -> Iterable[User]:
        """Get all users who have roles in the given assembly."""
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
    def remove_role(self, user_id: uuid.UUID, assembly_id: uuid.UUID) -> bool:
        """Remove a user's role from an assembly. Returns True if role was found and removed."""
        raise NotImplementedError
