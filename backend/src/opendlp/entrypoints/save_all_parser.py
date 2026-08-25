"""ABOUTME: Parses the bulk targets edit form into service-layer edit dataclasses.
ABOUTME: WTForms models one form per object, which does not fit a page of many categories."""

import re
import uuid
from typing import Any

from opendlp.service_layer.target_service import TargetCategoryEdit, TargetValueEdit
from opendlp.translations import gettext as _

# cat[<category_id>][name] and cat[<category_id>][values][<value_id>][percentage]
CATEGORY_FIELD = re.compile(r"^cat\[([0-9a-fA-F-]{36})\]\[(name|comment|source_url|deleted|sort_order)\]$")
VALUE_FIELD = re.compile(r"^cat\[([0-9a-fA-F-]{36})\]\[values\]\[([0-9a-fA-F-]{36}|new-\d+)\]\[(\w+)\]$")

VALUE_FIELDS = ("value", "percentage", "min", "max", "comment", "deleted", "relink")

TRUTHY = frozenset({"true", "1", "on", "yes"})


def _is_true(raw: str) -> bool:
    """Whether a checkbox-style hidden field says yes."""
    return raw.strip().lower() in TRUTHY


def _parse_number(raw: str, field: str, errors: list[str]) -> Any:
    """Parse an optional numeric cell, recording a message rather than raising."""
    text = raw.strip()
    if not text:
        return None
    try:
        return float(text) if field == "percentage" else int(text)
    except ValueError:
        errors.append(_('"%(value)s" is not a valid %(field)s', value=text[:40], field=field))
        return None


def _collect_fields(form_data: Any) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, str]]]:
    """Split the raw form into per-category and per-value cells, keyed by id."""
    categories: dict[str, dict[str, Any]] = {}
    values: dict[tuple[str, str], dict[str, str]] = {}

    for key in form_data:
        category_match = CATEGORY_FIELD.match(key)
        if category_match:
            category_id, field = category_match.groups()
            categories.setdefault(category_id, {})[field] = form_data[key]
            continue

        value_match = VALUE_FIELD.match(key)
        if value_match:
            category_id, value_id, field = value_match.groups()
            if field in VALUE_FIELDS:
                categories.setdefault(category_id, {})
                values.setdefault((category_id, value_id), {})[field] = form_data[key]

    return categories, values


def _value_edit(value_id: str, cells: dict[str, str], errors: list[str]) -> TargetValueEdit | None:
    """Build one value edit, or None when the row is unusable."""
    deleted = _is_true(cells.get("deleted", ""))
    name = cells.get("value", "").strip()
    if not name and not deleted:
        errors.append(_("Every target value needs a name"))
        return None

    return TargetValueEdit(
        value=name,
        value_id=None if value_id.startswith("new-") else uuid.UUID(value_id),
        percentage=_parse_number(cells.get("percentage", ""), "percentage", errors),
        min=_parse_number(cells.get("min", ""), "min", errors),
        max=_parse_number(cells.get("max", ""), "max", errors),
        comment=cells.get("comment", "").strip(),
        deleted=deleted,
        relink=_is_true(cells.get("relink", "")),
    )


def parse_save_all_targets(form_data: Any) -> tuple[list[TargetCategoryEdit], list[str]]:
    """Turn a submitted bulk-edit form into edit dataclasses.

    Returns the edits and a list of already-translated error messages. Field names
    that do not match the expected shape are ignored rather than rejected: the form
    also carries the CSRF token and whatever else the page needs.
    """
    errors: list[str] = []
    categories, values = _collect_fields(form_data)

    edits = []
    for category_id, fields in categories.items():
        deleted = _is_true(fields.get("deleted", ""))
        # A category on its way out is not held to its own or its values' rules.
        value_edits = []
        if not deleted:
            for (owner, value_id), cells in values.items():
                if owner != category_id:
                    continue
                edit = _value_edit(value_id, cells, errors)
                if edit is not None:
                    value_edits.append(edit)

        edits.append(
            TargetCategoryEdit(
                category_id=uuid.UUID(category_id),
                name=fields.get("name", "").strip(),
                comment=fields.get("comment", "").strip(),
                source_url=fields.get("source_url", "").strip(),
                values=value_edits,
                deleted=deleted,
                sort_order=_parse_number(fields.get("sort_order", ""), "sort order", errors),
            )
        )

    return edits, errors
