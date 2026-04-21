"""ABOUTME: Respondent domain model for assembly participant pool management
ABOUTME: Contains Respondent class for tracking participants in the selection pool"""

import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from opendlp.domain.value_objects import RespondentSourceType, RespondentStatus


def normalise_field_name(key: str) -> str:
    """Normalise a field name for loose matching.

    Lowercases the key and strips everything that isn't ``a-z0-9``.
    Keys with no alphanumerics normalise to the empty string.
    """
    return re.sub(r"[^a-z0-9]", "", key.lower())


def pop_normalised(attrs: dict[str, Any], key: str, default: Any = None) -> Any:
    """Pop a key from dict using normalised matching.

    Matches keys like "canAttend", "can_attend", "CAN_ATTEND" to "can_attend".
    """
    key_normal = normalise_field_name(key)
    for k in list(attrs.keys()):
        if normalise_field_name(k) == key_normal:
            return attrs.pop(k)
    return default


# Top-level Respondent fields that must not be shadowed by an attribute key.
# Kept in sync with the Respondent constructor signature.
_RESERVED_FIELD_NAMES: frozenset[str] = frozenset(
    normalise_field_name(name)
    for name in (
        "id",
        "assembly_id",
        "external_id",
        "selection_status",
        "selection_run_id",
        "consent",
        "stay_on_db",
        "eligible",
        "can_attend",
        "email",
        "source_type",
        "source_reference",
        "created_at",
        "updated_at",
    )
)


def validate_no_field_name_collisions(field_names: Iterable[str]) -> None:
    """Reject attribute field name sets that would collide after normalisation.

    Two keys that normalise to the same value are rejected. Keys that
    normalise to the empty string are rejected. Keys that normalise to
    the name of a reserved top-level Respondent field are rejected.
    """
    seen: dict[str, str] = {}
    for name in field_names:
        normalised = normalise_field_name(name)
        if not normalised:
            raise ValueError(f"Field name {name!r} normalises to an empty string")
        if normalised in _RESERVED_FIELD_NAMES:
            raise ValueError(f"Field name {name!r} collides with a reserved Respondent field ({normalised!r})")
        if normalised in seen:
            raise ValueError(f"Field names {seen[normalised]!r} and {name!r} both normalise to {normalised!r}")
        seen[normalised] = name


class Respondent:
    """Respondent domain model for participant tracking"""

    def __init__(
        self,
        assembly_id: uuid.UUID,
        external_id: str,
        selection_status: RespondentStatus = RespondentStatus.POOL,
        selection_run_id: uuid.UUID | None = None,
        consent: bool | None = None,
        stay_on_db: bool | None = None,
        eligible: bool | None = None,
        can_attend: bool | None = None,
        email: str = "",
        source_type: RespondentSourceType = RespondentSourceType.MANUAL_ENTRY,
        source_reference: str = "",
        attributes: dict[str, Any] | None = None,
        respondent_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        if not external_id.strip():
            raise ValueError("external_id is required")

        self.id = respondent_id or uuid.uuid4()
        self.assembly_id = assembly_id
        self.external_id = external_id.strip()
        self.selection_status = selection_status
        self.selection_run_id = selection_run_id
        self.consent = consent
        self.stay_on_db = stay_on_db
        self.eligible = eligible
        self.can_attend = can_attend
        self.email = email.strip()
        self.source_type = source_type
        self.source_reference = source_reference.strip()
        self.attributes = attributes or {}
        validate_no_field_name_collisions(self.attributes.keys())
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)

    def mark_as_selected(self, selection_run_id: uuid.UUID) -> None:
        """Mark respondent as selected in a specific selection run"""
        self.selection_status = RespondentStatus.SELECTED
        self.selection_run_id = selection_run_id
        self.updated_at = datetime.now(UTC)

    def mark_as_confirmed(self) -> None:
        """Mark selected respondent as confirmed"""
        if self.selection_status != RespondentStatus.SELECTED:
            raise ValueError("Only selected respondents can be marked as confirmed")
        self.selection_status = RespondentStatus.CONFIRMED
        self.updated_at = datetime.now(UTC)

    def mark_as_withdrawn(self) -> None:
        """Mark respondent as withdrawn"""
        if self.selection_status not in (RespondentStatus.SELECTED, RespondentStatus.CONFIRMED):
            raise ValueError("Only selected or confirmed respondents can be withdrawn")
        self.selection_status = RespondentStatus.WITHDRAWN
        self.updated_at = datetime.now(UTC)

    def reset_to_pool(self) -> None:
        """Reset respondent back to pool status, clearing any selection run association"""
        self.selection_status = RespondentStatus.POOL
        self.selection_run_id = None
        self.updated_at = datetime.now(UTC)

    def is_available_for_selection(self) -> bool:
        """Check if respondent is available for selection"""
        return (
            self.selection_status == RespondentStatus.POOL
            and self.eligible is not False
            and self.can_attend is not False
        )

    def get_attribute(self, key: str, default: Any = None) -> Any:
        """Safely get attribute value"""
        return self.attributes.get(key, default)

    def display_name(self, field_names: list[str]) -> str:
        """Build a human-readable name from the given attribute fields.

        Joins non-empty values from ``field_names`` with a single space.
        Falls back to the local-part of the email, then to ``external_id``.
        """
        parts = []
        for field in field_names:
            value = self.attributes.get(field)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                parts.append(text)
        if parts:
            return " ".join(parts)
        if self.email:
            return self.email.split("@", 1)[0]
        return self.external_id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Respondent):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def create_detached_copy(self) -> "Respondent":
        """Create a detached copy for use outside SQLAlchemy sessions."""
        return Respondent(
            assembly_id=self.assembly_id,
            external_id=self.external_id,
            selection_status=self.selection_status,
            selection_run_id=self.selection_run_id,
            consent=self.consent,
            stay_on_db=self.stay_on_db,
            eligible=self.eligible,
            can_attend=self.can_attend,
            email=self.email,
            source_type=self.source_type,
            source_reference=self.source_reference,
            attributes=self.attributes,
            respondent_id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
