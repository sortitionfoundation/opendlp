"""ABOUTME: Per-assembly respondent field schema — groups, labels, and display order.
ABOUTME: Shared infrastructure consumed by any module that needs respondent field metadata.

This module defines the canonical schema describing the fields that make up a
respondent for a given assembly. It is intentionally framework-agnostic and
module-agnostic: modules read from it, they do not each build a parallel one.

Current and anticipated consumers:

- The grouped view_registrant detail page (current): renders fields in the order
  and groups defined here.
- The registration form module (planned): will read the schema as its field
  catalogue when rendering the public form — see docs/agent/module_design.md.
- The targets module (potential): could eventually reference schema fields
  instead of matching by attribute name.
- Confirmation calling, export column ordering, etc. (potential): same pattern.

If you are adding a new module that reasons about respondent fields, read the
schema from here via ``respondent_field_schema_service`` rather than introducing
a parallel configuration. See docs/agent/446-grouped-registrant-view/respondent_field_schema.md
for the design rationale."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from opendlp.translations import lazy_gettext as _l

_UNSET: Any = object()


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


class FieldType(Enum):
    TEXT = "text"
    LONGTEXT = "longtext"
    BOOL = "bool"
    BOOL_OR_NONE = "bool_or_none"
    CHOICE_RADIO = "choice_radio"
    CHOICE_DROPDOWN = "choice_dropdown"
    INTEGER = "integer"
    EMAIL = "email"


FIELD_TYPE_LABELS: dict[FieldType, str] = {
    FieldType.TEXT: _l("Text"),
    FieldType.LONGTEXT: _l("Long text"),
    FieldType.BOOL: _l("Yes / No"),
    FieldType.BOOL_OR_NONE: _l("Yes / No / Not set"),
    FieldType.CHOICE_RADIO: _l("Choice (radios)"),
    FieldType.CHOICE_DROPDOWN: _l("Choice (dropdown)"),
    FieldType.INTEGER: _l("Whole number"),
    FieldType.EMAIL: _l("Email"),
}


BOOL_TYPES: frozenset[FieldType] = frozenset({FieldType.BOOL, FieldType.BOOL_OR_NONE})
CHOICE_TYPES: frozenset[FieldType] = frozenset({FieldType.CHOICE_RADIO, FieldType.CHOICE_DROPDOWN})


# Hardcoded override for fixed-field rows. The four eligibility/consent flags are
# bool | None in the domain, so they use BOOL_OR_NONE.
FIXED_FIELD_TYPES: dict[str, FieldType] = {
    "email": FieldType.EMAIL,
    "eligible": FieldType.BOOL_OR_NONE,
    "can_attend": FieldType.BOOL_OR_NONE,
    "consent": FieldType.BOOL_OR_NONE,
    "stay_on_db": FieldType.BOOL_OR_NONE,
}


def _validate_type_and_options(field_type: "FieldType", options: "list[ChoiceOption] | None") -> None:
    if field_type in CHOICE_TYPES:
        if not options:
            raise ValueError("Choice field requires a non-empty options list")
    elif options:
        raise ValueError("options must be None for non-choice field types")


@dataclass(frozen=True)
class ChoiceOption:
    value: str
    help_text: str = ""

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("ChoiceOption value cannot be blank")

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value, "help_text": self.help_text}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChoiceOption":
        return cls(value=data["value"], help_text=data.get("help_text", ""))


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
        field_type: FieldType = FieldType.TEXT,
        options: list[ChoiceOption] | None = None,
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
        _validate_type_and_options(field_type, options)

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
        self.field_type = field_type
        self.options = list(options) if options else None
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)

    @property
    def effective_field_type(self) -> FieldType:
        return FIXED_FIELD_TYPES.get(self.field_key, self.field_type)

    def update(
        self,
        label: str | None = None,
        group: RespondentFieldGroup | None = None,
        sort_order: int | None = None,
        field_type: FieldType | None = None,
        options: list[ChoiceOption] | None = _UNSET,
    ) -> None:
        """Update mutable fields. Touches ``updated_at`` on any change.

        ``options`` uses a sentinel (``_UNSET``) so callers can distinguish
        "leave alone" from "set to None". Pass ``options=None`` to clear.
        """
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
        if field_type is not None or options is not _UNSET:
            if self.is_fixed:
                raise ValueError("Cannot change field_type or options on a fixed field")
            new_type = field_type if field_type is not None else self.field_type
            # When the caller didn't pass options explicitly, preserve the
            # current list across choice<->choice transitions, but drop it
            # when switching to a non-choice type so the invariant holds.
            new_options = (None if new_type not in CHOICE_TYPES else self.options) if options is _UNSET else options
            _validate_type_and_options(new_type, new_options)
            self.field_type = new_type
            self.options = list(new_options) if new_options else None
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
            field_type=self.field_type,
            options=list(self.options) if self.options else None,
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
