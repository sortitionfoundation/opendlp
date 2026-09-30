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

import re
from collections.abc import Callable, Sequence
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
class AgeBracket:
    """One age range: a target value, and the age at which it starts.

    It runs up to the next bracket's start; the top bracket is open-ended.
    """

    from_age: int
    label: str


def check_age_brackets(brackets: Sequence[AgeBracket]) -> None:
    """Raise ValueError, with a message for the organiser, unless these brackets can make a rule."""
    if not brackets:
        raise ValueError(_("There must be at least one age range"))
    if any(bracket.from_age < 0 for bracket in brackets):
        raise ValueError(_("An age range cannot start below zero"))
    if len({bracket.from_age for bracket in brackets}) != len(brackets):
        raise ValueError(_("Two age ranges cannot start at the same age"))
    labels = [bracket.label for bracket in brackets]
    if any(not label.strip() for label in labels):
        raise ValueError(_("Every age range needs a target value"))
    if len(set(labels)) != len(labels):
        raise ValueError(_("Each target value can only be one age range"))


@dataclass(frozen=True)
class AgeBracketRule:
    """Buckets an age into the target's own values, as of a fixed date.

    ``as_of_date`` is required and never "today": a derived value must not
    depend on when derivation happened to run. Ages below the lowest bracket
    take the fallback, so a target with no "under 16" value counts the too
    young as unknown.
    """

    as_of_date: date
    brackets: tuple[AgeBracket, ...]
    fallback: str = DEFAULT_FALLBACK

    def __post_init__(self) -> None:
        object.__setattr__(self, "brackets", tuple(sorted(self.brackets, key=lambda bracket: bracket.from_age)))
        check_age_brackets(self.brackets)
        if not self.fallback.strip():
            raise ValueError("fallback cannot be blank")
        if self.fallback in self.labels():
            raise ValueError(_("An age range cannot use the value '%(value)s'", value=self.fallback))

    def labels(self) -> list[str]:
        """The bracket labels, youngest first."""
        return [bracket.label for bracket in self.brackets]

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
        label = self.fallback
        for bracket in self.brackets:
            if bracket.from_age > age:
                break
            label = bracket.label
        return label

    def to_config(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "brackets": [{"from_age": bracket.from_age, "label": bracket.label} for bracket in self.brackets],
            "fallback": self.fallback,
        }

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "AgeBracketRule":
        raw_date = config.get("as_of_date")
        if not raw_date:
            raise ValueError("as_of_date is required in an age bracket config")
        raw_brackets = config.get("brackets")
        if not raw_brackets:
            raise ValueError("brackets are required in an age bracket config")
        return cls(
            as_of_date=date.fromisoformat(raw_date),
            brackets=tuple(AgeBracket(from_age=int(b["from_age"]), label=str(b["label"])) for b in raw_brackets),
            fallback=config.get("fallback", DEFAULT_FALLBACK),
        )


@dataclass(frozen=True)
class AgeBracketMatch:
    """What could be worked out about the age each target value starts at.

    ``from_ages`` holds every value that could be placed. ``problem`` is empty
    when every value was placed and the ranges fit together; otherwise it says
    why they don't, in words an organiser can act on.
    """

    from_ages: dict[str, int]
    problem: str = ""


_WHOLE_NUMBER = re.compile(r"\d+")


def match_age_brackets(labels: list[str]) -> AgeBracketMatch:
    """Work out the age each target value starts at, from the numbers in it.

    A value with two numbers is a range ("16-29", "16 to 29", "16-29 év").
    A value with one number is an open end, and its position decides which:
    at or below the lowest range's start it is the bottom ("under 16", "<16"),
    and at the highest range's end or one above it is the top ("60+", ">59",
    "over 59"). Without a top value, the highest range is open-ended. Reading
    position rather than words means no keyword list, in any language.
    """
    ranges: list[tuple[str, int, int]] = []
    singles: list[tuple[str, int]] = []
    unplaced = False
    for label in labels:
        numbers = [int(number) for number in _WHOLE_NUMBER.findall(label)]
        if len(numbers) == 2 and numbers[0] <= numbers[1]:
            ranges.append((label, numbers[0], numbers[1]))
        elif len(numbers) == 1:
            singles.append((label, numbers[0]))
        else:
            unplaced = True
    if not ranges:
        return AgeBracketMatch(from_ages={}, problem=_age_match_generic_problem())

    ranges.sort(key=lambda entry: entry[1])
    from_ages = {label: start for label, start, _end in ranges}
    problem = _range_problem(ranges)

    lowest_start = ranges[0][1]
    highest_end = ranges[-1][2]
    bottoms = [label for label, number in singles if lowest_start > 0 and number <= lowest_start]
    tops = [label for label, number in singles if number in (highest_end, highest_end + 1)]
    if len(bottoms) == 1:
        from_ages[bottoms[0]] = 0
    if len(tops) == 1 and tops[0] not in from_ages:
        from_ages[tops[0]] = highest_end + 1
    if unplaced or len(from_ages) < len(labels):
        problem = problem or _age_match_generic_problem()
    return AgeBracketMatch(from_ages=from_ages, problem=problem)


def _range_problem(ranges: list[tuple[str, int, int]]) -> str:
    for (_label, _start, previous_end), (_next_label, start, _end) in pairwise(ranges):
        if start > previous_end + 1:
            if start == previous_end + 2:
                return _("The target values leave out age %(age)s", age=previous_end + 1)
            return _("The target values leave out ages %(first)s to %(last)s", first=previous_end + 1, last=start - 1)
        if start <= previous_end:
            return _("Age %(age)s is in more than one target value", age=start)
    return ""


def _age_match_generic_problem() -> str:
    return _(
        "Could not work out age ranges from the target values. Enter the age each one starts at, "
        "or change the target values to look like 16-29, 30-44, 45-59, 60+."
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

    Age brackets carry their own labels (the target's values); mapping rules take the organiser's
    declared output values (a small mapping can fall back to the distinct
    values in its table). The fallback is always appended so the value
    round-trips through the edit form, export and target counts.
    """
    if isinstance(rule, AgeBracketRule):
        values = rule.labels()
    elif isinstance(rule, SmallMappingRule):
        values = declared_outputs if declared_outputs is not None else list(dict.fromkeys(rule.mapping.values()))
    else:
        if declared_outputs is None:
            raise ValueError("declared_outputs is required for a large mapping rule")
        values = declared_outputs
    if rule.fallback not in values:
        values = [*values, rule.fallback]
    return [ChoiceOption(value=value) for value in dict.fromkeys(values)]
