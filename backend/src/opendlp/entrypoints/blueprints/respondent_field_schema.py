"""ABOUTME: Backoffice routes for managing a per-assembly respondent field schema
ABOUTME: Read-only schema rows plus an HTMX add/edit field modal; move, delete, initialise"""

import contextlib
import re
import uuid
from datetime import date
from itertools import zip_longest
from typing import Any

import structlog
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.domain.respondent_derivation import (
    DEFAULT_FALLBACK,
    AgeBracketRule,
    DerivationRule,
    LargeMappingRule,
    SmallMappingRule,
)
from opendlp.domain.respondent_field_schema import (
    CHOICE_TYPES,
    FIELD_TYPE_LABELS,
    GROUP_DISPLAY_ORDER,
    GROUP_LABELS,
    ChoiceOption,
    DerivationType,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    normalise_field_key,
)
from opendlp.entrypoints.scroll_utils import redirect_preserving_scroll
from opendlp.service_layer.assembly_service import (
    determine_data_source,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_tab_enabled_states,
)
from opendlp.service_layer.derivation_service import (
    MappingUploadReport,
    RecomputeReport,
    compatible_source_fields,
    create_derived_field,
    recompute_derived_field,
    update_derivation,
    upload_large_mapping,
)
from opendlp.service_layer.exceptions import (
    InsufficientPermissions,
    NotFoundError,
    ServiceLayerError,
)
from opendlp.service_layer.respondent_field_schema_service import (
    FieldDefinitionConflictError,
    FieldDefinitionNotFoundError,
    add_choice_option,
    add_field,
    delete_field,
    get_schema,
    get_schema_grouped,
    guess_field_types,
    initialise_empty_schema,
    remove_choice_option,
    reorder_group,
    update_choice_option,
    update_field,
)
from opendlp.service_layer.respondent_field_spec_service import build_field_spec
from opendlp.translations import gettext as _
from opendlp.translations import lazy_gettext as _l

respondent_field_schema_bp = Blueprint("respondent_field_schema", __name__)

logger = structlog.get_logger(__name__)


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _schema_page_redirect(assembly_id: uuid.UUID) -> ResponseReturnValue:
    # Preserve the submitting form's scroll position so saving a field, moving a
    # row, or editing an option doesn't bounce the user back to the top of the page.
    return redirect_preserving_scroll(url_for("respondent_field_schema.view_schema", assembly_id=assembly_id))


def _parse_group(raw: str | None) -> RespondentFieldGroup | None:
    """Parse a submitted group value; returns None if empty or unrecognised."""
    if not raw:
        return None
    try:
        return RespondentFieldGroup(raw)
    except ValueError:
        return None


def _parse_field_type(raw: str | None) -> FieldType | None:
    """Parse a submitted field_type value; returns None if empty or unrecognised."""
    if not raw:
        return None
    try:
        return FieldType(raw)
    except ValueError:
        return None


def _parse_on_registration_page(raw: str | None) -> FieldOnRegistrationPage | None:
    """Parse a submitted on_registration_page value; returns None if empty or unrecognised."""
    if not raw:
        return None
    try:
        return FieldOnRegistrationPage(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# The modal's user-facing type taxonomy.
#
# The modal offers a shorter menu than FieldType: LONGTEXT and BOOL_OR_NONE are
# excluded (no current use case outside CSV import), but a field that already
# has one of those types shows it as a selectable entry so editing never forces
# a type change. "free_text" fans out to TEXT/EMAIL/INTEGER via a sub-select
# and "choice" to CHOICE_RADIO/CHOICE_DROPDOWN.
# ---------------------------------------------------------------------------

_STANDARD_TYPE_CHOICES: list[dict[str, Any]] = [
    {"value": "bool", "label": FIELD_TYPE_LABELS[FieldType.BOOL]},
    {"value": "free_text", "label": FIELD_TYPE_LABELS[FieldType.TEXT]},
    {"value": "choice", "label": FIELD_TYPE_LABELS[FieldType.CHOICE_RADIO]},
    {"value": "date", "label": FIELD_TYPE_LABELS[FieldType.DATE]},
]

_LEGACY_TYPE_CHOICES: dict[FieldType, dict[str, Any]] = {
    FieldType.LONGTEXT: {"value": "longtext", "label": FIELD_TYPE_LABELS[FieldType.LONGTEXT]},
    FieldType.BOOL_OR_NONE: {"value": "bool_or_none", "label": FIELD_TYPE_LABELS[FieldType.BOOL_OR_NONE]},
}

_FREE_TEXT_SUBTYPES: dict[str, FieldType] = {
    "text": FieldType.TEXT,
    "email": FieldType.EMAIL,
    "integer": FieldType.INTEGER,
}

_CHOICE_STYLES: dict[str, FieldType] = {
    "choice_radio": FieldType.CHOICE_RADIO,
    "choice_dropdown": FieldType.CHOICE_DROPDOWN,
}


def _field_type_from_taxonomy(values: dict[str, Any]) -> FieldType:
    """Map the modal's type_choice/subtype/style values onto a FieldType."""
    type_choice = values["type_choice"]
    if type_choice == "bool":
        return FieldType.BOOL
    if type_choice == "free_text":
        return _FREE_TEXT_SUBTYPES.get(values["free_text_subtype"], FieldType.TEXT)
    if type_choice == "choice":
        return _CHOICE_STYLES.get(values["choice_style"], FieldType.CHOICE_RADIO)
    if type_choice == "date":
        return FieldType.DATE
    if type_choice == "longtext":
        return FieldType.LONGTEXT
    if type_choice == "bool_or_none":
        return FieldType.BOOL_OR_NONE
    return FieldType.TEXT


def _taxonomy_from_field_type(field_type: FieldType) -> dict[str, str]:
    """The modal taxonomy values that would produce ``field_type``."""
    values = {"type_choice": "free_text", "free_text_subtype": "text", "choice_style": "choice_radio"}
    if field_type == FieldType.BOOL:
        values["type_choice"] = "bool"
    elif field_type in (FieldType.TEXT, FieldType.EMAIL, FieldType.INTEGER):
        values["free_text_subtype"] = next(k for k, v in _FREE_TEXT_SUBTYPES.items() if v == field_type)
    elif field_type in CHOICE_TYPES:
        values["type_choice"] = "choice"
        values["choice_style"] = field_type.value
    elif field_type == FieldType.DATE:
        values["type_choice"] = "date"
    elif field_type in _LEGACY_TYPE_CHOICES:
        values["type_choice"] = _LEGACY_TYPE_CHOICES[field_type]["value"]
    return values


# ---------------------------------------------------------------------------
# Modal context builders — everything _field_modal.html needs to render.
# ---------------------------------------------------------------------------


def _modal_values_from_request(source: Any) -> dict[str, Any]:
    """Rebuild the modal form state from a submitted (or hx-included) form."""
    options = [
        {"value": value, "help_text": help_text}
        for value, help_text in zip_longest(source.getlist("option_value"), source.getlist("option_help"), fillvalue="")
    ]
    return {
        "label": source.get("label", ""),
        "field_key": source.get("field_key", ""),
        "type_choice": source.get("type_choice", "free_text"),
        "free_text_subtype": source.get("free_text_subtype", "text"),
        "choice_style": source.get("choice_style", "choice_radio"),
        "help_text": source.get("help_text", ""),
        "on_registration_page": source.get("on_registration_page", FieldOnRegistrationPage.YES_REQUIRED.value),
        "options": options,
        "target_name": source.get("target_name", ""),
        "derivation_method": source.get("derivation_method", DerivationType.AGE_BRACKET.value),
        "source_key": source.get("source_key", ""),
        "as_of_day": source.get("as_of_day", ""),
        "as_of_month": source.get("as_of_month", ""),
        "as_of_year": source.get("as_of_year", ""),
        "min_age": source.get("min_age", ""),
        "max_age": source.get("max_age", ""),
        "boundaries": source.get("boundaries", ""),
        "map_source": source.getlist("map_source"),
        "map_target": source.getlist("map_target"),
    }


def _modal_values_from_field(field: RespondentFieldDefinition) -> dict[str, Any]:
    """The modal form state for editing an existing field."""
    values = _default_modal_values()
    values.update({
        "label": field.label,
        "field_key": field.field_key,
        "help_text": field.help_text,
        "on_registration_page": field.on_registration_page.value,
        "options": [{"value": o.value, "help_text": o.help_text} for o in field.options or []],
    })
    values.update(_taxonomy_from_field_type(field.field_type))
    if field.is_derived:
        values["type_choice"] = "derived"
        values["derivation_method"] = field.derivation_type.value if field.derivation_type else ""
        values["source_key"] = (field.derived_from or [""])[0]
        values["target_name"] = field.field_key
        _seed_config_values(values, field)
    return values


def _seed_config_values(values: dict[str, Any], field: RespondentFieldDefinition) -> None:
    """Fill the method-config form values from a derived field's stored derivation_config."""
    config = field.derivation_config or {}
    if field.derivation_type == DerivationType.AGE_BRACKET:
        raw_date = config.get("as_of_date", "")
        if raw_date:
            year, month, day = raw_date.split("-")
            values.update({"as_of_year": year, "as_of_month": str(int(month)), "as_of_day": str(int(day))})
        values["min_age"] = str(config.get("min_age", 16))
        values["max_age"] = str(config.get("max_age", 100))
        values["boundaries"] = ", ".join(str(b) for b in config.get("boundaries", []))
    elif field.derivation_type == DerivationType.SMALL_MAPPING:
        mapping = config.get("mapping", {})
        values["map_source"] = list(mapping.keys())
        values["map_target"] = list(mapping.values())


def _default_modal_values() -> dict[str, Any]:
    return {
        "label": "",
        "field_key": "",
        "type_choice": "free_text",
        "free_text_subtype": "text",
        "choice_style": "choice_radio",
        "help_text": "",
        "on_registration_page": FieldOnRegistrationPage.YES_REQUIRED.value,
        "options": [],
        "target_name": "",
        "derivation_method": DerivationType.AGE_BRACKET.value,
        "source_key": "",
        "as_of_day": "",
        "as_of_month": "",
        "as_of_year": "",
        "min_age": "",
        "max_age": "",
        "boundaries": "",
        "map_source": [],
        "map_target": [],
    }


def _normalise_modal_values(values: dict[str, Any]) -> dict[str, Any]:
    """Keep the rendered form coherent: a choice type always shows ≥1 option row."""
    if values["type_choice"] == "choice" and not values["options"]:
        values["options"] = [{"value": "", "help_text": ""}]
    return values


def _new_modal_ctx(assembly_id: uuid.UUID, values: dict[str, Any], error: str = "") -> dict[str, Any]:
    is_derived_choice = values["type_choice"] == "derived"
    derived = _build_derived_ctx(assembly_id, values, target_locked=False) if is_derived_choice else None
    if is_derived_choice:
        action_url = url_for("respondent_field_schema.add_derived_field_view", assembly_id=assembly_id)
    else:
        action_url = url_for("respondent_field_schema.add_field_view", assembly_id=assembly_id)
    # Without targets the Derived option is left off the type picker entirely —
    # a derived field feeds one, so there is nothing it could be pointed at.
    has_targets = _assembly_has_targets(assembly_id)
    type_choices = list(_STANDARD_TYPE_CHOICES)
    if has_targets:
        type_choices.append({"value": "derived", "label": _l("Derived (computed from another field)")})
    choice_candidate_key = _choice_candidate_key(values) if values["type_choice"] == "choice" else ""
    return {
        "mode": "new",
        "field": None,
        "action_url": action_url,
        "refresh_url": url_for("respondent_field_schema.new_field_modal", assembly_id=assembly_id),
        "type_choices": type_choices,
        "type_locked": False,
        "is_derived": False,
        "has_targets": has_targets,
        "derived": derived,
        "choice_candidate_key": choice_candidate_key,
        "choice_target": _matching_choice_target(assembly_id, choice_candidate_key),
        "error": error,
        "values": _normalise_modal_values(values),
    }


def _edit_modal_ctx(
    assembly_id: uuid.UUID, field: RespondentFieldDefinition, values: dict[str, Any], error: str = ""
) -> dict[str, Any]:
    type_choices = list(_STANDARD_TYPE_CHOICES)
    if field.field_type in _LEGACY_TYPE_CHOICES:
        type_choices.append(_LEGACY_TYPE_CHOICES[field.field_type])
    derived = _build_derived_ctx(assembly_id, values, target_locked=True) if field.is_derived else None
    if field.is_derived:
        action_url = url_for(
            "respondent_field_schema.update_derivation_view", assembly_id=assembly_id, field_id=field.id
        )
    else:
        action_url = url_for("respondent_field_schema.update_field_view", assembly_id=assembly_id, field_id=field.id)
    offers_choice = values["type_choice"] == "choice" and not field.is_fixed and not field.is_derived
    choice_candidate_key = _choice_candidate_key(values, field) if offers_choice else ""
    return {
        "mode": "edit",
        "field": field,
        "action_url": action_url,
        "refresh_url": url_for("respondent_field_schema.edit_field_modal", assembly_id=assembly_id, field_id=field.id),
        "type_choices": type_choices,
        "type_locked": field.is_fixed,
        "is_derived": field.is_derived,
        "has_targets": True,
        "derived": derived,
        "choice_candidate_key": choice_candidate_key,
        "choice_target": _matching_choice_target(assembly_id, choice_candidate_key),
        "error": error,
        "values": _normalise_modal_values(values),
    }


def _apply_option_action(values: dict[str, Any], form_action: str) -> dict[str, Any]:
    """Apply an options-editor round-trip action (add/remove a row) to the form state."""
    if form_action == "add_option":
        values["options"].append({"value": "", "help_text": ""})
    elif form_action.startswith("remove_option_"):
        try:
            index = int(form_action.removeprefix("remove_option_"))
        except ValueError:
            return values
        if 0 <= index < len(values["options"]):
            values["options"].pop(index)
    return values


def _choice_candidate_key(values: dict[str, Any], field: RespondentFieldDefinition | None = None) -> str:
    """The field key this choice field will carry — what a target's name has to match."""
    if field is not None:
        return field.field_key
    return normalise_field_key(values["field_key"] or values["label"])


def _matching_choice_target(assembly_id: uuid.UUID, candidate_key: str) -> dict[str, Any] | None:
    """The target category whose name matches the field key, for the copy-options button.

    Case-insensitive exact name match — the same join the field spec and
    selection use, so a copy also means the field will actually feed the target.
    """
    if not candidate_key:
        return None
    uow = bootstrap.get_flask_uow()
    with uow:
        for category in uow.target_categories.get_by_assembly_id(assembly_id):
            if category.name.lower() == candidate_key.lower():
                return {"name": category.name, "values": [v.value for v in category.values]}
    return None


def _copy_target_options(assembly_id: uuid.UUID, values: dict[str, Any], candidate_key: str) -> dict[str, Any]:
    """Replace the option rows with the matching target's values (a one-off copy, no link).

    Help text already written against a matching value survives the copy;
    without a matching target this is a no-op re-render.
    """
    target = _matching_choice_target(assembly_id, candidate_key)
    if target is None:
        return values
    existing_help = {row["value"]: row["help_text"] for row in values["options"]}
    values["options"] = [{"value": value, "help_text": existing_help.get(value, "")} for value in target["values"]]
    return values


def _submitted_options(values: dict[str, Any]) -> list[ChoiceOption]:
    """The non-blank option rows as domain objects; blank rows are dropped."""
    return [
        ChoiceOption(value=row["value"].strip(), help_text=row["help_text"].strip())
        for row in values["options"]
        if row["value"].strip()
    ]


# ---------------------------------------------------------------------------
# The derived-field panel: source filtering, config parsing, and pre-fills.
# ---------------------------------------------------------------------------

_UNDER_RE = re.compile(r"^under-(\d+)$")
_PLUS_RE = re.compile(r"^(\d+)\+$")
_RANGE_RE = re.compile(r"^(\d+)-(\d+)$")


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


def parse_derivation_rule(values: dict[str, Any]) -> DerivationRule:
    """The rule the modal's derived-panel values describe. Raises ValueError."""
    method = values["derivation_method"]
    if method == DerivationType.AGE_BRACKET.value:
        return parse_age_rule(values)
    if method == DerivationType.SMALL_MAPPING.value:
        return parse_small_mapping_rule(values)
    if method == DerivationType.LARGE_MAPPING.value:
        return LargeMappingRule()
    raise ValueError(_("Choose how the field should be derived"))


def age_prefill_from_target(target_values: list[str]) -> dict[str, str] | None:
    """min/max/boundaries form values parsed from "16-24"-style target value names.

    Returns None when the target's values don't look like a complete bracket
    set — the caller leaves the inputs blank for the user to fill in (Q9).
    """
    min_age: int | None = None
    max_age: int | None = None
    lowers: list[int] = []
    for value in target_values:
        if under := _UNDER_RE.match(value):
            min_age = int(under.group(1))
        elif plus := _PLUS_RE.match(value):
            max_age = int(plus.group(1))
        elif rng := _RANGE_RE.match(value):
            lowers.append(int(rng.group(1)))
        else:
            return None
    if not lowers or max_age is None:
        return None
    lowers = sorted(set(lowers))
    if min_age is None:
        min_age = lowers[0]
    boundaries = [lower for lower in lowers if lower != min_age]
    return {
        "min_age": str(min_age),
        "max_age": str(max_age),
        "boundaries": ", ".join(str(b) for b in boundaries),
    }


def _assembly_has_targets(assembly_id: uuid.UUID) -> bool:
    uow = bootstrap.get_flask_uow()
    with uow:
        return bool(list(uow.target_categories.get_by_assembly_id(assembly_id)))


def _apply_age_prefills(values: dict[str, Any], selected_target: dict[str, Any] | None, first_date: Any) -> None:
    """Pre-fill blank age-config inputs: the as-of date from the assembly, brackets from the target."""
    if not (values["as_of_day"] or values["as_of_month"] or values["as_of_year"]) and first_date is not None:
        values["as_of_day"] = str(first_date.day)
        values["as_of_month"] = str(first_date.month)
        values["as_of_year"] = str(first_date.year)
    # While no boundaries have been entered, the target's values own the whole
    # bracket config — so a successful parse overwrites min/max defaults too.
    if selected_target and not values["boundaries"]:
        prefill = age_prefill_from_target(selected_target["values"])
        if prefill:
            values.update(prefill)
    values["min_age"] = values["min_age"] or "16"
    values["max_age"] = values["max_age"] or "100"


def _build_derived_ctx(assembly_id: uuid.UUID, values: dict[str, Any], target_locked: bool) -> dict[str, Any]:
    """Everything the derived panel needs: targets, compatible sources, pre-fills and warnings."""
    uow = bootstrap.get_flask_uow()
    with uow:
        assembly = uow.assemblies.get(assembly_id)
        first_date = assembly.first_assembly_date if assembly else None
        categories = list(uow.target_categories.get_by_assembly_id(assembly_id))
        targets: list[dict[str, Any]] = [{"name": c.name, "values": [v.value for v in c.values]} for c in categories]
        schema = [f.create_detached_copy() for f in uow.respondent_field_definitions.list_by_assembly(assembly_id)]

    method = values["derivation_method"]
    try:
        derivation_type = DerivationType(method)
    except ValueError:
        derivation_type = DerivationType.AGE_BRACKET
        values["derivation_method"] = derivation_type.value

    sources = sorted(compatible_source_fields(schema, derivation_type), key=lambda f: f.field_key)
    selected_target = next((t for t in targets if t["name"].lower() == values["target_name"].lower()), None)
    selected_source = next((f for f in sources if f.field_key == values["source_key"]), None)

    preview_labels: list[str] = []
    mismatch_labels: list[str] = []
    if derivation_type == DerivationType.AGE_BRACKET:
        _apply_age_prefills(values, selected_target, first_date)
        try:
            rule = parse_age_rule(values)
        except ValueError:
            pass  # incomplete config — no preview or mismatch warning yet
        else:
            preview_labels = [*rule.bracket_labels(), rule.fallback]
            if selected_target:
                target_value_set = set(selected_target["values"])
                mismatch_labels = [label for label in rule.bracket_labels() if label not in target_value_set]

    map_rows: list[dict[str, str]] = []
    if derivation_type == DerivationType.SMALL_MAPPING and selected_source and selected_source.options:
        submitted = dict(zip_longest(values["map_source"], values["map_target"], fillvalue=""))
        map_rows = [
            {"source_value": option.value, "target_value": submitted.get(option.value, "")}
            for option in selected_source.options
        ]

    return {
        "targets": targets,
        "selected_target": selected_target,
        "sources": sources,
        "selected_source": selected_source,
        "source_is_integer": selected_source is not None and selected_source.effective_field_type == FieldType.INTEGER,
        "target_locked": target_locked,
        "preview_labels": preview_labels,
        "mismatch_labels": mismatch_labels,
        "map_rows": map_rows,
        "fallback": DEFAULT_FALLBACK,
        "method_options": [
            {"value": DerivationType.AGE_BRACKET.value, "label": _("Age brackets")},
            {"value": DerivationType.SMALL_MAPPING.value, "label": _("Map choices")},
            {"value": DerivationType.LARGE_MAPPING.value, "label": _("Lookup table")},
        ],
        "method_help": {
            DerivationType.AGE_BRACKET.value: _("From a date of birth or a year of birth"),
            DerivationType.SMALL_MAPPING.value: _("Map each answer of an existing choice field to a target value"),
            DerivationType.LARGE_MAPPING.value: _("Upload a CSV mapping, e.g. postcode to region"),
        },
    }


# ---------------------------------------------------------------------------
# Page and fragment rendering.
# ---------------------------------------------------------------------------


def _derivation_type_labels() -> dict[str, str]:
    return {
        DerivationType.AGE_BRACKET.value: _("Age brackets"),
        DerivationType.SMALL_MAPPING.value: _("Map choices"),
        DerivationType.LARGE_MAPPING.value: _("Lookup table"),
    }


def _schema_page_context(assembly_id: uuid.UUID) -> dict[str, Any]:
    """Everything view.html and _editor.html need to render the schema page."""
    uow = bootstrap.get_flask_uow()
    gsheet = None
    csv_status = None
    with uow:
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
        grouped = get_schema_grouped(uow, current_user.id, assembly_id)

        # Reuse the assembly-tabs computed state so the tab bar renders correctly.
        # Both lookups are optional — a fresh assembly has neither.
        with contextlib.suppress(ServiceLayerError):
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)
        with contextlib.suppress(ServiceLayerError):
            csv_status = get_csv_upload_status(uow, current_user.id, assembly_id)

    sections = [
        {
            "group": group,
            "label": GROUP_LABELS[group],
            "fields": grouped.get(group, []),
        }
        for group in GROUP_DISPLAY_ORDER
    ]
    schema_has_rows = any(section["fields"] for section in sections)

    data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))
    targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(data_source, gsheet, csv_status)

    all_fields = [f for group_fields in grouped.values() for f in group_fields]
    has_guessable_text_rows = any(
        not f.is_fixed and not f.is_derived and f.field_type == FieldType.TEXT for f in all_fields
    )
    large_mapping_fields = [f for f in all_fields if f.is_derived and f.derivation_type == DerivationType.LARGE_MAPPING]
    with uow:
        has_respondents = uow.respondents.count_by_assembly_id(assembly_id) > 0
        mapping_row_counts = {
            f.id: uow.respondent_field_mapping_entries.count_for_field(f.id) for f in large_mapping_fields
        }
    show_guess_button = has_guessable_text_rows and has_respondents

    return {
        "mapping_row_counts": mapping_row_counts,
        "assembly": assembly,
        "sections": sections,
        "group_choices": [{"value": group.value, "label": GROUP_LABELS[group]} for group in GROUP_DISPLAY_ORDER],
        "field_type_labels_by_value": {ft.value: FIELD_TYPE_LABELS[ft] for ft in FieldType},
        "derivation_type_labels": _derivation_type_labels(),
        "on_registration_page_choices": [
            {"value": FieldOnRegistrationPage.NO.value, "label": _("Not shown")},
            {"value": FieldOnRegistrationPage.YES_OPTIONAL.value, "label": _("Optional")},
            {"value": FieldOnRegistrationPage.YES_REQUIRED.value, "label": _("Required")},
        ],
        "schema_has_rows": schema_has_rows,
        "show_guess_button": show_guess_button,
        "data_source": data_source,
        "gsheet": gsheet,
        "targets_enabled": targets_enabled,
        "respondents_enabled": respondents_enabled,
        "selection_enabled": selection_enabled,
    }


def _render_schema_page(
    assembly_id: uuid.UUID, modal_ctx: dict[str, Any] | None = None, status: int = 200
) -> ResponseReturnValue:
    """Render the full schema page, optionally with the field modal already open."""
    return render_template(
        "backoffice/respondent_field_schema/view.html",
        modal_ctx=modal_ctx,
        **_schema_page_context(assembly_id),
    ), status


def _render_editor_fragment(assembly_id: uuid.UUID, oob: bool = False) -> ResponseReturnValue:
    """Render just the #schema-editor fragment.

    With ``oob=True`` the fragment swaps out-of-band, so the (otherwise empty)
    response also clears #field-modal-container — closing the modal that
    triggered the mutation.
    """
    return render_template(
        "backoffice/respondent_field_schema/_editor.html",
        oob=oob,
        **_schema_page_context(assembly_id),
    ), 200


def _render_modal_fragment(assembly_id: uuid.UUID, modal_ctx: dict[str, Any], status: int = 200) -> ResponseReturnValue:
    return render_template(
        "backoffice/respondent_field_schema/_field_modal.html",
        modal_ctx=modal_ctx,
        **_schema_page_context(assembly_id),
    ), status


def _load_field(assembly_id: uuid.UUID, field_id: uuid.UUID) -> RespondentFieldDefinition | None:
    uow = bootstrap.get_flask_uow()
    with uow:
        field = uow.respondent_field_definitions.get(field_id)
        if field is None or field.assembly_id != assembly_id:
            return None
        detached: RespondentFieldDefinition = field.create_detached_copy()
        return detached


# ---------------------------------------------------------------------------
# Routes.
# ---------------------------------------------------------------------------


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema")
@login_required
def view_schema(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Display the respondent field schema for an assembly."""
    try:
        return _render_schema_page(assembly_id)
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for user", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions for assembly", assembly_id=str(assembly_id), error=str(e))
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema.json")
@login_required
def field_spec_json(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Return the assembly's full respondent field spec as JSON.

    Deliberately not linked from anywhere in the UI. It exists so a script
    outside the app — a test-data generator, for one — can discover an
    assembly's CSV columns and their valid values without scraping the schema
    page. See docs/respondent_field_spec.md for the shape.
    """
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            spec = build_field_spec(uow, current_user.id, assembly_id)
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for field spec",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        return jsonify({"error": _("Assembly not found")}), 404
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions for field spec", assembly_id=str(assembly_id), error=str(e))
        return jsonify({"error": _("You don't have permission to view this assembly")}), 403
    return jsonify(spec), 200


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema/initialise", methods=["POST"])
@login_required
def initialise_schema(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Seed an empty schema (fixed-field rows only) for registration-first assemblies."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            inserted = initialise_empty_schema(uow, current_user.id, assembly_id)
        if inserted:
            flash(_("Schema initialised with %(count)d fixed fields", count=inserted), "success")
        else:
            flash(_("Schema already exists"), "info")
    except InsufficientPermissions:
        flash(_("You don't have permission to initialise the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema/fields/new-modal")
@login_required
def new_field_modal(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the add-field modal.

    HTMX requests get the modal fragment — both on first open and on the
    type-radio re-renders, which hx-include the form state as query args. A
    plain navigation gets the whole schema page with the modal already open,
    so the flow still works (via full page loads) when JS is unavailable.
    """
    values = _modal_values_from_request(request.args) if "modal" in request.args else _default_modal_values()
    modal_ctx = _new_modal_ctx(assembly_id, values)
    try:
        if _is_htmx():
            return _render_modal_fragment(assembly_id, modal_ctx)
        return _render_schema_page(assembly_id, modal_ctx=modal_ctx)
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/edit-modal")
@login_required
def edit_field_modal(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the edit-field modal (HTMX fragment / full-page fallback)."""
    try:
        field = _load_field(assembly_id, field_id)
        if field is None:
            flash(_("Field not found"), "error")
            return redirect(url_for("respondent_field_schema.view_schema", assembly_id=assembly_id))
        values = (
            _modal_values_from_request(request.args) if "modal" in request.args else _modal_values_from_field(field)
        )
        modal_ctx = _edit_modal_ctx(assembly_id, field, values)
        if _is_htmx():
            return _render_modal_fragment(assembly_id, modal_ctx)
        return _render_schema_page(assembly_id, modal_ctx=modal_ctx)
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))


def _modal_roundtrip_response(
    assembly_id: uuid.UUID, modal_ctx: dict[str, Any], status: int = 200
) -> ResponseReturnValue:
    """Re-render the modal without saving — HTMX gets the fragment, no-JS the full page."""
    if _is_htmx():
        return _render_modal_fragment(assembly_id, modal_ctx, status=status)
    return _render_schema_page(assembly_id, modal_ctx=modal_ctx, status=status)


def _flash_failure_response(assembly_id: uuid.UUID, message: str) -> ResponseReturnValue:
    flash(message, "error")
    return _schema_page_redirect(assembly_id)


def _try_add_field(assembly_id: uuid.UUID, values: dict[str, Any], is_modal: bool) -> str:
    """Validate and save a new field; returns a user-facing error message, or "" on success."""
    label = values["label"].strip()
    field_key = normalise_field_key(values["field_key"] or label or request.form.get("field_key", ""))
    if not field_key:
        return _("A label or field key is required (letters, numbers and underscores)")
    group = _parse_group(request.form.get("group")) or RespondentFieldGroup.OTHER
    if is_modal:
        field_type = _field_type_from_taxonomy(values)
    else:
        field_type = _parse_field_type(request.form.get("field_type")) or FieldType.TEXT
    on_registration_page = (
        _parse_on_registration_page(values["on_registration_page"]) or FieldOnRegistrationPage.YES_REQUIRED
    )

    options = _submitted_options(values) if field_type in CHOICE_TYPES else None
    if field_type in CHOICE_TYPES and not options:
        return _("A choice field needs at least one option")

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            add_field(
                uow,
                current_user.id,
                assembly_id,
                field_key,
                label=label or None,
                group=group,
                field_type=field_type,
                options=options,
                on_registration_page=on_registration_page,
                help_text=values["help_text"].strip(),
            )
    except FieldDefinitionConflictError as e:
        return str(e)
    except InsufficientPermissions:
        return _("You don't have permission to edit the schema")
    except NotFoundError:
        return _("Assembly not found")
    return ""


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/add",
    methods=["POST"],
)
@login_required
def add_field_view(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Add a new field to the schema — from the modal, or a plain form post.

    Modal submissions carry the type taxonomy (``type_choice`` etc.), a
    wholesale options list, and a ``form_action`` distinguishing Save from the
    options-editor round-trips. A plain post with ``field_key``/``field_type``
    (the pre-modal shape) still works so scripted callers don't break.
    """
    form_action = request.form.get("form_action", "save")
    is_modal = request.form.get("modal") == "1"
    values = _modal_values_from_request(request.form)

    if is_modal and form_action != "save":
        # An options-editor round-trip (add/remove/copy rows) or a no-JS type
        # refresh — re-render the form with the entered values, saving nothing.
        if form_action == "copy_target_options":
            values = _copy_target_options(assembly_id, values, _choice_candidate_key(values))
        else:
            values = _apply_option_action(values, form_action)
        return _modal_roundtrip_response(assembly_id, _new_modal_ctx(assembly_id, values))

    error = _try_add_field(assembly_id, values, is_modal)
    if error:
        if is_modal:
            return _modal_roundtrip_response(assembly_id, _new_modal_ctx(assembly_id, values, error=error), status=422)
        return _flash_failure_response(assembly_id, error)

    if _is_htmx():
        return _render_editor_fragment(assembly_id, oob=True)
    flash(_("Field added"), "success")
    return _schema_page_redirect(assembly_id)


def _report_response(
    assembly_id: uuid.UUID,
    report: RecomputeReport,
    title: str,
    upload_report: MappingUploadReport | None = None,
) -> ResponseReturnValue:
    """Show the recompute report in the modal (Q11) and refresh the editor behind it."""
    page_ctx = _schema_page_context(assembly_id)
    report_ctx = {"report": report, "title": title, "upload_report": upload_report}
    if _is_htmx():
        report_html = render_template(
            "backoffice/respondent_field_schema/_derivation_report_modal.html", report_ctx=report_ctx, **page_ctx
        )
        editor_html = render_template("backoffice/respondent_field_schema/_editor.html", oob=True, **page_ctx)
        return report_html + editor_html, 200
    return render_template(
        "backoffice/respondent_field_schema/view.html",
        modal_ctx={"mode": "report", "report_ctx": report_ctx},
        **page_ctx,
    ), 200


def _try_create_derived(assembly_id: uuid.UUID, values: dict[str, Any]) -> tuple[RecomputeReport | None, str]:
    """Validate and create the derived field; returns (report, error-message)."""
    target_name = values["target_name"].strip()
    if not target_name:
        return None, _("Choose the target this field feeds")
    if not values["source_key"]:
        return None, _("Choose the field to derive from")
    try:
        rule = parse_derivation_rule(values)
    except ValueError as e:
        return None, str(e)
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            categories = list(uow.target_categories.get_by_assembly_id(assembly_id))
            target = next((c for c in categories if c.name.lower() == target_name.lower()), None)
            if target is None:
                return None, _("Choose the target this field feeds")
            # The field key is the target's name verbatim: selection pairs a
            # target category with a respondent column by exact string match,
            # and the field-spec join is a case-insensitive name match.
            field, report = create_derived_field(
                uow,
                current_user.id,
                assembly_id,
                field_key=target.name.strip(),
                label=target.name.strip(),
                source_field_key=values["source_key"],
                rule=rule,
                output_values=[v.value for v in target.values],
            )
            if values["help_text"].strip():
                update_field(uow, current_user.id, assembly_id, field.id, help_text=values["help_text"].strip())
    except FieldDefinitionConflictError as e:
        return None, str(e)
    except InsufficientPermissions:
        return None, _("You don't have permission to edit the schema")
    except NotFoundError:
        return None, _("Assembly not found")
    return report, ""


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/add-derived",
    methods=["POST"],
)
@login_required
def add_derived_field_view(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Create a derived field from the modal's derived panel.

    Success shows the recompute report in the modal (the save recomputes the
    whole pool synchronously); failure re-renders the panel at 422.
    """
    form_action = request.form.get("form_action", "save")
    values = _modal_values_from_request(request.form)
    values["type_choice"] = "derived"

    if form_action != "save":
        return _modal_roundtrip_response(assembly_id, _new_modal_ctx(assembly_id, values))

    report, error = _try_create_derived(assembly_id, values)
    if error or report is None:
        return _modal_roundtrip_response(assembly_id, _new_modal_ctx(assembly_id, values, error=error), status=422)
    return _report_response(assembly_id, report, _("Derived field created"))


def _try_update_derivation(
    assembly_id: uuid.UUID, field: RespondentFieldDefinition, values: dict[str, Any]
) -> tuple[RecomputeReport | None, str]:
    """Validate and apply a derivation edit; returns (report, error-message)."""
    try:
        rule = parse_derivation_rule(values)
    except ValueError as e:
        return None, str(e)
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            categories = list(uow.target_categories.get_by_assembly_id(assembly_id))
            target = next((c for c in categories if c.name.lower() == field.field_key.lower()), None)
            output_values = [v.value for v in target.values] if target else None
            _field, report = update_derivation(
                uow, current_user.id, assembly_id, field.id, rule, output_values=output_values
            )
            update_field(
                uow,
                current_user.id,
                assembly_id,
                field.id,
                label=values["label"].strip() or None,
                help_text=values["help_text"],
            )
    except FieldDefinitionConflictError as e:
        return None, str(e)
    except FieldDefinitionNotFoundError:
        return None, _("Field not found")
    except InsufficientPermissions:
        return None, _("You don't have permission to edit the schema")
    except NotFoundError:
        return None, _("Assembly not found")
    return report, ""


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/derivation",
    methods=["POST"],
)
@login_required
def update_derivation_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Edit a derived field's method config (and label/help text) from the modal.

    The source and target cannot be changed here — delete and recreate instead
    (the modal says so). Success shows the recompute report.
    """
    form_action = request.form.get("form_action", "save")
    values = _modal_values_from_request(request.form)
    values["type_choice"] = "derived"

    field = _load_field(assembly_id, field_id)
    if field is None or not field.is_derived:
        return _field_missing_response(assembly_id, oob=True)

    if form_action != "save":
        return _modal_roundtrip_response(assembly_id, _edit_modal_ctx(assembly_id, field, values))

    report, error = _try_update_derivation(assembly_id, field, values)
    if error or report is None:
        return _modal_roundtrip_response(
            assembly_id, _edit_modal_ctx(assembly_id, field, values, error=error), status=422
        )
    return _report_response(assembly_id, report, _("Derivation updated"))


def _render_mapping_modal(
    assembly_id: uuid.UUID,
    field: RespondentFieldDefinition,
    error: str = "",
    allow_new_outputs: bool = False,
    status: int = 200,
) -> ResponseReturnValue:
    modal_ctx = {"mode": "mapping", "field": field, "error": error, "allow_new_outputs": allow_new_outputs}
    if _is_htmx():
        return render_template(
            "backoffice/respondent_field_schema/_mapping_upload_modal.html",
            modal_ctx=modal_ctx,
            **_schema_page_context(assembly_id),
        ), status
    return _render_schema_page(assembly_id, modal_ctx=modal_ctx, status=status)


def _load_large_mapping_field(assembly_id: uuid.UUID, field_id: uuid.UUID) -> RespondentFieldDefinition | None:
    field = _load_field(assembly_id, field_id)
    if field is None or not field.is_derived or field.derivation_type != DerivationType.LARGE_MAPPING:
        return None
    return field


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/mapping-modal")
@login_required
def mapping_upload_modal(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the lookup-table upload dialog (HTMX fragment / full-page fallback)."""
    field = _load_large_mapping_field(assembly_id, field_id)
    if field is None:
        flash(_("Field not found"), "error")
        return redirect(url_for("respondent_field_schema.view_schema", assembly_id=assembly_id))
    try:
        return _render_mapping_modal(assembly_id, field)
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/mapping-upload",
    methods=["POST"],
)
@login_required
def mapping_upload_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Replace a lookup table from an uploaded CSV, recompute, and show the combined report.

    The file is parsed in memory and never persisted — only the normalised
    rows are stored (see upload_large_mapping).
    """
    field = _load_large_mapping_field(assembly_id, field_id)
    if field is None:
        return _field_missing_response(assembly_id, oob=True)
    allow_new_outputs = request.form.get("allow_new_outputs") == "1"

    def _fail(message: str) -> ResponseReturnValue:
        return _render_mapping_modal(assembly_id, field, error=message, allow_new_outputs=allow_new_outputs, status=422)

    upload = request.files.get("mapping_file")
    if upload is None or not upload.filename:
        return _fail(_("Choose a CSV file to upload."))
    try:
        csv_content = upload.read().decode("utf-8")
    except UnicodeDecodeError:
        return _fail(_("Could not read the file — it must be UTF-8 encoded CSV."))

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            upload_report = upload_large_mapping(
                uow, current_user.id, assembly_id, field_id, csv_content, allow_new_outputs=allow_new_outputs
            )
            report = recompute_derived_field(uow, current_user.id, assembly_id, field_id)
    except FieldDefinitionConflictError as e:
        return _fail(str(e))
    except FieldDefinitionNotFoundError:
        return _fail(_("Field not found"))
    except InsufficientPermissions:
        return _fail(_("You don't have permission to edit the schema"))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _report_response(assembly_id, report, _("Lookup table uploaded"), upload_report=upload_report)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/recompute",
    methods=["POST"],
)
@login_required
def recompute_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Recompute one derived field across the pool and show the report."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            report = recompute_derived_field(uow, current_user.id, assembly_id, field_id)
    except (FieldDefinitionConflictError, FieldDefinitionNotFoundError):
        flash(_("Field not found"), "error")
        return _schema_page_redirect(assembly_id)
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
        return _schema_page_redirect(assembly_id)
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _report_response(assembly_id, report, _("Recompute complete"))


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/update",
    methods=["POST"],
)
@login_required
def update_field_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Update a field — from the edit modal, or the row's section select.

    Modal submissions carry the type taxonomy and a wholesale options list;
    the row form posts just ``group``. A plain post with ``field_type`` (the
    pre-modal shape) still works so scripted callers don't break.
    """
    form_action = request.form.get("form_action", "save")
    is_modal = request.form.get("modal") == "1"
    values = _modal_values_from_request(request.form)

    field = _load_field(assembly_id, field_id)
    if field is None:
        return _field_missing_response(assembly_id, oob=is_modal)

    if is_modal and form_action != "save":
        if form_action == "copy_target_options":
            values = _copy_target_options(assembly_id, values, _choice_candidate_key(values, field))
        else:
            values = _apply_option_action(values, form_action)
        return _modal_roundtrip_response(assembly_id, _edit_modal_ctx(assembly_id, field, values))

    if is_modal:
        update_kwargs, error = _modal_update_kwargs(field, values)
    else:
        update_kwargs, error = _legacy_update_kwargs()
        if not update_kwargs and not error:
            return _nothing_submitted_response(assembly_id)

    if not error:
        error = _try_update_field(assembly_id, field_id, update_kwargs)

    if error:
        if is_modal:
            return _modal_roundtrip_response(
                assembly_id, _edit_modal_ctx(assembly_id, field, values, error=error), status=422
            )
        return _flash_failure_response(assembly_id, error)

    if _is_htmx():
        # A modal save clears the modal via the out-of-band swap; the row's
        # section select targets #schema-editor directly, so no OOB there.
        return _render_editor_fragment(assembly_id, oob=is_modal)
    flash(_("Field updated"), "success")
    return _schema_page_redirect(assembly_id)


def _field_missing_response(assembly_id: uuid.UUID, oob: bool) -> ResponseReturnValue:
    if _is_htmx():
        return _render_editor_fragment(assembly_id, oob=oob)
    flash(_("Field not found"), "error")
    return _schema_page_redirect(assembly_id)


def _nothing_submitted_response(assembly_id: uuid.UUID) -> ResponseReturnValue:
    if _is_htmx():
        return _render_editor_fragment(assembly_id)
    flash(_("No changes submitted"), "info")
    return _schema_page_redirect(assembly_id)


def _modal_update_kwargs(field: RespondentFieldDefinition, values: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """The update_field kwargs for a modal save, plus a validation error message ("" when valid).

    A fixed field keeps its type and a derived field keeps its type, options and
    registration state — the modal doesn't render those controls, so the save
    doesn't touch them.
    """
    update_kwargs: dict[str, Any] = {
        "label": values["label"].strip() or None,
        "help_text": values["help_text"],
    }
    if not field.is_derived:
        update_kwargs["on_registration_page"] = _parse_on_registration_page(values["on_registration_page"])
    if not field.is_fixed and not field.is_derived:
        field_type = _field_type_from_taxonomy(values)
        update_kwargs["field_type"] = field_type
        if field_type in CHOICE_TYPES:
            options = _submitted_options(values)
            if not options:
                return {}, _("A choice field needs at least one option")
            update_kwargs["options"] = options
    return update_kwargs, ""


def _legacy_update_kwargs() -> tuple[dict[str, Any], str]:
    """The update_field kwargs for a plain (non-modal) post; empty dict means nothing was submitted."""
    label = request.form.get("label", "").strip() or None
    group = _parse_group(request.form.get("group"))
    field_type = _parse_field_type(request.form.get("field_type"))
    on_registration_page = _parse_on_registration_page(request.form.get("on_registration_page"))
    if label is None and group is None and field_type is None and on_registration_page is None:
        return {}, ""
    return {
        "label": label,
        "group": group,
        "field_type": field_type,
        "on_registration_page": on_registration_page,
    }, ""


def _try_update_field(assembly_id: uuid.UUID, field_id: uuid.UUID, update_kwargs: dict[str, Any]) -> str:
    """Run the update; returns a user-facing error message, or "" on success."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            update_field(uow, current_user.id, assembly_id, field_id, **update_kwargs)
    except FieldDefinitionConflictError as e:
        return str(e)
    except FieldDefinitionNotFoundError:
        # The message may carry internal detail — show a generic one.
        return _("Field not found")
    except ValueError as e:
        # Domain validation (e.g. a choice type without options) — the message
        # is developer-written and safe to show.
        return str(e)
    except InsufficientPermissions:
        return _("You don't have permission to edit the schema")
    except NotFoundError:
        return _("Assembly not found")
    return ""


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/guess-types",
    methods=["POST"],
)
@login_required
def guess_types_view(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Overwrite TEXT-typed schema rows with guessed types based on respondent data."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            changed = guess_field_types(uow, current_user.id, assembly_id)
        if changed:
            flash(_("Guessed types for %(count)d fields", count=len(changed)), "success")
        else:
            flash(_("No fields were guessed — no untouched text rows to update"), "info")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/options/add",
    methods=["POST"],
)
@login_required
def add_option_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Append a ChoiceOption to a choice field."""
    value = request.form.get("value", "").strip()
    help_text = request.form.get("help_text", "")
    if not value:
        flash(_("Option value is required"), "error")
        return _schema_page_redirect(assembly_id)
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            add_choice_option(uow, current_user.id, assembly_id, field_id, value, help_text)
        flash(_("Option added"), "success")
    except FieldDefinitionConflictError as e:
        flash(str(e), "error")
    except FieldDefinitionNotFoundError:
        flash(_("Field not found"), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/options/update",
    methods=["POST"],
)
@login_required
def update_option_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Update the value and/or help_text of an existing ChoiceOption."""
    old_value = request.form.get("old_value", "").strip()
    new_value = request.form.get("value", "").strip()
    new_help_text = request.form.get("help_text", "")
    if not old_value:
        flash(_("Original option value is required"), "error")
        return _schema_page_redirect(assembly_id)
    if not new_value:
        flash(_("Option value cannot be blank"), "error")
        return _schema_page_redirect(assembly_id)
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            update_choice_option(
                uow,
                current_user.id,
                assembly_id,
                field_id,
                old_value=old_value,
                new_value=new_value,
                new_help_text=new_help_text,
            )
        flash(_("Option updated"), "success")
    except FieldDefinitionConflictError as e:
        flash(str(e), "error")
    except FieldDefinitionNotFoundError:
        flash(_("Option not found"), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/options/remove",
    methods=["POST"],
)
@login_required
def remove_option_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Remove a ChoiceOption from a choice field."""
    value = request.form.get("value", "").strip()
    if not value:
        flash(_("Option value is required"), "error")
        return _schema_page_redirect(assembly_id)
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            remove_choice_option(uow, current_user.id, assembly_id, field_id, value)
        flash(_("Option removed"), "success")
    except FieldDefinitionConflictError as e:
        flash(str(e), "error")
    except FieldDefinitionNotFoundError:
        flash(_("Option not found"), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/move",
    methods=["POST"],
)
@login_required
def move_field(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Shift a field up or down one slot within its group.

    Accepts a ``direction`` form field of ``"up"`` or ``"down"``. Reuses the
    service-layer ``reorder_group`` to re-issue sort_orders atomically.
    """
    direction = request.form.get("direction", "")
    if direction not in {"up", "down"}:
        flash(_("Invalid move direction"), "error")
        return _schema_page_redirect(assembly_id)

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            fields = get_schema(uow, current_user.id, assembly_id)
            target = next((f for f in fields if f.id == field_id), None)
            if target is None:
                flash(_("Field not found"), "error")
                return _schema_page_redirect(assembly_id)

            same_group = [f for f in fields if f.group == target.group]
            index = next(i for i, f in enumerate(same_group) if f.id == field_id)
            swap_with = index - 1 if direction == "up" else index + 1
            if swap_with < 0 or swap_with >= len(same_group):
                # Already at the top/bottom — silent no-op rather than a flash.
                return _schema_page_redirect(assembly_id)

            new_order = same_group[:]
            new_order[index], new_order[swap_with] = new_order[swap_with], new_order[index]
            reorder_group(
                uow,
                current_user.id,
                assembly_id,
                target.group,
                [f.id for f in new_order],
            )
    except InsufficientPermissions:
        flash(_("You don't have permission to reorder fields"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/delete",
    methods=["POST"],
)
@login_required
def delete_field_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Delete a non-fixed field from the schema. Fixed fields are protected by the service layer."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            delete_field(uow, current_user.id, assembly_id, field_id)
        flash(_("Field removed"), "success")
    except FieldDefinitionConflictError as e:
        flash(str(e), "error")
    except FieldDefinitionNotFoundError:
        flash(_("Field not found"), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)
