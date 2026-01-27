"""ABOUTME: Domain model for TOTP verification attempts for rate limiting
ABOUTME: Tracks successful and failed 2FA verification attempts with timestamps"""

import uuid
from datetime import UTC, datetime


class TotpVerificationAttempt:
    """Represents a TOTP verification attempt for rate limiting."""

    def __init__(
        self,
        user_id: uuid.UUID,
        success: bool,
        attempt_id: uuid.UUID | None = None,
        attempted_at: datetime | None = None,
    ):
        """Create a new TOTP verification attempt.

        Args:
            user_id: The user's UUID
            success: Whether the verification was successful
            attempt_id: Optional UUID for the attempt (generated if not provided)
            attempted_at: Optional timestamp (defaults to now)
        """
        self.id = attempt_id or uuid.uuid4()
        self.user_id = user_id
        self.attempted_at = attempted_at or datetime.now(UTC)
        self.success = success

    def __eq__(self, other: object) -> bool:
        """Two attempts are equal if they have the same ID."""
        if not isinstance(other, TotpVerificationAttempt):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        """Hash based on ID."""
        return hash(self.id)
