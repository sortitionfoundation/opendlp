"""ABOUTME: UserBackupCode domain model for 2FA recovery codes
ABOUTME: Contains backup code entities as plain Python objects"""

import uuid
from datetime import UTC, datetime


class UserBackupCode:
    """Backup code domain model for 2FA recovery."""

    def __init__(
        self,
        user_id: uuid.UUID,
        code_hash: str,
        backup_code_id: uuid.UUID | None = None,
        used_at: datetime | None = None,
        created_at: datetime | None = None,
    ):
        self.id = backup_code_id or uuid.uuid4()
        self.user_id = user_id
        self.code_hash = code_hash
        self.used_at = used_at
        self.created_at = created_at or datetime.now(UTC)

    def is_used(self) -> bool:
        """Check if this backup code has been used."""
        return self.used_at is not None

    def mark_as_used(self) -> None:
        """Mark this backup code as used."""
        if self.used_at is not None:
            raise ValueError("Backup code has already been used")
        self.used_at = datetime.now(UTC)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UserBackupCode):  # pragma: no cover
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
