"""ABOUTME: Respondent domain model for assembly participant pool management
ABOUTME: Contains Respondent class for tracking participants in the selection pool"""

import uuid
from datetime import UTC, datetime
from typing import Any

from opendlp.domain.value_objects import RespondentSourceType, RespondentStatus


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

    def is_available_for_selection(self) -> bool:
        """Check if respondent is available for selection"""
        return self.selection_status == RespondentStatus.POOL and self.eligible is True and self.can_attend is True

    def get_attribute(self, key: str, default: Any = None) -> Any:
        """Safely get attribute value"""
        return self.attributes.get(key, default)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Respondent):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def create_detached_copy(self) -> "Respondent":
        """Create a detached copy for use outside SQLAlchemy sessions"""
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
            attributes=self.attributes.copy(),
            respondent_id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
