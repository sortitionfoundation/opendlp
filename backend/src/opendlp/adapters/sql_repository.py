"""ABOUTME: SQLAlchemy implementations of repository interfaces
ABOUTME: Provides concrete database operations using SQLAlchemy sessions"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from opendlp.adapters import orm
from opendlp.domain.assembly import Assembly
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyStatus, GlobalRole
from opendlp.service_layer.repositories import (
    AssemblyRepository,
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

    def list(self) -> Iterable[User]:
        """List all users."""
        return self.session.query(User).all()

    def get_by_username(self, username: str) -> User | None:
        """Get a user by their username."""
        return self.session.query(User).filter_by(username=username).first()

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

    def list(self) -> Iterable[Assembly]:
        """List all assemblies."""
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

    def list(self) -> Iterable[UserInvite]:
        """List all invites."""
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

    def list(self) -> Iterable[UserAssemblyRole]:
        """List all invites."""
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
