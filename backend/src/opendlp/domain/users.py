"""ABOUTME: User domain models for OpenDLP authentication and authorization
ABOUTME: Contains User and UserAssemblyRole classes as plain Python objects"""

import secrets
import uuid
from datetime import UTC, datetime

from .validators import validate_email
from .value_objects import AssemblyRole, GlobalRole

# Prefix marking a password hash that no input can ever match. A user must
# always have a password hash or OAuth credentials, so locking an account out
# replaces the hash with an unusable one rather than removing it.
UNUSABLE_PASSWORD_PREFIX = "!"  # noqa: S105 - a marker for hashes that cannot match, not a password

# Separates the user id from the session epoch in the value flask-login stores
# in the session cookie and the remember-me cookie.
SESSION_ID_SEPARATOR = "|"


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
        totp_secret_encrypted: str | None = None,
        totp_enabled: bool = False,
        totp_enabled_at: datetime | None = None,
        email_confirmed_at: datetime | None = None,
        sessions_invalidated_at: datetime | None = None,
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
        self.totp_secret_encrypted = totp_secret_encrypted
        self.totp_enabled = totp_enabled
        self.totp_enabled_at = totp_enabled_at
        self.email_confirmed_at = email_confirmed_at
        self.sessions_invalidated_at = sessions_invalidated_at
        self.assembly_roles: list[UserAssemblyRole] = []

    # couple of things required for flask_login
    @property
    def is_authenticated(self) -> bool:
        return self.is_active

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        """Return the id flask-login stores in the session and remember-me cookie.

        The session epoch is included so that invalidating sessions makes every
        previously issued id stale - see `session_epoch` and `load_user`.
        """
        return f"{self.id}{SESSION_ID_SEPARATOR}{self.session_epoch}"

    @property
    def session_epoch(self) -> str:
        """The marker distinguishing sessions issued before the last lockout from those after."""
        if self.sessions_invalidated_at is None:
            return ""
        return self.sessions_invalidated_at.isoformat()

    def invalidate_sessions(self) -> None:
        """Make every session and remember-me cookie issued so far unusable."""
        self.sessions_invalidated_at = datetime.now(UTC)

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

    def set_unusable_password(self) -> None:
        """Replace the password with a value that no input can ever match.

        Used when locking an account out: the old password must not work again,
        but the user still needs a password hash to satisfy the invariant that
        every user has at least one authentication method.
        """
        self.password_hash = f"{UNUSABLE_PASSWORD_PREFIX}{secrets.token_urlsafe(32)}"

    def has_usable_password(self) -> bool:
        """Check whether the user has a password they could actually log in with."""
        if not self.password_hash:
            return False
        return not self.password_hash.startswith(UNUSABLE_PASSWORD_PREFIX)

    def has_multiple_auth_methods(self) -> bool:
        """Check if user has more than one authentication method."""
        return bool(self.has_usable_password() and self.oauth_provider)

    def get_assembly_role(self, assembly_id: uuid.UUID) -> AssemblyRole | None:
        """Get user's role for a specific assembly."""
        for role in self.assembly_roles:
            if role.assembly_id == assembly_id:
                return role.role
        return None

    def mark_data_agreement_agreed(self) -> None:
        """Mark that the user has agreed to the data agreement at the current time."""
        self.user_data_agreement_agreed_at = datetime.now(UTC)

    def enable_totp(self, encrypted_secret: str) -> None:
        """Enable TOTP 2FA with encrypted secret."""
        if self.oauth_provider:
            raise ValueError("Cannot enable 2FA for OAuth users")
        self.totp_secret_encrypted = encrypted_secret
        self.totp_enabled = True
        self.totp_enabled_at = datetime.now(UTC)

    def disable_totp(self) -> None:
        """Disable TOTP 2FA."""
        self.totp_secret_encrypted = None
        self.totp_enabled = False
        self.totp_enabled_at = None

    def requires_2fa(self) -> bool:
        """Check if user requires 2FA verification (password users with 2FA enabled)."""
        return self.totp_enabled and not self.oauth_provider

    def confirm_email(self) -> None:
        """Mark email as confirmed."""
        self.email_confirmed_at = datetime.now(UTC)

    def is_email_confirmed(self) -> bool:
        """Check if email is confirmed."""
        return self.email_confirmed_at is not None

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
            totp_secret_encrypted=self.totp_secret_encrypted,
            totp_enabled=self.totp_enabled,
            totp_enabled_at=self.totp_enabled_at,
            email_confirmed_at=self.email_confirmed_at,
            sessions_invalidated_at=self.sessions_invalidated_at,
        )
        detached_user.assembly_roles = [r.create_detached_copy() for r in self.assembly_roles]
        return detached_user


def split_session_id(session_id: str) -> tuple[uuid.UUID, str] | None:
    """Split a value produced by `User.get_id()` into a user id and session epoch.

    Returns None if the value is not in that form - including a bare user id,
    which is what sessions issued before session epochs existed contain.
    """
    user_id_str, separator, epoch = session_id.partition(SESSION_ID_SEPARATOR)
    if not separator:
        return None
    try:
        return uuid.UUID(user_id_str), epoch
    except ValueError:
        return None


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
