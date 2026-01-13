"""ABOUTME: User domain models for OpenDLP authentication and authorization
ABOUTME: Contains User and UserAssemblyRole classes as plain Python objects"""

import uuid
from datetime import UTC, datetime

from .value_objects import AssemblyRole, GlobalRole, validate_email


class User:
    """User domain model for authentication and role management."""

    def __init__(
        self,
        email: str,
        global_role: GlobalRole,
        first_name: str = "",
        last_name: str = "",
        user_id: uuid.UUID | None = None,
        password_hash: str | None = None,
        oauth_provider: str | None = None,
        oauth_id: str | None = None,
        created_at: datetime | None = None,
        is_active: bool = True,
        user_data_agreement_agreed_at: datetime | None = None,
    ):
        validate_email(email)

        if not password_hash and not (oauth_provider and oauth_id):
            raise ValueError("User must have either password_hash or OAuth credentials")

        self.id = user_id or uuid.uuid4()
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.password_hash = password_hash
        self.oauth_provider = oauth_provider
        self.oauth_id = oauth_id
        self.global_role = global_role
        self.created_at = created_at or datetime.now(UTC)
        self.is_active = is_active
        self.user_data_agreement_agreed_at = user_data_agreement_agreed_at
        self.assembly_roles: list[UserAssemblyRole] = []

    # couple of things required for flask_login
    @property
    def is_authenticated(self) -> bool:
        return self.is_active

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)

    @property
    def display_name(self) -> str:
        """Get user's display name, preferring full name over email."""
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.email.split("@")[0]  # Use email prefix as fallback

    @property
    def full_name(self) -> str:
        """Get user's full name."""
        return f"{self.first_name} {self.last_name}".strip()

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

    def add_oauth_credentials(self, provider: str, oauth_id: str) -> None:
        """Add OAuth credentials to existing user account (account linking)."""
        if not provider or not oauth_id:
            raise ValueError("Provider and OAuth ID are required")

        self.oauth_provider = provider
        self.oauth_id = oauth_id

    def remove_password(self) -> None:
        """Remove password authentication. Requires OAuth to be set."""
        if not self.oauth_provider:
            raise ValueError("Cannot remove password: no OAuth authentication configured")

        self.password_hash = None

    def remove_oauth(self) -> None:
        """Remove OAuth authentication. Requires password to be set."""
        if not self.password_hash:
            raise ValueError("Cannot remove OAuth: no password authentication configured")

        self.oauth_provider = None
        self.oauth_id = None

    def has_multiple_auth_methods(self) -> bool:
        """Check if user has more than one authentication method."""
        return bool(self.password_hash and self.oauth_provider)

    def get_assembly_role(self, assembly_id: uuid.UUID) -> AssemblyRole | None:
        """Get user's role for a specific assembly."""
        for role in self.assembly_roles:
            if role.assembly_id == assembly_id:
                return role.role
        return None

    def mark_data_agreement_agreed(self) -> None:
        """Mark that the user has agreed to the data agreement at the current time."""
        self.user_data_agreement_agreed_at = datetime.now(UTC)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):  # pragma: no cover
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def create_detached_copy(self) -> "User":
        """Create a detached copy of this user for use outside SQLAlchemy sessions"""
        detached_user = User(
            email=self.email,
            global_role=self.global_role,
            first_name=self.first_name,
            last_name=self.last_name,
            user_id=self.id,
            password_hash=self.password_hash,
            oauth_provider=self.oauth_provider,
            oauth_id=self.oauth_id,
            created_at=self.created_at,
            is_active=self.is_active,
            user_data_agreement_agreed_at=self.user_data_agreement_agreed_at,
        )
        detached_user.assembly_roles = [r.create_detached_copy() for r in self.assembly_roles]
        return detached_user


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
        self.created_at = created_at or datetime.now(UTC)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UserAssemblyRole):  # pragma: no cover
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def create_detached_copy(self) -> "UserAssemblyRole":
        return UserAssemblyRole(
            user_id=self.user_id,
            assembly_id=self.assembly_id,
            role=self.role,
            role_id=self.id,
            created_at=self.created_at,
        )
