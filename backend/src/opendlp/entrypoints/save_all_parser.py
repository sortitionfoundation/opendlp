"""ABOUTME: Parses the bulk targets edit form into service-layer edit dataclasses.
ABOUTME: Also maps a submission back to the shape the template renders, for redisplay after an error."""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from opendlp.service_layer.target_service import TargetCategoryEdit, TargetEditError, TargetValueEdit
from opendlp.translations import gettext as _

# cat[<category_id>][name] and cat[<category_id>][values][<value_id>][percentage].
# Either id may be "new-<n>" instead of a UUID: something the user added in the
# form, which does not exist until the save goes through.
ID = r"[0-9a-fA-F-]{36}|new-\d+"
CATEGORY_FIELD = re.compile(rf"^cat\[({ID})\]\[(name|comment|source_url|deleted|sort_order)\]$")
VALUE_FIELD = re.compile(rf"^cat\[({ID})\]\[values\]\[({ID})\]\[(\w+)\]$")

VALUE_FIELDS = ("value", "percentage", "min", "max", "comment", "deleted", "relink", "minmax_manual")

TRUTHY = frozenset({"true", "1", "on", "yes"})


def _is_true(raw: str) -> bool:
    """Whether a checkbox-style hidden field says yes."""
    return raw.strip().lower() in TRUTHY


def _submitted_id(raw: str) -> uuid.UUID | None:
    """The id of a submitted category or value, or None when it is a new one."""
    return None if raw.startswith("new-") else uuid.UUID(raw)


def _parse_number(
    raw: str,
    field: str,
    errors: list[TargetEditError],
    category_form_id: str = "",
    value_form_id: str = "",
) -> Any:
    """Parse an optional numeric cell, recording a message rather than raising."""
    text = raw.strip()
    if not text:
        return None
    try:
        return float(text) if field == "percentage" else int(text)
    except ValueError:
        errors.append(
            TargetEditError(
                _('"%(value)s" is not a valid %(field)s', value=text[:40], field=field),
                category_form_id,
                value_form_id,
                field,
            )
        )
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


def _value_edit(
    category_id: str,
    value_id: str,
    cells: dict[str, str],
    errors: list[TargetEditError],
) -> TargetValueEdit:
    """Build one value edit, recording anything wrong with the cells it came from.

    A bad row still produces an edit. Dropping it would take the row off the page
    when the form is redisplayed, which loses the very thing the user has to fix.
    """
    deleted = _is_true(cells.get("deleted", ""))
    name = cells.get("value", "").strip()
    if not name and not deleted:
        errors.append(TargetEditError(_("Every target value needs a name"), category_id, value_id, "value"))

    # A row on its way out is not worth complaining about: `_value_problem`
    # skips deleted rows too, and without this a stale number in a row the user
    # has already removed would block the whole save.
    number_errors = [] if deleted else errors

    return TargetValueEdit(
        value=name,
        value_id=_submitted_id(value_id),
        percentage=_parse_number(cells.get("percentage", ""), "percentage", number_errors, category_id, value_id),
        min=_parse_number(cells.get("min", ""), "min", number_errors, category_id, value_id),
        max=_parse_number(cells.get("max", ""), "max", number_errors, category_id, value_id),
        comment=cells.get("comment", "").strip(),
        deleted=deleted,
        relink=_is_true(cells.get("relink", "")),
        form_id=value_id,
    )


def parse_save_all_targets(form_data: Any) -> tuple[list[TargetCategoryEdit], list[TargetEditError]]:
    """Turn a submitted bulk-edit form into edit dataclasses.

    Returns the edits and every error found, each tied to the field that caused
    it. Field names that do not match the expected shape are ignored rather than
    rejected: the form also carries the CSRF token and whatever else the page needs.

    A category with a problem still produces an edit, so the redisplayed form has
    every row the user submitted, including the broken ones.
    """
    errors: list[TargetEditError] = []
    categories, values = _collect_fields(form_data)

    edits = []
    for category_id, fields in categories.items():
        deleted = _is_true(fields.get("deleted", ""))
        # A category on its way out is not held to its own or its values' rules.
        value_edits = []
        if not deleted:
            if not fields.get("name", "").strip():
                errors.append(TargetEditError(_("Every target needs a name"), category_id, field="name"))
            for (owner, value_id), cells in values.items():
                if owner != category_id:
                    continue
                value_edits.append(_value_edit(category_id, value_id, cells, errors))

        edits.append(
            TargetCategoryEdit(
                category_id=_submitted_id(category_id),
                name=fields.get("name", "").strip(),
                comment=fields.get("comment", "").strip(),
                source_url=fields.get("source_url", "").strip(),
                values=value_edits,
                deleted=deleted,
                sort_order=_parse_number(fields.get("sort_order", ""), "sort_order", errors, category_id),
                form_id=category_id,
            )
        )

    return edits, errors


@dataclass
class PendingValue:
    """One submitted value row, shaped like a `TargetValue` for the bulk form.

    Built from the raw cells rather than from the parsed edit, so a redisplayed
    form shows exactly what was typed - including a number the parser could not
    read, which is precisely the one the user has to go back and correct.
    """

    value_id: str
    value: str = ""
    percentage_target: str = ""
    min: str = ""
    max: str = ""
    comment: str = ""
    deleted: bool = False
    relink: bool = False
    # Carried through the form only so a redisplayed row still offers the re-link
    # button. `save_all_targets` works this out from the stored value and the
    # submitted numbers, and never reads it from here.
    minmax_manual: bool = False


@dataclass
class PendingCategory:
    """One submitted category, shaped like a `TargetCategory` for the bulk form."""

    id: str
    name: str = ""
    comment: str = ""
    source_url: str = ""
    sort_order: str = ""
    values: list[PendingValue] = field(default_factory=list)
    deleted: bool = False


def pending_categories(form_data: Any) -> list[PendingCategory]:
    """Rebuild the submitted form as the objects the bulk edit template renders."""
    categories, values = _collect_fields(form_data)

    pending = []
    for category_id, fields in categories.items():
        rows = [
            PendingValue(
                value_id=value_id,
                value=cells.get("value", ""),
                percentage_target=cells.get("percentage", "").strip(),
                min=cells.get("min", "").strip(),
                max=cells.get("max", "").strip(),
                comment=cells.get("comment", ""),
                deleted=_is_true(cells.get("deleted", "")),
                relink=_is_true(cells.get("relink", "")),
                minmax_manual=_is_true(cells.get("minmax_manual", "")),
            )
            for (owner, value_id), cells in values.items()
            if owner == category_id
        ]
        pending.append(
            PendingCategory(
                id=category_id,
                name=fields.get("name", ""),
                comment=fields.get("comment", ""),
                source_url=fields.get("source_url", ""),
                sort_order=fields.get("sort_order", "").strip(),
                values=rows,
                deleted=_is_true(fields.get("deleted", "")),
            )
        )
    return pending


def _field_key(error: TargetEditError) -> str:
    """The form field name an error belongs against."""
    key = f"cat[{error.category_form_id}]"
    if error.value_form_id:
        key += f"[values][{error.value_form_id}]"
    if error.field:
        key += f"[{error.field}]"
    return key


def errors_by_field(errors: list[TargetEditError]) -> dict[str, str]:
    """Group error messages by form field name, as the template looks them up.

    Several messages against one field are joined with newlines: the input
    component renders its error with `white-space: pre-line`, so they stack.
    """
    grouped: dict[str, list[str]] = {}
    for error in errors:
        grouped.setdefault(_field_key(error), []).append(error.message)
    return {key: "\n".join(messages) for key, messages in grouped.items()}
