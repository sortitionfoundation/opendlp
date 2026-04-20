"""ABOUTME: Per-assembly respondent field schema — groups, labels, and display order.
ABOUTME: Drives grouping on the view_registrant detail page and seeds the future registration form."""

import uuid
from datetime import UTC, datetime
from enum import Enum

from opendlp.translations import lazy_gettext as _l


class RespondentFieldGroup(Enum):
    """Fixed catalogue of groups that a respondent field can belong to.

    Stored on ``RespondentFieldDefinition.group`` and used to bucket fields
    in the view_registrant detail page. Order here is not significant —
    ``GROUP_DISPLAY_ORDER`` below fixes the rendering order.
    """

    ELIGIBILITY = "eligibility"
    NAME_AND_CONTACT = "name_and_contact"
    ADDRESS = "address"
    ABOUT_YOU = "about_you"
    CONSENT = "consent"
    OTHER = "other"


GROUP_DISPLAY_ORDER: list[RespondentFieldGroup] = [
    RespondentFieldGroup.ELIGIBILITY,
    RespondentFieldGroup.NAME_AND_CONTACT,
    RespondentFieldGroup.ADDRESS,
    RespondentFieldGroup.ABOUT_YOU,
    RespondentFieldGroup.CONSENT,
    RespondentFieldGroup.OTHER,
]


GROUP_LABELS: dict[RespondentFieldGroup, str] = {
    RespondentFieldGroup.ELIGIBILITY: _l("Eligibility"),
    RespondentFieldGroup.NAME_AND_CONTACT: _l("Name and contact"),
    RespondentFieldGroup.ADDRESS: _l("Address"),
    RespondentFieldGroup.ABOUT_YOU: _l("About you"),
    RespondentFieldGroup.CONSENT: _l("Consent"),
    RespondentFieldGroup.OTHER: _l("Other"),
}


# Default sort_order gap — rows are seeded at multiples of this so drag-and-drop
# reorder can slot a field between two existing ones before re-issuing.
SORT_ORDER_STEP = 10


class RespondentFieldDefinition:
    """One field in the per-assembly respondent schema.

    ``field_key`` matches a ``Respondent.attributes`` key (for custom fields)
    or a reserved top-level field name (``email``, ``consent``, ...) when
    ``is_fixed=True``.
    """

    def __init__(
        self,
        assembly_id: uuid.UUID,
        field_key: str,
        label: str,
        group: RespondentFieldGroup,
        sort_order: int,
        is_fixed: bool = False,
        is_derived: bool = False,
        derived_from: list[str] | None = None,
        derivation_kind: str = "",
        field_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        if not field_key or not field_key.strip():
            raise ValueError("field_key is required")
        if not label or not label.strip():
            raise ValueError("label is required")
        if sort_order < 0:
            raise ValueError("sort_order cannot be negative")
        if is_derived and not derived_from:
            raise ValueError("derived_from must be provided when is_derived is True")

        self.id = field_id or uuid.uuid4()
        self.assembly_id = assembly_id
        self.field_key = field_key.strip()
        self.label = label.strip()
        self.group = group
        self.sort_order = sort_order
        self.is_fixed = is_fixed
        self.is_derived = is_derived
        self.derived_from = list(derived_from) if derived_from else None
        self.derivation_kind = derivation_kind.strip()
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)

    def update(
        self,
        label: str | None = None,
        group: RespondentFieldGroup | None = None,
        sort_order: int | None = None,
    ) -> None:
        """Update mutable fields. Touches ``updated_at`` on any change."""
        changed = False
        if label is not None:
            if not label.strip():
                raise ValueError("label cannot be empty")
            self.label = label.strip()
            changed = True
        if group is not None:
            self.group = group
            changed = True
        if sort_order is not None:
            if sort_order < 0:
                raise ValueError("sort_order cannot be negative")
            self.sort_order = sort_order
            changed = True
        if changed:
            self.updated_at = datetime.now(UTC)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RespondentFieldDefinition):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def create_detached_copy(self) -> "RespondentFieldDefinition":
        """Create a detached copy for use outside SQLAlchemy sessions."""
        return RespondentFieldDefinition(
            assembly_id=self.assembly_id,
            field_key=self.field_key,
            label=self.label,
            group=self.group,
            sort_order=self.sort_order,
            is_fixed=self.is_fixed,
            is_derived=self.is_derived,
            derived_from=list(self.derived_from) if self.derived_from else None,
            derivation_kind=self.derivation_kind,
            field_id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


# Reserved respondent top-level fields that live in the schema (editable group/order).
# Paired with their default group, used when seeding a fresh schema.
IN_SCHEMA_FIXED_FIELDS: list[tuple[str, RespondentFieldGroup, str]] = [
    ("email", RespondentFieldGroup.NAME_AND_CONTACT, "Email"),
    ("eligible", RespondentFieldGroup.ELIGIBILITY, "Eligible"),
    ("can_attend", RespondentFieldGroup.ELIGIBILITY, "Can attend"),
    ("consent", RespondentFieldGroup.CONSENT, "Consent"),
    ("stay_on_db", RespondentFieldGroup.CONSENT, "Stay on database"),
]


def humanise_field_key(field_key: str) -> str:
    """Default display label: underscores/hyphens to spaces, sentence case.

    ``first_name`` -> ``First name``. Preserves existing capitalisation of
    individual letters beyond the first — e.g. ``NHS_number`` -> ``NHS number``.
    """
    spaced = field_key.replace("_", " ").replace("-", " ").strip()
    if not spaced:
        return field_key
    # Only capitalise the first character; leave the rest alone so acronyms survive.
    return spaced[0].upper() + spaced[1:]
