"""ABOUTME: Password reset domain model for secure password recovery
ABOUTME: Contains PasswordResetToken class for managing reset tokens and expiration"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta


def generate_reset_token(length: int = 32) -> str:
    """Generate a cryptographically secure URL-safe reset token."""
    return secrets.token_urlsafe(length)


class PasswordResetToken:
    """Password reset token domain model for secure password recovery."""

    def __init__(
        self,
        user_id: uuid.UUID,
        expires_in_hours: int = 1,  # 1 hour default for security
        token_id: uuid.UUID | None = None,
        token: str | None = None,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
        used_at: datetime | None = None,
    ):
        if expires_in_hours <= 0:
            raise ValueError("Expiry hours must be positive")

        current_time = created_at or datetime.now(UTC)

        self.id = token_id or uuid.uuid4()
        self.user_id = user_id
        self.token = token or generate_reset_token()
        self.created_at = current_time
        self.expires_at = expires_at or (current_time + timedelta(hours=expires_in_hours))
        self.used_at = used_at

    def is_valid(self) -> bool:
        """Check if token is valid (not expired and not used)."""
        now = datetime.now(UTC)
        return self.used_at is None and self.expires_at > now

    def use(self) -> None:
        """Mark token as used."""
        if self.used_at is not None:
            raise ValueError("Token has already been used")

        if not self.is_valid():
            raise ValueError("Cannot use invalid token")

        self.used_at = datetime.now(UTC)

    def is_expired(self) -> bool:
        """Check if token has expired."""
        return datetime.now(UTC) >= self.expires_at

    def is_used(self) -> bool:
        """Check if token has been used."""
        return self.used_at is not None

    def time_until_expiry(self) -> timedelta:
        """Get time remaining until expiry."""
        return self.expires_at - datetime.now(UTC)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PasswordResetToken):  # pragma: no cover
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def create_detached_copy(self) -> "PasswordResetToken":
        """Create a detached copy of this token for use outside SQLAlchemy sessions"""
        return PasswordResetToken(
            user_id=self.user_id,
            token_id=self.id,
            token=self.token,
            created_at=self.created_at,
            expires_at=self.expires_at,
            used_at=self.used_at,
        )
