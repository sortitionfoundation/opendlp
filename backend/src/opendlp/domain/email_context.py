"""ABOUTME: View-objects supplying a documented context to email templates
ABOUTME: Builds best-effort respondent names so the sandbox never sees raw aggregates"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from babel.dates import format_date

from opendlp.domain.respondent_field_schema import (
    BOOL_TYPES,
    CHOICE_TYPES,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
)
from opendlp.domain.respondents import normalise_field_name
from opendlp.translations import gettext as _

if TYPE_CHECKING:
    from opendlp.domain.assembly import Assembly
    from opendlp.domain.respondents import Respondent


@dataclass(frozen=True)
class AssemblyContext:
    """Project fields exposed to email template authors.

    Templates reach this object as ``project`` and, for emails written before
    the interface called it a project, as ``assembly``. The date is likewise
    readable as ``first_event_date`` or ``first_assembly_date``.
    """

    title: str = ""
    question: str = ""
    first_assembly_date: str = ""
    # The same date written out for the reader, such as "14 November 2026".
    first_assembly_date_text: str = ""
    number_to_select: int = 0

    @property
    def first_event_date(self) -> str:
        return self.first_assembly_date

    @property
    def first_event_date_text(self) -> str:
        return self.first_assembly_date_text

    @classmethod
    def from_assembly(cls, assembly: "Assembly", locale: str = "en") -> "AssemblyContext":
        """``locale`` is the language the email is read in, such as "hu" or "en_GB"."""
        first_date = assembly.first_assembly_date
        return cls(
            title=assembly.title,
            question=assembly.question,
            first_assembly_date=first_date.isoformat() if first_date else "",
            first_assembly_date_text=format_date(first_date, "long", locale=locale) if first_date else "",
            number_to_select=assembly.number_to_select,
        )


# Normalised field-name aliases for the respondent's name. The single source of
# truth for both deriving names off a real respondent (_derive_names) and
# synthesising a sample respondent (_sample_field_value) - keep the two in step
# by adding any new alias here rather than in either consumer.
_FIRST_NAME_KEYS = ("firstname",)
_LAST_NAME_KEYS = ("lastname", "surname")
_FULL_NAME_KEYS = ("fullname", "name")


def _first_non_empty(normalised: Mapping[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = normalised.get(key)
        if value:
            return value
    return ""


def _derive_names(attributes: Mapping[str, Any]) -> tuple[str, str, str]:
    normalised: dict[str, str] = {}
    for key, value in attributes.items():
        name = normalise_field_name(key)
        if name and name not in normalised:
            normalised[name] = str(value).strip() if value is not None else ""
    first = _first_non_empty(normalised, _FIRST_NAME_KEYS)
    last = _first_non_empty(normalised, _LAST_NAME_KEYS)
    full = _first_non_empty(normalised, _FULL_NAME_KEYS)
    # A form that asks only for a name gets the whole of it as the first name:
    # splitting it would guess wrong for names written family name first.
    if not first:
        first = full
    if not full:
        full = " ".join(part for part in (first, last) if part)
    return first, last, full


class RespondentContext:
    """Respondent fields exposed to email template authors."""

    def __init__(self, email: str = "", attributes: Mapping[str, Any] | None = None):
        self.email = email
        self.attributes = dict(attributes or {})
        self._first, self._last, self._full = _derive_names(self.attributes)

    @classmethod
    def from_respondent(cls, respondent: "Respondent") -> "RespondentContext":
        return cls(email=respondent.email, attributes=respondent.attributes)

    @property
    def first_name(self) -> str:
        return self._first

    @property
    def last_name(self) -> str:
        return self._last

    @property
    def full_name(self) -> str:
        return self._full

    @property
    def first_name_or_friend(self) -> str:
        # Translated at render time, so it follows the language the email is read
        # in. It completes a greeting such as "Hi Friend," or "Kedves Résztvevő!".
        return self._first or _("Friend")


def build_context(assembly: AssemblyContext, respondent: RespondentContext) -> dict[str, Any]:
    # "project" is the name the editor offers; "assembly" keeps saved emails working.
    return {"assembly": assembly, "project": assembly, "respondent": respondent}


_SAMPLE_FIRST_NAME = "Alex"
_SAMPLE_LAST_NAME = "Example"
_SAMPLE_EMAIL = "sample@example.com"


def _static_sample_respondent(to_email: str) -> RespondentContext:
    """The canonical made-up respondent, used when there is no field schema to shape one."""
    return RespondentContext(
        email=to_email,
        attributes={"first_name": _SAMPLE_FIRST_NAME, "last_name": _SAMPLE_LAST_NAME},
    )


def _sample_field_value(fd: RespondentFieldDefinition, to_email: str) -> Any:
    field_type = fd.effective_field_type
    if field_type in BOOL_TYPES:
        return True
    if field_type in CHOICE_TYPES:
        return fd.options[0].value if fd.options else ""
    if field_type == FieldType.INTEGER:
        # Plausible as a year of birth, so age-bracket-style templates read sensibly.
        return 1985
    if field_type == FieldType.DATE:
        return "1985-06-15"
    if field_type == FieldType.EMAIL:
        return to_email
    name = normalise_field_name(fd.field_key)
    if name in _FIRST_NAME_KEYS:
        return _SAMPLE_FIRST_NAME
    if name in _LAST_NAME_KEYS:
        return _SAMPLE_LAST_NAME
    if name in _FULL_NAME_KEYS:
        return f"{_SAMPLE_FIRST_NAME} {_SAMPLE_LAST_NAME}"
    return f"[{fd.label}]"


def sample_respondent_context(
    field_definitions: Sequence[RespondentFieldDefinition], to_email: str = _SAMPLE_EMAIL
) -> RespondentContext:
    """A made-up respondent for test sends, shaped by the assembly's field schema.

    Every attribute a real registrant would end up with gets a value: fields
    collected on the form get a type-appropriate sample (name fields get a
    recognisable fake name, choices their first option), and derived fields get
    a ``[Label]`` placeholder since their real values are computed after
    registration. Fixed fields are top-level on a Respondent rather than
    attributes, so they are skipped; the email address is the test recipient's.
    """
    attributes: dict[str, Any] = {}
    for fd in field_definitions:
        if fd.is_derived:
            attributes[fd.field_key] = f"[{fd.label}]"
        elif fd.on_registration_page != FieldOnRegistrationPage.NO:
            attributes[fd.field_key] = _sample_field_value(fd, to_email)
    if not attributes:
        return _static_sample_respondent(to_email)
    return RespondentContext(email=to_email, attributes=attributes)
