"""ABOUTME: Derivation rule value objects — age brackets, small mappings and large mappings.
ABOUTME: Pure domain logic for computing derived respondent field values; no database, no Flask.

Each derived ``RespondentFieldDefinition`` carries a ``derivation_type`` and a
``derivation_config`` dict. The rule classes here give that config behaviour:
``rule_from_field`` turns the stored pair back into a rule object, and each rule
serialises itself with ``to_config``. The three rules deliberately do not share
a ``derive()`` signature — an age rule needs a birth date, a postcode lookup
does not — so the dispatch in the service layer calls each one honestly.

The fallback value is a real output: it lands in the field's options, shows up
in target counts, and is the organiser's signal that source data needs
attention. The house convention is the literal ``"UNKNOWN"``.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from itertools import pairwise
from typing import Any

from opendlp.domain.respondent_field_schema import ChoiceOption, DerivationType
from opendlp.translations import gettext as _

DEFAULT_FALLBACK = "UNKNOWN"

# Ages beyond this are treated as data errors (a typo'd year), not people.
MAX_SANE_AGE = 120


def normalise_lookup_key(value: str) -> str:
    """Collapse a large-mapping key to its canonical form: uppercase, no whitespace.

    Applied to both sides of the lookup — on table upload and on derivation —
    so ``SW1A 1AA``, ``sw1a1aa`` and ``SW1A  1AA`` all match one stored key.
    """
    return "".join(value.split()).upper()


@dataclass(frozen=True)
class AgeBracketRule:
    """Buckets an age into labelled brackets, as of a fixed date.

    ``as_of_date`` is required and never "today": a derived value must not
    depend on when derivation happened to run, and the eligibility sentence
    has to name a specific date.
    """

    as_of_date: date
    min_age: int = 16
    max_age: int = 100
    boundaries: tuple[int, ...] = ()
    fallback: str = DEFAULT_FALLBACK

    def __post_init__(self) -> None:
        object.__setattr__(self, "boundaries", tuple(self.boundaries))
        if self.min_age <= 0:
            raise ValueError("min_age must be greater than zero")
        if self.max_age <= self.min_age:
            raise ValueError("max_age must be greater than min_age")
        if list(self.boundaries) != sorted(set(self.boundaries)):
            raise ValueError("boundaries must be sorted and unique")
        if any(not (self.min_age < b < self.max_age) for b in self.boundaries):
            raise ValueError("boundaries must be strictly between min_age and max_age")
        if not self.fallback.strip():
            raise ValueError("fallback cannot be blank")

    def bracket_labels(self) -> list[str]:
        """All bracket labels in ascending order, e.g. under-16, 16-21, ..., 100+."""
        edges = [self.min_age, *self.boundaries, self.max_age]
        labels = [f"under-{self.min_age}"]
        labels.extend(f"{lower}-{upper - 1}" for lower, upper in pairwise(edges))
        labels.append(f"{self.max_age}+")
        return labels

    def eligibility_sentence(self) -> str:
        """The self-declaration wording the registration form should carry.

        Generated from the same numbers the derivation uses, so the form
        wording and the bracket arithmetic cannot drift apart.
        """
        return _(
            "I will be at least %(min_age)s years old on %(as_of_date)s.",
            min_age=self.min_age,
            as_of_date=self.as_of_date.isoformat(),
        )

    def derive_from_date(self, born: date) -> str:
        """Bracket for an exact birth date."""
        had_birthday = (self.as_of_date.month, self.as_of_date.day) >= (born.month, born.day)
        age = self.as_of_date.year - born.year - (0 if had_birthday else 1)
        return self._bracket_for_age(age)

    def derive_from_year(self, year: int) -> str:
        """Bracket for a year of birth, treating the birthday as 1 January.

        Everyone born in a given year counts as having had their birthday, so
        some people land one bracket up from their true age. The eligibility
        checkbox does the real age gating; this is a data-quality backstop.
        """
        return self._bracket_for_age(self.as_of_date.year - year)

    def _bracket_for_age(self, age: int) -> str:
        if age < 0 or age > MAX_SANE_AGE:
            return self.fallback
        if age < self.min_age:
            return f"under-{self.min_age}"
        if age >= self.max_age:
            return f"{self.max_age}+"
        edges = [self.min_age, *self.boundaries, self.max_age]
        for lower, upper in pairwise(edges):
            if lower <= age < upper:
                return f"{lower}-{upper - 1}"
        raise AssertionError(f"age {age} escaped the bracket edges {edges}")  # pragma: no cover

    def to_config(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "min_age": self.min_age,
            "max_age": self.max_age,
            "boundaries": list(self.boundaries),
            "fallback": self.fallback,
        }

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "AgeBracketRule":
        raw_date = config.get("as_of_date")
        if not raw_date:
            raise ValueError("as_of_date is required in an age bracket config")
        return cls(
            as_of_date=date.fromisoformat(raw_date),
            min_age=config.get("min_age", 16),
            max_age=config.get("max_age", 100),
            boundaries=tuple(config.get("boundaries", ())),
            fallback=config.get("fallback", DEFAULT_FALLBACK),
        )


@dataclass(frozen=True)
class SmallMappingRule:
    """Maps one choice value to another via an inline table (≤ ~20 entries)."""

    mapping: dict[str, str] = field(default_factory=dict)
    fallback: str = DEFAULT_FALLBACK

    def __post_init__(self) -> None:
        object.__setattr__(self, "mapping", dict(self.mapping))
        if not self.mapping:
            raise ValueError("mapping cannot be empty")
        if not self.fallback.strip():
            raise ValueError("fallback cannot be blank")

    def derive(self, value: str) -> str:
        return self.mapping.get(value.strip(), self.fallback)

    def to_config(self) -> dict[str, Any]:
        return {"mapping": dict(self.mapping), "fallback": self.fallback}

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SmallMappingRule":
        return cls(mapping=config.get("mapping", {}), fallback=config.get("fallback", DEFAULT_FALLBACK))


@dataclass(frozen=True)
class LargeMappingRule:
    """Maps via a lookup table too big to inline (e.g. 200k+ postcodes).

    The rows live in ``respondent_field_mapping_entries``; the caller injects a
    lookup callable so this value object never holds the table itself.
    """

    fallback: str = DEFAULT_FALLBACK

    def __post_init__(self) -> None:
        if not self.fallback.strip():
            raise ValueError("fallback cannot be blank")

    def derive(self, value: str, lookup: Callable[[str], str | None]) -> str:
        key = normalise_lookup_key(value)
        if not key:
            return self.fallback
        result = lookup(key)
        return result if result is not None else self.fallback

    def to_config(self) -> dict[str, Any]:
        return {"fallback": self.fallback}

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "LargeMappingRule":
        return cls(fallback=config.get("fallback", DEFAULT_FALLBACK))


DerivationRule = AgeBracketRule | SmallMappingRule | LargeMappingRule


def rule_from_field(derivation_type: DerivationType, derivation_config: dict[str, Any]) -> DerivationRule:
    """Rebuild the rule object a derived field's stored (type, config) pair describes.

    Raises ``ValueError`` when the config does not satisfy the rule's own
    validation — a stored config can predate a code change, so this is the
    boundary where staleness surfaces.
    """
    match derivation_type:
        case DerivationType.AGE_BRACKET:
            return AgeBracketRule.from_config(derivation_config)
        case DerivationType.SMALL_MAPPING:
            return SmallMappingRule.from_config(derivation_config)
        case DerivationType.LARGE_MAPPING:
            return LargeMappingRule.from_config(derivation_config)
    raise ValueError(f"Unknown derivation type: {derivation_type}")  # pragma: no cover


def output_options(rule: DerivationRule, declared_outputs: list[str] | None = None) -> list[ChoiceOption]:
    """The ChoiceOptions a derived field must carry for this rule.

    Age brackets generate their own labels; mapping rules take the organiser's
    declared output values (a small mapping can fall back to the distinct
    values in its table). The fallback is always appended so the value
    round-trips through the edit form, export and target counts.
    """
    if isinstance(rule, AgeBracketRule):
        values = rule.bracket_labels()
    elif isinstance(rule, SmallMappingRule):
        values = declared_outputs if declared_outputs is not None else list(dict.fromkeys(rule.mapping.values()))
    else:
        if declared_outputs is None:
            raise ValueError("declared_outputs is required for a large mapping rule")
        values = declared_outputs
    if rule.fallback not in values:
        values = [*values, rule.fallback]
    return [ChoiceOption(value=value) for value in dict.fromkeys(values)]
