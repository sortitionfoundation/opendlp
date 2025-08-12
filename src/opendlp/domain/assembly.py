"""ABOUTME: Assembly domain model for Citizens' Assembly management
ABOUTME: Contains Assembly class representing policy questions and selection configuration"""

import uuid
from datetime import date, datetime

from .value_objects import AssemblyStatus


class Assembly:
    """Assembly domain model for Citizens' Assembly configuration."""

    def __init__(
        self,
        title: str,
        question: str,
        gsheet: str,
        first_assembly_date: date,
        assembly_id: uuid.UUID | None = None,
        status: AssemblyStatus = AssemblyStatus.ACTIVE,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        if not title or not title.strip():
            raise ValueError("Assembly title is required")

        if not question or not question.strip():
            raise ValueError("Assembly question is required")

        if not gsheet or not gsheet.strip():
            raise ValueError("Google sheet reference is required")

        if first_assembly_date <= date.today():
            raise ValueError("First assembly date must be in the future")

        self.id = assembly_id or uuid.uuid4()
        self.title = title.strip()
        self.question = question.strip()
        self.gsheet = gsheet.strip()
        self.first_assembly_date = first_assembly_date
        self.status = status
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()

    def archive(self) -> None:
        """Archive this assembly."""
        self.status = AssemblyStatus.ARCHIVED
        self.updated_at = datetime.utcnow()

    def reactivate(self) -> None:
        """Reactivate this assembly."""
        self.status = AssemblyStatus.ACTIVE
        self.updated_at = datetime.utcnow()

    def update_details(
        self,
        title: str | None = None,
        question: str | None = None,
        gsheet: str | None = None,
        first_assembly_date: date | None = None,
    ) -> None:
        """Update assembly details."""
        if title is not None:
            if not title.strip():
                raise ValueError("Assembly title cannot be empty")
            self.title = title.strip()

        if question is not None:
            if not question.strip():
                raise ValueError("Assembly question cannot be empty")
            self.question = question.strip()

        if gsheet is not None:
            if not gsheet.strip():
                raise ValueError("Google sheet reference cannot be empty")
            self.gsheet = gsheet.strip()

        if first_assembly_date is not None:
            if first_assembly_date <= date.today():
                raise ValueError("First assembly date must be in the future")
            self.first_assembly_date = first_assembly_date

        self.updated_at = datetime.utcnow()

    def is_active(self) -> bool:
        """Check if assembly is active."""
        return self.status == AssemblyStatus.ACTIVE

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Assembly):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
