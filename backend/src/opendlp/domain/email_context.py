"""ABOUTME: View-objects supplying a documented context to email templates
ABOUTME: Builds best-effort respondent names so the sandbox never sees raw aggregates"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from opendlp.domain.respondents import normalise_field_name

if TYPE_CHECKING:
    from opendlp.domain.assembly import Assembly
    from opendlp.domain.respondents import Respondent


@dataclass(frozen=True)
class AssemblyContext:
    """Assembly fields exposed to email template authors."""

    title: str = ""
    question: str = ""
    first_assembly_date: str = ""
    number_to_select: int = 0

    @classmethod
    def from_assembly(cls, assembly: "Assembly") -> "AssemblyContext":
        return cls(
            title=assembly.title,
            question=assembly.question,
            first_assembly_date=assembly.first_assembly_date.isoformat() if assembly.first_assembly_date else "",
            number_to_select=assembly.number_to_select,
        )


def _derive_names(attributes: Mapping[str, Any]) -> tuple[str, str, str]:
    normalised: dict[str, str] = {}
    for key, value in attributes.items():
        name = normalise_field_name(key)
        if name and name not in normalised:
            normalised[name] = str(value).strip() if value is not None else ""
    first = normalised.get("firstname", "")
    last = normalised.get("lastname") or normalised.get("surname") or ""
    full = normalised.get("fullname") or normalised.get("name") or ""
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
        return self._first or "Friend"


def build_context(assembly: AssemblyContext, respondent: RespondentContext) -> dict[str, Any]:
    return {"assembly": assembly, "respondent": respondent}


def sample_context() -> dict[str, Any]:
    return build_context(
        AssemblyContext(
            title="Sample Assembly",
            question="Should the city pedestrianise the centre?",
            first_assembly_date="2026-01-01",
            number_to_select=100,
        ),
        RespondentContext(email="sample@example.com", attributes={"first_name": "Sam", "last_name": "Sample"}),
    )
