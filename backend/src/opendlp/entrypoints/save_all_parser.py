"""ABOUTME: Parses the bulk targets edit form into service-layer edit dataclasses.
ABOUTME: WTForms models one form per object, which does not fit a page of many categories."""

import re
import uuid
from typing import Any

from opendlp.service_layer.target_service import TargetCategoryEdit, TargetValueEdit
from opendlp.translations import gettext as _

# cat[<category_id>][name] and cat[<category_id>][values][<value_id>][percentage]
CATEGORY_FIELD = re.compile(r"^cat\[([0-9a-fA-F-]{36})\]\[(name|comment|source_url)\]$")
VALUE_FIELD = re.compile(r"^cat\[([0-9a-fA-F-]{36})\]\[values\]\[([0-9a-fA-F-]{36}|new-\d+)\]\[(\w+)\]$")

VALUE_FIELDS = ("value", "percentage", "min", "max", "comment")


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


def parse_save_all_targets(form_data: Any) -> tuple[list[TargetCategoryEdit], list[str]]:
    """Turn a submitted bulk-edit form into edit dataclasses.

    Returns the edits and a list of already-translated error messages. Field names
    that do not match the expected shape are ignored rather than rejected: the form
    also carries the CSRF token and whatever else the page needs.
    """
    errors: list[str] = []
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

    edits = []
    for category_id, fields in categories.items():
        value_edits = []
        for (owner, value_id), cells in values.items():
            if owner != category_id:
                continue
            name = cells.get("value", "").strip()
            if not name:
                errors.append(_("Every target value needs a name"))
                continue
            value_edits.append(
                TargetValueEdit(
                    value=name,
                    value_id=None if value_id.startswith("new-") else uuid.UUID(value_id),
                    percentage=_parse_number(cells.get("percentage", ""), "percentage", errors),
                    min=_parse_number(cells.get("min", ""), "min", errors),
                    max=_parse_number(cells.get("max", ""), "max", errors),
                    comment=cells.get("comment", "").strip(),
                )
            )

        edits.append(
            TargetCategoryEdit(
                category_id=uuid.UUID(category_id),
                name=fields.get("name", "").strip(),
                comment=fields.get("comment", "").strip(),
                source_url=fields.get("source_url", "").strip(),
                values=value_edits,
            )
        )

    return edits, errors
