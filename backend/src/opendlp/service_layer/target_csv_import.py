"""ABOUTME: Importing target categories and values from a CSV or spreadsheet
ABOUTME: Parsing the extra columns, deriving percentages, and turning it all into TargetCategory objects"""

from __future__ import annotations

import csv as csv_module
from io import StringIO
from typing import TYPE_CHECKING, NamedTuple

from sortition_algorithms.features import read_in_features

from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.translations import gettext as _

from .constants import SORT_ORDER_STEP
from .exceptions import InvalidSelection
from .target_service import _load_user_and_assembly

if TYPE_CHECKING:
    import uuid

    from .unit_of_work import AbstractUnitOfWork


WARNING_VALUE_CHARS = 60


class TargetImportResult(NamedTuple):
    """Imported categories, plus non-fatal warnings worth showing the user."""

    categories: list[TargetCategory]
    warnings: list[str]


VALUE_PERCENTAGE_COLUMN = "percentage"


VALUE_COMMENT_COLUMN = "comment"


CATEGORY_COMMENT_COLUMN = "category_comment"


CATEGORY_SOURCE_URL_COLUMN = "source_url"


def _truncate(text: str) -> str:
    if len(text) <= WARNING_VALUE_CHARS:
        return text
    return text[: WARNING_VALUE_CHARS - 1] + "\u2026"


def _cell(row: dict[str, str], columns: dict[str, str], name: str) -> str:
    """Read one of our optional columns from a raw CSV row, case-insensitively."""
    header = columns.get(name)
    if header is None:
        return ""
    return (row.get(header) or "").strip()


def _parse_percentage(raw: str, feature: str, value: str) -> float | None:
    if not raw:
        return None
    try:
        percentage = float(raw.rstrip("%").strip())
    except ValueError as e:
        raise InvalidSelection(f"Invalid percentage '{raw}' for {feature} / {value}") from e
    if not 0 <= percentage <= 100:
        raise InvalidSelection(f"Percentage '{raw}' for {feature} / {value} must be between 0 and 100")
    return percentage


def _collect_csv_extras(
    body: list[dict[str, str]],
    columns: dict[str, str],
    feature_col: str,
    value_col: str,
) -> tuple[dict[tuple[str, str], dict[str, str]], dict[str, dict[str, list[str]]]]:
    """Index our optional columns out of the raw rows.

    Value-level extras are keyed by (feature, value). Category-level extras are
    keyed by feature and keep *every* distinct non-empty value seen, so a
    disagreement between rows can be reported rather than silently resolved.
    """
    value_extras: dict[tuple[str, str], dict[str, str]] = {}
    category_extras: dict[str, dict[str, list[str]]] = {}

    for row in body:
        feature = (row.get(feature_col) or "").strip()
        value = (row.get(value_col) or "").strip()
        if not feature or not value:
            continue

        value_extras[(feature, value)] = {
            VALUE_PERCENTAGE_COLUMN: _cell(row, columns, VALUE_PERCENTAGE_COLUMN),
            VALUE_COMMENT_COLUMN: _cell(row, columns, VALUE_COMMENT_COLUMN),
        }

        seen = category_extras.setdefault(feature, {CATEGORY_COMMENT_COLUMN: [], CATEGORY_SOURCE_URL_COLUMN: []})
        for column in (CATEGORY_COMMENT_COLUMN, CATEGORY_SOURCE_URL_COLUMN):
            cell = _cell(row, columns, column)
            if cell and cell not in seen[column]:
                seen[column].append(cell)

    return value_extras, category_extras


def _resolve_category_column(
    feature: str,
    column: str,
    category_extras: dict[str, dict[str, list[str]]],
    warnings: list[str],
) -> str:
    """First non-empty value wins; a disagreement between rows is reported."""
    seen = category_extras.get(feature, {}).get(column, [])
    if not seen:
        return ""
    if len(seen) > 1:
        warnings.append(
            _(
                'Rows for "%(category)s" gave different values for %(column)s. '
                'Using "%(used)s" and ignoring %(count)s other value(s).',
                category=feature,
                column=column,
                used=_truncate(seen[0]),
                count=len(seen) - 1,
            )
        )
    return seen[0]


def import_targets_from_csv(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    csv_content: str,
    replace_existing: bool = False,
) -> TargetImportResult:
    """
    Import target categories from CSV using sortition-algorithms library.

    CSV format matches sortition-algorithms feature files with columns:
    feature, value, min, max, min_flex, max_flex

    Four optional columns are read by us rather than the library, which ignores
    headers it does not recognise: `percentage` and `comment` per value,
    `category_comment` and `source_url` per category.

    Every imported value is marked `minmax_manual`. The CSV format makes min and
    max mandatory, so imported numbers are always deliberate; leaving the link
    intact would let a later change to number_to_select silently narrow every
    imported range from the derived percentage.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = _load_user_and_assembly(uow, user_id, assembly_id, "import targets")

    # Parse and validate CSV using sortition-algorithms
    # Note: read_in_features() already calls set_default_max_flex() and check_min_max()
    csv_file = StringIO(csv_content)
    reader = csv_module.DictReader(csv_file)

    if not reader.fieldnames:
        raise InvalidSelection("CSV file is empty or malformed")

    headers = list(reader.fieldnames)
    body = list(reader)

    try:
        feature_collection, feature_col, value_col = read_in_features(headers, body)
    except Exception as e:
        raise InvalidSelection(f"Failed to parse CSV: {e!s}") from e

    columns = {h.strip().lower(): h for h in headers}
    value_extras, category_extras = _collect_csv_extras(body, columns, feature_col, value_col)
    warnings: list[str] = []

    # Replace existing if requested
    if replace_existing:
        uow.target_categories.delete_all_for_assembly(assembly_id)

    # Convert to TargetCategory objects
    categories = []
    for idx, (feature_name, feature_values) in enumerate(feature_collection.items(), start=1):
        # The domain refuses an over-long comment or a URL with no scheme with a
        # bare ValueError. Uncaught it reaches the route's `except Exception`,
        # which tells the user "an unexpected error occurred" and logs a stack
        # trace - for what is an ordinary mistake in their spreadsheet.
        try:
            category = TargetCategory(
                assembly_id=assembly_id,
                name=feature_name,
                sort_order=idx * SORT_ORDER_STEP,
                comment=_resolve_category_column(feature_name, CATEGORY_COMMENT_COLUMN, category_extras, warnings),
                source_url=_resolve_category_column(
                    feature_name, CATEGORY_SOURCE_URL_COLUMN, category_extras, warnings
                ),
            )
        except ValueError as e:
            raise InvalidSelection(f"Invalid data for {feature_name}: {e}") from e

        # Add target values
        for value_name, fv_minmax in feature_values.items():
            extras = value_extras.get((feature_name, value_name), {})
            try:
                target_val = TargetValue(
                    value=value_name,
                    min=fv_minmax.min,
                    max=fv_minmax.max,
                    min_flex=fv_minmax.min_flex,
                    max_flex=fv_minmax.max_flex,
                    percentage_target=_parse_percentage(
                        extras.get(VALUE_PERCENTAGE_COLUMN, ""), feature_name, value_name
                    ),
                    comment=extras.get(VALUE_COMMENT_COLUMN, ""),
                    minmax_manual=True,
                )
            except ValueError as e:
                raise InvalidSelection(f"Invalid data for {feature_name} / {value_name}: {e}") from e
            category.add_value(target_val)

        _fill_missing_percentages(category, assembly.number_to_select)

        uow.target_categories.add(category)
        categories.append(category)

    return TargetImportResult(
        categories=[c.create_detached_copy() for c in categories],
        warnings=warnings,
    )


def _clamp_percentage(percentage: float) -> float:
    """Hold a derived percentage inside the range the domain accepts."""
    return round(min(max(percentage, 0.0), 100.0), 1)


def _fill_missing_percentages(category: TargetCategory, number_to_select: int) -> None:
    """Derive percentages for imported values that did not carry one.

    With a seat count, use midpoint/number_to_select - deliberately the same
    formula the selection report uses, so an imported percentage and the report
    agree by construction, and a CSV whose midpoints do not sum to the assembly
    size still trips the sum-to-100 warning.

    Without one, normalise within the category instead, which needs no seat count
    but always totals 100 and so can never trip that warning.

    Both branches clamp to 0-100. A CSV whose midpoint exceeds number_to_select -
    say min=50, max=60 against 10 seats - otherwise derives a percentage the
    domain rejects, and TargetValue validates on load as well as on construction,
    so the row would be written once and then raise on every read after that.
    """
    missing = [v for v in category.values if v.percentage_target is None]
    if not missing:
        return

    if number_to_select > 0:
        for target_value in missing:
            target_value.percentage_target = _clamp_percentage(
                (target_value.min + target_value.max) / 2 / number_to_select * 100
            )
        return

    denominator = sum(v.min + v.max for v in category.values)
    if denominator == 0:
        return
    for target_value in missing:
        target_value.percentage_target = _clamp_percentage((target_value.min + target_value.max) / denominator * 100)
