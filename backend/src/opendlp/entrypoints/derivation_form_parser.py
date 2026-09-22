"""ABOUTME: Parsers turning the derivation set-up forms into domain rules
ABOUTME: Used by the target data sources blueprint; every ValueError carries a message for the organiser"""

from datetime import UTC, date, datetime
from itertools import zip_longest
from typing import Any

from opendlp.domain.respondent_derivation import (
    AgeBracketRule,
    SmallMappingRule,
    age_brackets_from_labels,
)
from opendlp.translations import gettext as _


def parse_boundaries(raw: str) -> tuple[int, ...]:
    """A comma-separated boundaries string as sorted unique ints. Raises ValueError."""
    parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    try:
        return tuple(sorted({int(p) for p in parts}))
    except ValueError:
        raise ValueError(_("Boundaries must be whole numbers separated by commas, e.g. 25, 40, 60")) from None


def parse_age_rule(values: dict[str, Any]) -> AgeBracketRule:
    """Build an AgeBracketRule from the modal's age-config values. Raises ValueError."""
    try:
        as_of = date(int(values["as_of_year"]), int(values["as_of_month"]), int(values["as_of_day"]))
    except (TypeError, ValueError):
        raise ValueError(_("Enter a valid as-of date (day, month and year)")) from None
    # The as-of date is usually the first assembly date, so it is always near
    # today. A year outside this window is a typo, and a silent one: the
    # brackets it produces look plausible and put everyone in the fallback.
    this_year = datetime.now(UTC).date().year
    if not (this_year - 1 <= as_of.year <= this_year + 1):
        raise ValueError(
            _("The as-of year must be between %(low)d and %(high)d", low=this_year - 1, high=this_year + 1)
        )
    try:
        min_age = int(values["min_age"] or 16)
        max_age = int(values["max_age"] or 100)
    except ValueError:
        raise ValueError(_("Minimum and maximum age must be whole numbers")) from None
    return AgeBracketRule(
        as_of_date=as_of,
        min_age=min_age,
        max_age=max_age,
        boundaries=parse_boundaries(values["boundaries"]),
    )


def parse_small_mapping_rule(values: dict[str, Any]) -> SmallMappingRule:
    """Build a SmallMappingRule from the modal's mapping-table rows. Raises ValueError.

    A row whose target select was left on the fall-back entry is simply not in
    the mapping — those source values fall back to UNKNOWN at derivation time.
    """
    mapping = {
        source.strip(): target.strip()
        for source, target in zip_longest(values["map_source"], values["map_target"], fillvalue="")
        if source.strip() and target.strip()
    }
    if not mapping:
        raise ValueError(_("Map at least one answer to a target value"))
    return SmallMappingRule(mapping=mapping)


def age_prefill_from_target(target_values: list[str]) -> dict[str, str] | None:
    """min/max/boundaries form values parsed from "16-24"-style target value names.

    Returns None when the target's values don't look like a complete bracket
    set — the caller leaves the inputs blank for the user to fill in (Q9).
    """
    brackets = age_brackets_from_labels(target_values)
    if brackets is None:
        return None
    min_age, max_age, boundaries = brackets
    return {
        "min_age": str(min_age),
        "max_age": str(max_age),
        "boundaries": ", ".join(str(b) for b in boundaries),
    }
