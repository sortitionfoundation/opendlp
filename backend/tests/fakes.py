"""ABOUTME: Fake repository implementations for testing
ABOUTME: In-memory repositories that implement the same interfaces as real ones"""

import uuid
from collections.abc import Iterable
from typing import Any

from opendlp.domain.assembly import Assembly, AssemblyGSheet, SelectionRunRecord
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.service_layer.repositories import (
    AbstractRepository,
    AssemblyGSheetRepository,
    AssemblyRepository,
    SelectionRunRecordRepository,
    UserAssemblyRoleRepository,
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


class FakeUnitOfWork(AbstractUnitOfWork):
    """Fake Unit of Work implementation for testing."""

    def __init__(self) -> None:
        self.users = self.fake_users = FakeUserRepository()
        self.assemblies = self.fake_assemblies = FakeAssemblyRepository()
        self.assembly_gsheets = self.fake_assembly_gsheets = FakeAssemblyGSheetRepository()
        self.user_invites = self.fake_user_invites = FakeUserInviteRepository()
        self.user_assembly_roles = self.fake_user_assembly_roles = FakeUserAssemblyRoleRepository()
        self.selection_run_records = self.fake_selection_run_records = FakeSelectionRunRecordRepository()
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
        self.committed = False
