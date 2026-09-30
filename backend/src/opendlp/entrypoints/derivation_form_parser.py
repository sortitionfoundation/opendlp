"""ABOUTME: Parsers turning the derivation set-up forms into domain rules
ABOUTME: Used by the target data sources blueprint; every ValueError carries a message for the organiser"""

from datetime import UTC, date, datetime
from itertools import zip_longest
from typing import Any

from opendlp.domain.respondent_derivation import (
    AgeBracket,
    AgeBracketRule,
    SmallMappingRule,
    check_age_brackets,
)
from opendlp.domain.respondent_field_schema import ChoiceOption, duplicate_option_value
from opendlp.translations import gettext as _


def parse_as_of_date(values: dict[str, Any]) -> date:
    """The date respondent age is calculated on, from its day, month and year inputs. Raises ValueError."""
    try:
        as_of = date(int(values["as_of_year"]), int(values["as_of_month"]), int(values["as_of_day"]))
    except (TypeError, ValueError):
        raise ValueError(_("Enter a valid date to calculate respondent age on (day, month and year)")) from None
    # The as-of date is usually the first assembly date, so it is always near
    # today. A year outside this window is a typo, and a silent one: the
    # brackets it produces look plausible and put everyone in the fallback.
    this_year = datetime.now(UTC).date().year
    if not (this_year - 1 <= as_of.year <= this_year + 1):
        raise ValueError(
            _(
                "The year to calculate respondent age on must be between %(low)d and %(high)d",
                low=this_year - 1,
                high=this_year + 1,
            )
        )
    return as_of


def parse_age_brackets(values: dict[str, Any]) -> tuple[AgeBracket, ...]:
    """One bracket per target value, from the paired ``bracket_label`` / ``bracket_from`` lists. Raises ValueError.

    Every target value needs the age it starts at: an age rule can only ever
    produce the values it has a bracket for.
    """
    brackets = []
    for label, raw_from in zip_longest(values["bracket_label"], values["bracket_from"], fillvalue=""):
        if not raw_from.strip():
            raise ValueError(_("Enter the age where '%(value)s' starts", value=label))
        try:
            from_age = int(raw_from.strip())
        except ValueError:
            raise ValueError(_("The age where '%(value)s' starts must be a whole number", value=label)) from None
        brackets.append(AgeBracket(from_age=from_age, label=label))
    check_age_brackets(brackets)
    return tuple(brackets)


def parse_age_rule(values: dict[str, Any]) -> AgeBracketRule:
    """Build an AgeBracketRule from the modal's age-config values. Raises ValueError."""
    brackets = parse_age_brackets(values)
    return AgeBracketRule(as_of_date=parse_as_of_date(values), brackets=brackets)


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


def parse_answer_options(values: dict[str, Any]) -> list[ChoiceOption]:
    """The answers typed into the mapping table, as the options of the question being created.

    Blank rows are dropped. Raises ValueError with a message for the organiser
    when nothing is left, or when an answer is repeated.
    """
    options = [ChoiceOption(value=source.strip()) for source in values["map_source"] if source.strip()]
    if not options:
        raise ValueError(_("Enter at least one answer"))
    duplicate = duplicate_option_value(options)
    if duplicate:
        raise ValueError(_("Answer values must be different: '%(value)s' appears more than once", value=duplicate))
    return options
