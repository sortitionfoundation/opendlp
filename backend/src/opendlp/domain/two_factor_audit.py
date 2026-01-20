"""ABOUTME: TwoFactorAuditLog domain model for tracking 2FA security events
ABOUTME: Contains audit log entities for 2FA setup, disable, and recovery events"""

import uuid
from datetime import UTC, datetime


class TwoFactorAuditLog:
    """Audit log domain model for tracking 2FA security events."""

    def __init__(
        self,
        user_id: uuid.UUID,
        action: str,
        performed_by: uuid.UUID | None = None,
        audit_log_id: uuid.UUID | None = None,
        timestamp: datetime | None = None,
        metadata: dict | None = None,
    ):
        self.id = audit_log_id or uuid.uuid4()
        self.user_id = user_id
        self.action = action
        self.performed_by = performed_by
        self.timestamp = timestamp or datetime.now(UTC)
        self.metadata = metadata or {}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TwoFactorAuditLog):  # pragma: no cover
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
