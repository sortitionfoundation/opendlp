"""ABOUTME: SQLAlchemy implementations of repository interfaces
ABOUTME: Provides concrete database operations using SQLAlchemy sessions"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from opendlp.adapters import orm
from opendlp.domain.assembly import Assembly, AssemblyGSheet, SelectionRunRecord
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyStatus, GlobalRole, SelectionRunStatus
from opendlp.service_layer.repositories import (
    AssemblyGSheetRepository,
    AssemblyRepository,
    SelectionRunRecordRepository,
    UserAssemblyRoleRepository,
    UserInviteRepository,
    UserRepository,
)


class SqlAlchemyRepository:
    """Base SQLAlchemy repository with common functionality."""

    def __init__(self, session: Session) -> None:
        self.session = session


class SqlAlchemyUserRepository(SqlAlchemyRepository, UserRepository):
    """SQLAlchemy implementation of UserRepository."""

    def add(self, item: User) -> None:
        """Add a user to the repository."""
        self.session.add(item)

    def get(self, item_id: uuid.UUID) -> User | None:
        """Get a user by their ID."""
        return self.session.query(User).filter_by(id=item_id).first()

    def all(self) -> Iterable[User]:
        """Get all users."""
        return self.session.query(User).all()

    def filter(self, role: str | None = None, active: bool | None = None) -> Iterable[User]:
        """List users filtered by criteria."""
        user_query = self.session.query(User)
        if role:
            role_enum = GlobalRole(role.lower())
            user_query = user_query.filter(orm.users.c.role == role_enum)
        if active is not None:
            user_query = user_query.filter(orm.users.c.active == active)
        return user_query.all()

    def filter_paginated(
        self,
        role: str | None = None,
        active: bool | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """List users filtered by criteria with pagination."""
        # Build base query
        user_query = self.session.query(User)

        # Apply role filter
        if role:
            role_enum = GlobalRole(role.lower())
            user_query = user_query.filter(orm.users.c.global_role == role_enum)

        # Apply active filter
        if active is not None:
            user_query = user_query.filter(orm.users.c.is_active == active)

        # Apply search filter (case-insensitive search across email, first_name, last_name)
        if search:
            search_term = f"%{search}%"
            user_query = user_query.filter(
                or_(
                    orm.users.c.email.ilike(search_term),
                    orm.users.c.first_name.ilike(search_term),
                    orm.users.c.last_name.ilike(search_term),
                )
            )

        # Get total count before pagination
        total_count = user_query.count()

        # Apply ordering and pagination
        users = user_query.order_by(orm.users.c.created_at.desc()).limit(limit).offset(offset).all()

        return list(users), total_count

    def get_by_email(self, email: str) -> User | None:
        """Get a user by their email address."""
        return self.session.query(User).filter_by(email=email).first()

    def get_by_oauth_credentials(self, provider: str, oauth_id: str) -> User | None:
        """Get a user by their OAuth provider and ID."""
        return self.session.query(User).filter_by(oauth_provider=provider, oauth_id=oauth_id).first()

    def get_users_for_assembly(self, assembly_id: uuid.UUID) -> Iterable[User]:
        """Get all users who have roles in the given assembly."""
        # Query for users who have roles in this assembly
        user_ids_subquery = select(orm.user_assembly_roles.c.user_id).where(
            orm.user_assembly_roles.c.assembly_id == assembly_id
        )

        return self.session.query(User).filter(orm.users.c.id.in_(user_ids_subquery)).all()

    def get_active_users(self) -> Iterable[User]:
        """Get all active users."""
        return self.session.query(User).filter_by(is_active=True).all()

    def get_admins(self) -> Iterable[User]:
        """Get all users with admin privileges."""
        return (
            self.session.query(User)
            .filter(
                or_(
                    orm.users.c.global_role == GlobalRole.ADMIN,
                    orm.users.c.global_role == GlobalRole.GLOBAL_ORGANISER,
                )
            )
            .all()
        )


class SqlAlchemyAssemblyRepository(SqlAlchemyRepository, AssemblyRepository):
    """SQLAlchemy implementation of AssemblyRepository."""

    def add(self, item: Assembly) -> None:
        """Add an assembly to the repository."""
        self.session.add(item)

    def get(self, item_id: uuid.UUID) -> Assembly | None:
        """Get an assembly by its ID."""
        return self.session.query(Assembly).filter_by(id=item_id).first()

    def all(self) -> Iterable[Assembly]:
        """Get all assemblies."""
        return self.session.query(Assembly).all()

    def get_active_assemblies(self) -> Iterable[Assembly]:
        """Get all assemblies that are currently active."""
        return (
            self.session.query(Assembly)
            .filter_by(status=AssemblyStatus.ACTIVE)
            .order_by(orm.assemblies.c.created_at.desc())
            .all()
        )

    def get_assemblies_for_user(self, user_id: uuid.UUID) -> Iterable[Assembly]:
        """Get all assemblies that a user has access to."""
        # First check if user has global permissions
        user = self.session.query(User).filter_by(id=user_id).first()
        if not user:
            return []

        if user.global_role in (GlobalRole.ADMIN, GlobalRole.GLOBAL_ORGANISER):
            # Global users can access all active assemblies
            return self.get_active_assemblies()

        # Regular users can only access assemblies where they have specific roles
        assembly_ids_subquery = select(orm.user_assembly_roles.c.assembly_id).where(
            orm.user_assembly_roles.c.user_id == user_id
        )

        return (
            self.session.query(Assembly)
            .filter(
                and_(
                    orm.assemblies.c.id.in_(assembly_ids_subquery),
                    orm.assemblies.c.status == AssemblyStatus.ACTIVE,
                )
            )
            .order_by(orm.assemblies.c.created_at.desc())
            .all()
        )

    def search_by_title(self, search_term: str) -> Iterable[Assembly]:
        """Search assemblies by title (case-insensitive partial match)."""
        return (
            self.session.query(Assembly)
            .filter(orm.assemblies.c.title.ilike(f"%{search_term}%"))
            .filter_by(status=AssemblyStatus.ACTIVE)
            .order_by(orm.assemblies.c.created_at.desc())
            .all()
        )

    def get_assemblies_by_status(self, status: AssemblyStatus) -> Iterable[Assembly]:
        """Get assemblies by their status."""
        return self.session.query(Assembly).filter_by(status=status).order_by(orm.assemblies.c.created_at.desc()).all()


class SqlAlchemyUserInviteRepository(SqlAlchemyRepository, UserInviteRepository):
    """SQLAlchemy implementation of UserInviteRepository."""

    def add(self, item: UserInvite) -> None:
        """Add an invite to the repository."""
        self.session.add(item)

    def get(self, item_id: uuid.UUID) -> UserInvite | None:
        """Get an invite by its ID."""
        return self.session.query(UserInvite).filter_by(id=item_id).first()

    def all(self) -> Iterable[UserInvite]:
        """Get all invites."""
        return self.session.query(UserInvite).order_by(orm.user_invites.c.created_at.desc()).all()

    def get_by_code(self, code: str) -> UserInvite | None:
        """Get an invite by its code."""
        return self.session.query(UserInvite).filter_by(code=code).first()

    def get_valid_invites(self) -> Iterable[UserInvite]:
        """Get all invites that are valid (not expired and not used)."""
        now = datetime.now(UTC)
        return (
            self.session.query(UserInvite)
            .filter(
                and_(
                    orm.user_invites.c.used_by.is_(None),
                    orm.user_invites.c.expires_at > now,
                )
            )
            .order_by(orm.user_invites.c.created_at.desc())
            .all()
        )

    def get_invites_created_by(self, user_id: uuid.UUID) -> Iterable[UserInvite]:
        """Get all invites created by a specific user."""
        return (
            self.session.query(UserInvite)
            .filter_by(created_by=user_id)
            .order_by(orm.user_invites.c.created_at.desc())
            .all()
        )

    def get_expired_invites(self) -> Iterable[UserInvite]:
        """Get all invites that have expired."""
        now = datetime.now(UTC)
        return (
            self.session.query(UserInvite)
            .filter(orm.user_invites.c.expires_at <= now)
            .order_by(orm.user_invites.c.expires_at.desc())
            .all()
        )

    def get_used_invites(self) -> Iterable[UserInvite]:
        """Get all invites that have been used."""
        return (
            self.session.query(UserInvite)
            .filter(orm.user_invites.c.used_by.isnot(None))
            .order_by(orm.user_invites.c.used_at.desc())
            .all()
        )

    def delete(self, item: UserInvite) -> None:
        """Delete an invite from the repository."""
        self.session.delete(item)

    def cleanup_expired_invites(self) -> int:
        """Remove expired invites and return count of deleted items."""
        now = datetime.now(UTC)
        expired_invites = self.session.query(UserInvite).filter(orm.user_invites.c.expires_at <= now).all()

        count = len(expired_invites)
        for invite in expired_invites:
            self.session.delete(invite)

        return count


class SqlAlchemyUserAssemblyRoleRepository(SqlAlchemyRepository, UserAssemblyRoleRepository):
    """SQLAlchemy implementation for UserAssemblyRole operations."""

    def add(self, role: UserAssemblyRole) -> None:
        """Add a user assembly role."""
        self.session.add(role)

    def get(self, role_id: uuid.UUID) -> UserAssemblyRole | None:
        """Get a role by its ID."""
        return self.session.query(UserAssemblyRole).filter_by(id=role_id).first()

    def all(self) -> Iterable[UserAssemblyRole]:
        """Get all user assembly roles."""
        return self.session.query(UserAssemblyRole).order_by(orm.user_assembly_roles.c.created_at.desc()).all()

    def get_by_user_and_assembly(self, user_id: uuid.UUID, assembly_id: uuid.UUID) -> UserAssemblyRole | None:
        """Get a user's role for a specific assembly."""
        return self.session.query(UserAssemblyRole).filter_by(user_id=user_id, assembly_id=assembly_id).first()

    def get_roles_for_user(self, user_id: uuid.UUID) -> Iterable[UserAssemblyRole]:
        """Get all assembly roles for a user."""
        return (
            self.session.query(UserAssemblyRole)
            .filter_by(user_id=user_id)
            .order_by(orm.user_assembly_roles.c.created_at.desc())
            .all()
        )

    def get_roles_for_assembly(self, assembly_id: uuid.UUID) -> Iterable[UserAssemblyRole]:
        """Get all user roles for an assembly."""
        return (
            self.session.query(UserAssemblyRole)
            .filter_by(assembly_id=assembly_id)
            .order_by(orm.user_assembly_roles.c.created_at.desc())
            .all()
        )

    def remove_role(self, user_id: uuid.UUID, assembly_id: uuid.UUID) -> bool:
        """Remove a user's role from an assembly. Returns True if role was found and removed."""
        role = self.get_by_user_and_assembly(user_id, assembly_id)
        if role:
            self.session.delete(role)
            return True
        return False


class SqlAlchemyAssemblyGSheetRepository(SqlAlchemyRepository, AssemblyGSheetRepository):
    """SQLAlchemy implementation of AssemblyGSheetRepository."""

    def add(self, item: AssemblyGSheet) -> None:
        """Add an AssemblyGSheet to the repository."""
        self.session.add(item)

    def get(self, item_id: uuid.UUID) -> AssemblyGSheet | None:
        """Get an AssemblyGSheet by its ID."""
        return self.session.query(AssemblyGSheet).filter_by(assembly_gsheet_id=item_id).first()

    def all(self) -> Iterable[AssemblyGSheet]:
        """Get all AssemblyGSheets."""
        return self.session.query(AssemblyGSheet).all()

    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> AssemblyGSheet | None:
        """Get an AssemblyGSheet by its assembly ID."""
        return self.session.query(AssemblyGSheet).filter_by(assembly_id=assembly_id).first()

    def delete(self, item: AssemblyGSheet) -> None:
        """Delete an AssemblyGSheet from the repository."""
        self.session.delete(item)


class SqlAlchemySelectionRunRecordRepository(SqlAlchemyRepository, SelectionRunRecordRepository):
    """SQLAlchemy implementation of SelectionRunRecordRepository."""

    def add(self, item: SelectionRunRecord) -> None:
        """Add a SelectionRunRecord to the repository."""
        self.session.add(item)

    def get(self, item_id: uuid.UUID) -> SelectionRunRecord | None:
        """Get a SelectionRunRecord by its task ID (primary key)."""
        return self.session.query(SelectionRunRecord).filter_by(task_id=item_id).first()

    def all(self) -> Iterable[SelectionRunRecord]:
        """Get all SelectionRunRecords ordered by creation time."""
        return self.session.query(SelectionRunRecord).order_by(orm.selection_run_records.c.created_at.desc()).all()

    def get_by_task_id(self, task_id: uuid.UUID) -> SelectionRunRecord | None:
        """Get a SelectionRunRecord by its task ID."""
        return self.session.query(SelectionRunRecord).filter_by(task_id=task_id).first()

    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> Iterable[SelectionRunRecord]:
        """Get all SelectionRunRecords for a specific assembly."""
        return (
            self.session.query(SelectionRunRecord)
            .filter_by(assembly_id=assembly_id)
            .order_by(orm.selection_run_records.c.created_at.desc())
            .all()
        )

    def get_latest_for_assembly(self, assembly_id: uuid.UUID) -> SelectionRunRecord | None:
        """Get the most recent SelectionRunRecord for an assembly."""
        return (
            self.session.query(SelectionRunRecord)
            .filter_by(assembly_id=assembly_id)
            .order_by(orm.selection_run_records.c.created_at.desc())
            .first()
        )

    def get_running_tasks(self) -> Iterable[SelectionRunRecord]:
        """Get all currently running selection tasks."""
        return (
            self.session.query(SelectionRunRecord)
            .filter(orm.selection_run_records.c.status == SelectionRunStatus.RUNNING.value)
            .order_by(orm.selection_run_records.c.created_at.desc())
            .all()
        )
