"""ABOUTME: Shared helper functions for relating target categories to respondent data.
ABOUTME: Used by both backoffice targets and legacy targets blueprints."""

import uuid

from opendlp import bootstrap
from opendlp.service_layer.respondent_service import (
    get_respondent_attribute_columns,
    get_respondent_attribute_value_counts,
)

# When looking at respondent data and choosing columns which are reasonable to use
# as target categories, we want columns with not too many distinct values - as every distinct
# value needs a category value with min and max values. This can be quite a few - sometimes
# we have more than 10 regions. But it is rare for the number of values for a single target
# category to be over 20, so we use this as a rule of thumb for which columns we suggest as
# target categories.
MAX_DISTINCT_VALUES_FOR_AUTO_ADD = 20


def get_assembly_respondent_attribute_columns(assembly_id: uuid.UUID) -> list[str]:
    """Get respondent attribute columns for an assembly."""
    uow = bootstrap.bootstrap()
    with uow:
        return get_respondent_attribute_columns(uow, assembly_id)


def get_respondent_counts_for_category(
    assembly_id: uuid.UUID,
    category_name: str,
    attribute_columns: list[str],
) -> dict[str, int] | None:
    """Get respondent value counts for a category if its name matches a respondent attribute column.

    Uses case-insensitive matching. Returns None if no matching column found.
    """
    columns_lower = {col.lower(): col for col in attribute_columns}
    matched_col = columns_lower.get(category_name.lower())
    if matched_col is None:
        return None
    uow = bootstrap.bootstrap()
    with uow:
        return get_respondent_attribute_value_counts(uow, assembly_id, matched_col)


def get_column_distinct_counts(
    assembly_id: uuid.UUID,
    attribute_columns: list[str],
) -> dict[str, int]:
    """Get the number of distinct values for each respondent attribute column."""
    counts: dict[str, int] = {}
    uow = bootstrap.bootstrap()
    with uow:
        for col in attribute_columns:
            value_counts = get_respondent_attribute_value_counts(uow, assembly_id, col)
            counts[col] = len(value_counts)
    return counts


def build_respondent_counts(
    assembly_id: uuid.UUID,
    target_categories: list,
    attribute_columns: list[str],
) -> dict[str, dict[str, int]]:
    """Build respondent value counts for each target category that matches a respondent attribute."""
    respondent_counts: dict[str, dict[str, int]] = {}
    for category in target_categories:
        counts = get_respondent_counts_for_category(assembly_id, category.name, attribute_columns)
        if counts is not None:
            respondent_counts[category.name] = counts
    return respondent_counts
