"""ABOUTME: User invite domain model for registration and access control
ABOUTME: Contains UserInvite class for managing invite codes and expiration"""

import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

from .value_objects import GlobalRole


def generate_invite_code(length: int = 12) -> str:
    """Generate a secure random invite code."""
    alphabet = string.ascii_uppercase + string.digits
    # Exclude confusing characters
    alphabet = alphabet.replace("O", "").replace("I", "").replace("0", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


class UserInvite:
    """User invite domain model for registration flow."""

    def __init__(
        self,
        global_role: GlobalRole,
        created_by: uuid.UUID,
        expires_in_hours: int = 168,  # 7 days default
        invite_id: uuid.UUID | None = None,
        code: str | None = None,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
        used_by: uuid.UUID | None = None,
        used_at: datetime | None = None,
    ):
        if expires_in_hours <= 0:
            raise ValueError("Expiry hours must be positive")

        current_time = created_at or datetime.now(UTC)

        self.id = invite_id or uuid.uuid4()
        self.code = code or generate_invite_code()
        self.global_role = global_role
        self.created_by = created_by
        self.created_at = current_time
        self.expires_at = expires_at or (current_time + timedelta(hours=expires_in_hours))
        self.used_by = used_by
        self.used_at = used_at

    def is_valid(self) -> bool:
        """Check if invite is valid (not expired and not used)."""
        now = datetime.now(UTC)
        return self.used_by is None and self.expires_at > now

    def use(self, user_id: uuid.UUID) -> None:
        """Mark invite as used by a user."""
        if self.used_by is not None:
            raise ValueError("Invite has already been used")

        if not self.is_valid():
            raise ValueError("Cannot use invalid invite")

        self.used_by = user_id
        self.used_at = datetime.now(UTC)

    def is_expired(self) -> bool:
        """Check if invite has expired."""
        return datetime.now(UTC) >= self.expires_at

    def is_used(self) -> bool:
        """Check if invite has been used."""
        return self.used_by is not None

    def time_until_expiry(self) -> timedelta:
        """Get time remaining until expiry."""
        return self.expires_at - datetime.now(UTC)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UserInvite):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
