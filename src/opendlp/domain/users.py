"""ABOUTME: User domain models for OpenDLP authentication and authorization
ABOUTME: Contains User and UserAssemblyRole classes as plain Python objects"""

import uuid
from datetime import datetime

from .value_objects import AssemblyRole, GlobalRole, validate_email, validate_username


class User:
    """User domain model for authentication and role management."""

    def __init__(
        self,
        username: str,
        email: str,
        global_role: GlobalRole,
        user_id: uuid.UUID | None = None,
        password_hash: str | None = None,
        oauth_provider: str | None = None,
        oauth_id: str | None = None,
        created_at: datetime | None = None,
        is_active: bool = True,
    ):
        validate_username(username)
        validate_email(email)

        if not password_hash and not (oauth_provider and oauth_id):
            raise ValueError("User must have either password_hash or OAuth credentials")

        self.id = user_id or uuid.uuid4()
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.oauth_provider = oauth_provider
        self.oauth_id = oauth_id
        self.global_role = global_role
        self.created_at = created_at or datetime.utcnow()
        self.is_active = is_active
        self.assembly_roles: list[UserAssemblyRole] = []

    def can_access_assembly(self, assembly_id: uuid.UUID) -> bool:
        """Check if user can access the given assembly."""
        if self.global_role in (GlobalRole.ADMIN, GlobalRole.GLOBAL_ORGANISER):
            return True

        return any(role.assembly_id == assembly_id for role in self.assembly_roles)

    def has_global_admin(self) -> bool:
        """Check if user has global admin privileges."""
        return self.global_role == GlobalRole.ADMIN

    def switch_to_oauth(self, provider: str, oauth_id: str) -> None:
        """Switch user authentication from password to OAuth."""
        if not provider or not oauth_id:
            raise ValueError("Provider and OAuth ID are required")

        self.oauth_provider = provider
        self.oauth_id = oauth_id
        self.password_hash = None

    def get_assembly_role(self, assembly_id: uuid.UUID) -> AssemblyRole | None:
        """Get user's role for a specific assembly."""
        for role in self.assembly_roles:
            if role.assembly_id == assembly_id:
                return role.role
        return None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


class UserAssemblyRole:
    """User role assignment for specific assemblies."""

    def __init__(
        self,
        user_id: uuid.UUID,
        assembly_id: uuid.UUID,
        role: AssemblyRole,
        role_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
    ):
        self.id = role_id or uuid.uuid4()
        self.user_id = user_id
        self.assembly_id = assembly_id
        self.role = role
        self.created_at = created_at or datetime.utcnow()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UserAssemblyRole):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
