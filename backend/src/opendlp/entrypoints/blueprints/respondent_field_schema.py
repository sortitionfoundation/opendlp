"""ABOUTME: Backoffice routes for managing a per-assembly respondent field schema
ABOUTME: Read-only schema rows plus an HTMX add/edit field modal; move, delete, initialise"""

import contextlib
import functools
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from itertools import zip_longest
from typing import Any

import structlog
from flask import Blueprint, flash, jsonify, make_response, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.domain.respondent_field_schema import (
    BOOL_TYPES,
    CHOICE_TYPES,
    FIELD_TYPE_LABELS,
    GROUP_DISPLAY_ORDER,
    GROUP_LABELS,
    ChoiceOption,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    duplicate_option_value,
    normalise_field_key,
)
from opendlp.entrypoints.registration_hub import registration_hub_context
from opendlp.entrypoints.scroll_utils import redirect_preserving_scroll
from opendlp.service_layer.assembly_service import (
    determine_data_source,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_tab_enabled_states,
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
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _
from opendlp.translations import lazy_gettext as _l

respondent_field_schema_bp = Blueprint("respondent_field_schema", __name__)

logger = structlog.get_logger(__name__)


def _refusals_go_to_the_dashboard(view: Callable[..., ResponseReturnValue]) -> Callable[..., ResponseReturnValue]:
    """Answer a refusal that escapes the view with the dashboard, not a server error.

    The modal routes report a failed save by re-rendering the page around the
    modal, and building that page checks the assembly and the user's access
    again. When the save failed *because* of one of those, the re-render raises
    the very error the view had just handled - from somewhere no ``except``
    clause in the view covers.
    """

    @functools.wraps(view)
    def guarded(*args: Any, **kwargs: Any) -> ResponseReturnValue:
        try:
            return view(*args, **kwargs)
        except InsufficientPermissions:
            flash(_("You don't have permission to edit the schema"), "error")
            return redirect(url_for("backoffice.dashboard"))
        except NotFoundError:
            flash(_("Assembly not found"), "error")
            return redirect(url_for("backoffice.dashboard"))

    return guarded


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _schema_page_redirect(assembly_id: uuid.UUID) -> ResponseReturnValue:
    # Preserve the submitting form's scroll position so saving a field, moving a
    # row, or editing an option doesn't bounce the user back to the top of the page.
    return redirect_preserving_scroll(url_for("respondent_field_schema.view_schema", assembly_id=assembly_id))


def _parse_registration_group(raw: str | None) -> RespondentFieldGroup | None:
    """Parse a section a question can be placed in; derived fields have their own group, never chosen."""
    group = _parse_group(raw)
    return None if group == RespondentFieldGroup.DERIVED else group


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

_LEGACY_TYPE_CHOICES: dict[FieldType, dict[str, Any]] = {
    FieldType.LONGTEXT: {"value": "longtext", "label": FIELD_TYPE_LABELS[FieldType.LONGTEXT]},
    # Labelled apart from the plain Checkbox entry above it: both are checkboxes, and
    # a dropdown offering the same word twice would say nothing about the difference.
    FieldType.BOOL_OR_NONE: {"value": "bool_or_none", "label": _l("Checkbox (can be left unanswered)")},
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

_TYPE_CHOICES = frozenset({"bool", "free_text", "choice", "date", "longtext", "bool_or_none"})


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


def _question_type_choices(field: RespondentFieldDefinition | None = None) -> list[dict[str, Any]]:
    """The modal's single question type dropdown: a few plain types, then text and choice groups.

    Values are FieldType values. A field still on a legacy type keeps it as an
    extra option, so opening its modal doesn't silently change the type.
    """

    def plain(field_type: FieldType) -> dict[str, Any]:
        return {"value": field_type.value, "label": str(FIELD_TYPE_LABELS[field_type])}

    choices: list[dict[str, Any]] = [
        plain(FieldType.BOOL),
        plain(FieldType.DATE),
        {"label": _("Text"), "options": [plain(FieldType.TEXT), plain(FieldType.EMAIL), plain(FieldType.INTEGER)]},
        {
            # Short forms of FIELD_TYPE_LABELS' "Choice (radios)" and "Choice (dropdown)":
            # the group heading already says "Choice".
            "label": _("Choice"),
            "options": [
                {"value": FieldType.CHOICE_RADIO.value, "label": _("Radio")},
                {"value": FieldType.CHOICE_DROPDOWN.value, "label": _("Dropdown")},
            ],
        },
    ]
    if field is not None and field.field_type in _LEGACY_TYPE_CHOICES:
        choices.append({"value": field.field_type.value, "label": _LEGACY_TYPE_CHOICES[field.field_type]["label"]})
    return choices


def _choice_style_choices() -> list[dict[str, Any]]:
    """The question types a field whose options belong to a target can switch between."""
    return [
        {"value": field_type.value, "label": str(FIELD_TYPE_LABELS[field_type])}
        for field_type in (FieldType.CHOICE_RADIO, FieldType.CHOICE_DROPDOWN)
    ]


def _question_type_help() -> dict[str, str]:
    """When to pick each question type that needs explaining, shown under the dropdown once chosen."""
    return {
        FieldType.CHOICE_RADIO.value: _(
            "Use for a small number of options (typically fewer than 5) when users need to see and compare all choices."
        ),
        FieldType.CHOICE_DROPDOWN.value: _(
            "Use for longer lists (typically more than 10 options) when displaying all choices would be impractical."
        ),
    }


def _required_switch_label(values: dict[str, Any]) -> str:
    """The Required switch's label, saying what an answer to this type of question has to be."""
    if not values["type_choice"]:
        return _("Required")
    field_type = _field_type_from_taxonomy(values)
    if field_type in BOOL_TYPES:
        return _("Checkbox must be checked")
    if field_type in CHOICE_TYPES:
        return _("An option must be chosen")
    if field_type == FieldType.DATE:
        return _("Full date must be entered")
    if field_type in (FieldType.TEXT, FieldType.EMAIL, FieldType.INTEGER, FieldType.LONGTEXT):
        return _("Text must be entered")
    return _("Required")


def _question_type_value(values: dict[str, Any]) -> str:
    """The question type dropdown's value for the modal state; "" until a type is chosen."""
    if not values["type_choice"]:
        return ""
    return _field_type_from_taxonomy(values).value


def _taxonomy_from_question_type(raw: str) -> dict[str, str]:
    """The modal taxonomy values for a submitted question type; no type_choice when none is chosen."""
    try:
        return _taxonomy_from_field_type(FieldType(raw))
    except ValueError:
        return {"type_choice": ""}


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
    # "original" is the value a row had when the dialog opened ("" for a row added
    # since). It rides along through every round trip, so a save can tell an
    # option that was renamed from one that was removed and another added.
    options = [
        {"value": value, "help_text": help_text, "original": original}
        for value, help_text, original in zip_longest(
            source.getlist("option_value"),
            source.getlist("option_help"),
            source.getlist("option_original"),
            fillvalue="",
        )
    ]
    values = {
        "label": source.get("label", ""),
        "field_key": source.get("field_key", ""),
        "group": source.get("group", ""),
        "type_choice": source.get("type_choice", "free_text"),
        "free_text_subtype": source.get("free_text_subtype", "text"),
        "choice_style": source.get("choice_style", "choice_radio"),
        "help_text": source.get("help_text", ""),
        "on_registration_page": source.get("on_registration_page", FieldOnRegistrationPage.YES_REQUIRED.value),
        "options": options,
    }
    # The modal's single question type dropdown; posts without it (scripted
    # callers) still describe the type with type_choice.
    if "question_type" in source:
        values.update(_taxonomy_from_question_type(source.get("question_type", "")))
    # The modal's Required switch: a checkbox, so it posts nothing when off -
    # the hidden marker says the switch was there. "Not on registration page" is never
    # chosen here; only derived fields are off the form, and they get it implicitly.
    if "required_switch" in source:
        values["on_registration_page"] = (
            FieldOnRegistrationPage.YES_REQUIRED.value
            if source.get("required")
            else FieldOnRegistrationPage.YES_OPTIONAL.value
        )
    return values


def _modal_values_from_field(field: RespondentFieldDefinition) -> dict[str, Any]:
    """The modal form state for editing an existing field."""
    values = _default_modal_values()
    values.update({
        "label": field.label,
        "field_key": field.field_key,
        "group": field.group.value,
        "help_text": field.help_text,
        "on_registration_page": field.on_registration_page.value,
        "options": [{"value": o.value, "help_text": o.help_text, "original": o.value} for o in field.options or []],
    })
    values.update(_taxonomy_from_field_type(field.field_type))
    return values


def _default_modal_values() -> dict[str, Any]:
    return {
        "label": "",
        "field_key": "",
        "group": RespondentFieldGroup.OTHER.value,
        # No type until one is chosen from the dropdown.
        "type_choice": "",
        "free_text_subtype": "text",
        "choice_style": "choice_radio",
        "help_text": "",
        "on_registration_page": FieldOnRegistrationPage.YES_REQUIRED.value,
        "options": [],
    }


def _normalise_modal_values(values: dict[str, Any]) -> dict[str, Any]:
    """Keep the rendered form coherent: a choice type always shows ≥1 option row."""
    if values["type_choice"] == "choice" and not values["options"]:
        values["options"] = [{"value": "", "help_text": "", "original": ""}]
    return values


def _new_modal_ctx(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, values: dict[str, Any], error: str = ""
) -> dict[str, Any]:
    # No Derived option here: a derived field feeds a target, so it is created
    # (and edited) on the target data sources step, never from this modal.
    return {
        "mode": "new",
        "field": None,
        "action_url": url_for("respondent_field_schema.add_field_view", assembly_id=assembly_id),
        "refresh_url": url_for("respondent_field_schema.new_field_modal", assembly_id=assembly_id),
        "question_type_choices": _question_type_choices(),
        "question_type": _question_type_value(values),
        "question_type_help": _question_type_help(),
        "required_label": _required_switch_label(values),
        "type_locked": False,
        "target_locked": False,
        "linked_target_name": "",
        "error": error,
        "values": _normalise_modal_values(values),
    }


def _edit_modal_ctx(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    field: RespondentFieldDefinition,
    values: dict[str, Any],
    error: str = "",
) -> dict[str, Any]:
    target_locked = field.target_category_id is not None and not field.is_fixed and not field.is_derived
    return {
        "mode": "edit",
        "field": field,
        "action_url": url_for("respondent_field_schema.update_field_view", assembly_id=assembly_id, field_id=field.id),
        "refresh_url": url_for("respondent_field_schema.edit_field_modal", assembly_id=assembly_id, field_id=field.id),
        "question_type_choices": _choice_style_choices() if target_locked else _question_type_choices(field),
        "question_type": _question_type_value(values),
        "question_type_help": _question_type_help(),
        "required_label": _required_switch_label(values),
        "type_locked": field.is_fixed,
        "target_locked": target_locked,
        "linked_target_name": _linked_target_name(uow, field),
        "error": error,
        "values": _normalise_modal_values(values),
    }


def _linked_target_name(uow: AbstractUnitOfWork, field: RespondentFieldDefinition) -> str:
    """The name of the target category this field feeds, or "" when unlinked."""
    if field.target_category_id is None:
        return ""
    # Checks who is asking: the dialog's context may be built before the page's, which is what else would.
    get_assembly_with_permissions(uow, field.assembly_id, current_user.id)
    category = uow.target_categories.get(field.target_category_id)
    if category is None or category.assembly_id != field.assembly_id:
        return ""
    return str(category.name)


def _apply_option_action(values: dict[str, Any], form_action: str) -> dict[str, Any]:
    """Apply an options-editor round-trip action (add/remove a row) to the form state."""
    if form_action == "add_option":
        values["options"].append({"value": "", "help_text": "", "original": ""})
    elif form_action.startswith("remove_option_"):
        try:
            index = int(form_action.removeprefix("remove_option_"))
        except ValueError:
            return values
        if 0 <= index < len(values["options"]):
            values["options"].pop(index)
    return values


def _submitted_options(values: dict[str, Any]) -> list[ChoiceOption]:
    """The non-blank option rows as domain objects; blank rows are dropped."""
    return [
        ChoiceOption(value=row["value"].strip(), help_text=row["help_text"].strip())
        for row in values["options"]
        if row["value"].strip()
    ]


def _submitted_option_renames(values: dict[str, Any]) -> dict[str, str]:
    """Old value -> new value for each option row whose value was edited in the dialog.

    The service checks each pair against the field's real options, so a row
    whose "original" was tampered with describes no rename at all.
    """
    return {
        row["original"]: row["value"].strip()
        for row in values["options"]
        if row["original"] and row["value"].strip() and row["original"] != row["value"].strip()
    }


def _duplicate_option_error(options: list[ChoiceOption]) -> str:
    """A user-facing message naming a repeated option value, or "" when there is none."""
    duplicate = duplicate_option_value(options)
    if not duplicate:
        return ""
    return _("Option values must be different: '%(value)s' appears more than once", value=duplicate)


# ---------------------------------------------------------------------------
# Page and fragment rendering.
# ---------------------------------------------------------------------------


def _fed_target_names(
    fields: list[RespondentFieldDefinition], category_names_by_id: dict[uuid.UUID, str]
) -> dict[uuid.UUID, list[str]]:
    """The names of the targets each field feeds, in target-link order.

    A field feeds a target when it is linked to it directly, or when a derived
    field linked to that target is computed from it - a date of birth feeds the
    age bracket target even though only the derived field carries the link.
    """
    fields_by_key = {f.field_key: f for f in fields}
    names: dict[uuid.UUID, list[str]] = {}
    for field in fields:
        target_name = category_names_by_id.get(field.target_category_id) if field.target_category_id else None
        if target_name is None:
            continue
        feeders = [field]
        if field.is_derived:
            feeders += [fields_by_key[key] for key in field.derived_from or [] if key in fields_by_key]
        for feeder in feeders:
            feeder_names = names.setdefault(feeder.id, [])
            if target_name not in feeder_names:
                feeder_names.append(target_name)
    return names


def _schema_page_context(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, with_hub: bool | None = None
) -> dict[str, Any]:
    """Everything view.html and _editor.html need, read through the route's open ``uow``.

    Called after a route's writes, inside the same block, so the page it
    describes is the one the request leaves behind.

    ``with_hub`` adds the registration hub that view.html paints, inert, behind
    the step's takeover dialog; fragments leave it out. Left unset, it follows
    the request: a full page gets the hub, an HTMX fragment does not.
    """
    if with_hub is None:
        with_hub = not _is_htmx()
    gsheet = None
    csv_status = None
    assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
    grouped = get_schema_grouped(uow, current_user.id, assembly_id)
    category_names_by_id = {c.id: c.name for c in uow.target_categories.get_by_assembly_id(assembly_id)}

    # Reuse the assembly-tabs computed state so the tab bar renders correctly.
    # Both lookups are optional — a fresh assembly has neither.
    with contextlib.suppress(ServiceLayerError):
        gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)
    with contextlib.suppress(ServiceLayerError):
        csv_status = get_csv_upload_status(uow, current_user.id, assembly_id)

    data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))
    all_fields = [f for group_fields in grouped.values() for f in group_fields]
    has_respondents = uow.respondents.count_by_assembly_id(assembly_id) > 0
    hub_context: dict[str, Any] = {}
    if with_hub:
        hub_context = {**registration_hub_context(uow, assembly_id, data_source, gsheet), "page_takeover": True}

    # The DERIVED group is deliberately absent: derived fields are managed on
    # the target data sources step, not arranged on the registration page.
    sections = [
        {
            "group": group,
            "label": GROUP_LABELS[group],
            "fields": grouped.get(group, []),
        }
        for group in GROUP_DISPLAY_ORDER
        if group != RespondentFieldGroup.DERIVED
    ]
    schema_has_rows = any(section["fields"] for section in sections)

    targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(data_source, gsheet, csv_status)

    fed_target_names = _fed_target_names(all_fields, category_names_by_id)
    has_guessable_text_rows = any(
        not f.is_fixed and not f.is_derived and f.field_type == FieldType.TEXT for f in all_fields
    )
    show_guess_button = has_guessable_text_rows and has_respondents

    return {
        **hub_context,
        "assembly": assembly,
        "sections": sections,
        "fed_target_names": fed_target_names,
        "group_choices": [
            {"value": group.value, "label": GROUP_LABELS[group]}
            for group in GROUP_DISPLAY_ORDER
            if group != RespondentFieldGroup.DERIVED
        ],
        "field_type_labels_by_value": {ft.value: FIELD_TYPE_LABELS[ft] for ft in FieldType},
        "schema_has_rows": schema_has_rows,
        "show_guess_button": show_guess_button,
        "data_source": data_source,
        "gsheet": gsheet,
        "targets_enabled": targets_enabled,
        "respondents_enabled": respondents_enabled,
        "selection_enabled": selection_enabled,
    }


# Each takes the page context its route built inside its ``with uow:`` block, and
# renders outside it: a template is the slow part of a request, and a
# transaction held open across it is how a connection pool runs dry.


def _render_schema_page(
    page_ctx: dict[str, Any], modal_ctx: dict[str, Any] | None = None, status: int = 200
) -> ResponseReturnValue:
    """Render the full schema page, optionally with the field modal already open."""
    return render_template("backoffice/respondent_field_schema/view.html", modal_ctx=modal_ctx, **page_ctx), status


def _render_editor_fragment(page_ctx: dict[str, Any], oob: bool = False) -> ResponseReturnValue:
    """Render just the #schema-editor fragment.

    With ``oob=True`` the fragment swaps out-of-band, so the (otherwise empty)
    response also clears #field-modal-container — closing the modal that
    triggered the mutation.
    """
    return render_template("backoffice/respondent_field_schema/_editor.html", oob=oob, **page_ctx), 200


def _render_modal(page_ctx: dict[str, Any], modal_ctx: dict[str, Any], status: int = 200) -> ResponseReturnValue:
    """Render the dialog — HTMX gets the fragment, no-JS the full page with it open."""
    if _is_htmx():
        return render_template(
            "backoffice/respondent_field_schema/_field_modal.html", modal_ctx=modal_ctx, **page_ctx
        ), status
    return _render_schema_page(page_ctx, modal_ctx=modal_ctx, status=status)


def _load_field(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, field_id: uuid.UUID
) -> RespondentFieldDefinition | None:
    field = uow.respondent_field_definitions.get(field_id)
    if field is None or field.assembly_id != assembly_id:
        return None
    detached: RespondentFieldDefinition = field.create_detached_copy()
    return detached


# ---------------------------------------------------------------------------
# Routes.
#
# Each opens one ``with uow:`` block around everything it reads and writes,
# including the page context its response is rendered from, and renders after
# the block has closed. The one exception is a save that fails: its block has
# rolled back, so the dialog it re-opens is read in a block of its own.
# ---------------------------------------------------------------------------


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema")
@login_required
def view_schema(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Display the respondent field schema for an assembly."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            page_ctx = _schema_page_context(uow, assembly_id, with_hub=True)
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
    return _render_schema_page(page_ctx)


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
            flash(_("Schema initialised with %(count)d built-in questions", count=inserted), "success")
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
@_refusals_go_to_the_dashboard
def new_field_modal(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the add-field modal.

    HTMX requests get the modal fragment — both on first open and on the
    type-radio re-renders, which hx-include the form state as query args. A
    plain navigation gets the whole schema page with the modal already open,
    so the flow still works (via full page loads) when JS is unavailable.
    """
    if "modal" in request.args:
        values = _modal_values_from_request(request.args)
    else:
        # A section's own "Add a question" button opens the modal with that section chosen.
        values = _default_modal_values()
        if _parse_registration_group(request.args.get("group")) is not None:
            values["group"] = request.args["group"]
    return _modal_response(assembly_id, lambda uow: _new_modal_ctx(uow, assembly_id, values))


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/edit-modal")
@login_required
@_refusals_go_to_the_dashboard
def edit_field_modal(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the edit-field modal (HTMX fragment / full-page fallback)."""
    modal_ctx: dict[str, Any] | None = None
    uow = bootstrap.get_flask_uow()
    with uow:
        page_ctx = _schema_page_context(uow, assembly_id)
        field = _load_field(uow, assembly_id, field_id)
        if field is not None and not field.is_derived:
            values = (
                _modal_values_from_request(request.args) if "modal" in request.args else _modal_values_from_field(field)
            )
            modal_ctx = _edit_modal_ctx(uow, assembly_id, field, values)
    if field is None:
        flash(_("Field not found"), "error")
        return redirect(url_for("respondent_field_schema.view_schema", assembly_id=assembly_id))
    if modal_ctx is None:
        return _target_sources_redirect(assembly_id)
    return _render_modal(page_ctx, modal_ctx)


def _target_sources_redirect(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Send a request about a computed question to the step that manages it.

    Over HTMX a plain redirect would load the whole page into the modal
    container, so the browser is told to navigate instead.
    """
    flash(_("Computed questions are set up on the target data sources step"), "info")
    target_url = url_for("target_sources.view_sources", assembly_id=assembly_id)
    if _is_htmx():
        response = make_response("", 200)
        response.headers["HX-Redirect"] = target_url
        return response
    return redirect(target_url)


def _modal_response(
    assembly_id: uuid.UUID,
    build_modal_ctx: Callable[[AbstractUnitOfWork], dict[str, Any] | None],
    status: int = 200,
) -> ResponseReturnValue:
    """Read the page and the dialog over it in one block, then render the dialog.

    ``build_modal_ctx`` answers None when the field the dialog is about has gone.
    The page is read first, so whoever is asking is checked before the dialog is
    built; a refusal is left to ``_refusals_go_to_the_dashboard``.
    """
    uow = bootstrap.get_flask_uow()
    with uow:
        page_ctx = _schema_page_context(uow, assembly_id)
        modal_ctx = build_modal_ctx(uow)
    if modal_ctx is None:
        return _field_missing_response(assembly_id, page_ctx, oob=True)
    return _render_modal(page_ctx, modal_ctx, status)


def _flash_failure_response(assembly_id: uuid.UUID, message: str) -> ResponseReturnValue:
    flash(message, "error")
    return _schema_page_redirect(assembly_id)


def _new_field_kwargs(values: dict[str, Any], is_modal: bool) -> tuple[dict[str, Any], str]:
    """The add_field kwargs the form describes, plus a validation error message ("" when valid)."""
    label = values["label"].strip()
    field_key = normalise_field_key(values["field_key"] or label or request.form.get("field_key", ""))
    if not field_key:
        return {}, _("A label or field key is required (letters, numbers and underscores)")
    group = _parse_group(request.form.get("group")) or RespondentFieldGroup.OTHER
    if is_modal:
        # An unrecognised type would otherwise fall through to a text question.
        if values["type_choice"] not in _TYPE_CHOICES:
            return {}, _("Choose a question type")
        field_type = _field_type_from_taxonomy(values)
    else:
        field_type = _parse_field_type(request.form.get("field_type")) or FieldType.TEXT
    on_registration_page = (
        _parse_on_registration_page(values["on_registration_page"]) or FieldOnRegistrationPage.YES_REQUIRED
    )

    options = _submitted_options(values) if field_type in CHOICE_TYPES else None
    if field_type in CHOICE_TYPES and not options:
        return {}, _("A choice field needs at least one option")
    if options and (duplicate_error := _duplicate_option_error(options)):
        return {}, duplicate_error
    return {
        "field_key": field_key,
        "label": label or None,
        "group": group,
        "field_type": field_type,
        "options": options,
        "on_registration_page": on_registration_page,
        "help_text": values["help_text"].strip(),
    }, ""


def _try_add_field(assembly_id: uuid.UUID, add_kwargs: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Save a new field and read the page it leaves behind, in one block.

    Returns the page context - read only when the response is a fragment - and a
    user-facing error message, "" on success.
    """
    page_ctx: dict[str, Any] = {}
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            add_field(uow, current_user.id, assembly_id, **add_kwargs)
            if _is_htmx():
                page_ctx = _schema_page_context(uow, assembly_id)
    except FieldDefinitionConflictError as e:
        return {}, e.user_msg()
    except InsufficientPermissions:
        return {}, _("You don't have permission to edit the schema")
    except NotFoundError:
        return {}, _("Assembly not found")
    return page_ctx, ""


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/add",
    methods=["POST"],
)
@login_required
@_refusals_go_to_the_dashboard
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
        # An options-editor round-trip (add/remove rows) or a no-JS type
        # refresh — re-render the form with the entered values, saving nothing.
        def roundtrip(uow: AbstractUnitOfWork) -> dict[str, Any]:
            return _new_modal_ctx(uow, assembly_id, _apply_option_action(values, form_action))

        return _modal_response(assembly_id, roundtrip)

    add_kwargs, error = _new_field_kwargs(values, is_modal)
    page_ctx: dict[str, Any] = {}
    if not error:
        page_ctx, error = _try_add_field(assembly_id, add_kwargs)
    if error:
        if is_modal:
            return _modal_response(
                assembly_id, lambda uow: _new_modal_ctx(uow, assembly_id, values, error=error), status=422
            )
        return _flash_failure_response(assembly_id, error)

    if _is_htmx():
        return _render_editor_fragment(page_ctx, oob=True)
    flash(_("Question added"), "success")
    return _schema_page_redirect(assembly_id)


def _edit_dialog(
    assembly_id: uuid.UUID, field_id: uuid.UUID, values: dict[str, Any], form_action: str, error: str = ""
) -> Callable[[AbstractUnitOfWork], dict[str, Any] | None]:
    """How to build the edit dialog for the submitted values, for ``_modal_response`` to call in its block."""

    def build(uow: AbstractUnitOfWork) -> dict[str, Any] | None:
        field = _load_field(uow, assembly_id, field_id)
        if field is None:
            return None
        acted_on = values
        if form_action != "save":
            acted_on = _apply_option_action(values, form_action)
        return _edit_modal_ctx(uow, assembly_id, field, acted_on, error=error)

    return build


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/update",
    methods=["POST"],
)
@login_required
@_refusals_go_to_the_dashboard
def update_field_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Update a field — from the edit modal, or a plain form post.

    Modal submissions carry the type taxonomy, section and a wholesale options
    list. A plain post with ``group`` or ``field_type`` (the pre-modal shape)
    still works so scripted callers don't break.
    """
    form_action = request.form.get("form_action", "save")
    is_modal = request.form.get("modal") == "1"
    values = _modal_values_from_request(request.form)

    if is_modal and form_action != "save":
        return _modal_response(assembly_id, _edit_dialog(assembly_id, field_id, values, form_action))

    attempt = _try_update_field(assembly_id, field_id, values, is_modal)
    if attempt.error:
        if is_modal:
            dialog = _edit_dialog(assembly_id, field_id, values, form_action, error=attempt.error)
            return _modal_response(assembly_id, dialog, status=422)
        return _flash_failure_response(assembly_id, attempt.error)
    if attempt.field_missing:
        return _field_missing_response(assembly_id, attempt.page_ctx, oob=is_modal)
    if attempt.nothing_submitted:
        return _nothing_submitted_response(assembly_id, attempt.page_ctx)

    if _is_htmx():
        # A modal save clears the modal via the out-of-band swap; a plain HTMX
        # post targets #schema-editor directly, so no OOB there.
        return _render_editor_fragment(attempt.page_ctx, oob=is_modal)
    flash(_("Question updated"), "success")
    return _schema_page_redirect(assembly_id)


def _field_missing_response(assembly_id: uuid.UUID, page_ctx: dict[str, Any], oob: bool) -> ResponseReturnValue:
    if _is_htmx():
        return _render_editor_fragment(page_ctx, oob=oob)
    flash(_("Field not found"), "error")
    return _schema_page_redirect(assembly_id)


def _nothing_submitted_response(assembly_id: uuid.UUID, page_ctx: dict[str, Any]) -> ResponseReturnValue:
    if _is_htmx():
        return _render_editor_fragment(page_ctx)
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
        "help_text": values["help_text"].strip(),
    }
    if not field.is_derived:
        update_kwargs["on_registration_page"] = _parse_on_registration_page(values["on_registration_page"])
        update_kwargs["group"] = _parse_registration_group(values["group"])
    if not field.is_fixed and not field.is_derived:
        if not values["type_choice"]:
            return {}, _("Choose a question type")
        field_type = _field_type_from_taxonomy(values)
        update_kwargs["field_type"] = field_type
        if field_type in CHOICE_TYPES:
            options = _submitted_options(values)
            if not options:
                return {}, _("A choice field needs at least one option")
            if duplicate_error := _duplicate_option_error(options):
                return {}, duplicate_error
            update_kwargs["options"] = options
            update_kwargs["option_renames"] = _submitted_option_renames(values)
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


@dataclass
class _UpdateAttempt:
    """What one attempt to save an edited field came to."""

    error: str = ""
    field_missing: bool = False
    nothing_submitted: bool = False
    # Read only when the response is a fragment, and only when nothing went wrong.
    page_ctx: dict[str, Any] = dataclass_field(default_factory=dict)


def _try_update_field(
    assembly_id: uuid.UUID, field_id: uuid.UUID, values: dict[str, Any], is_modal: bool
) -> _UpdateAttempt:
    """Load the field, save what the form asks of it and read the page that leaves behind, in one block."""
    attempt = _UpdateAttempt()
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            field = _load_field(uow, assembly_id, field_id)
            attempt.field_missing = field is None
            if field is not None:
                update_kwargs, attempt.error = (
                    _modal_update_kwargs(field, values) if is_modal else _legacy_update_kwargs()
                )
                attempt.nothing_submitted = not update_kwargs and not attempt.error
                if update_kwargs:
                    update_field(uow, current_user.id, assembly_id, field_id, **update_kwargs)
            if _is_htmx() and not attempt.error:
                attempt.page_ctx = _schema_page_context(uow, assembly_id)
    except FieldDefinitionConflictError as e:
        attempt.error = e.user_msg()
    except FieldDefinitionNotFoundError:
        # The message may carry internal detail — show a generic one.
        attempt.error = _("Field not found")
    except ValueError as e:
        # Domain validation (e.g. a choice type without options) — the message
        # is developer-written and safe to show.
        attempt.error = str(e)
    except InsufficientPermissions:
        attempt.error = _("You don't have permission to edit the schema")
    except NotFoundError:
        attempt.error = _("Assembly not found")
    return attempt


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
            flash(_("Guessed types for %(count)d questions", count=len(changed)), "success")
        else:
            flash(_("No question types were guessed — no untouched text rows to update"), "info")
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
        flash(e.user_msg(), "error")
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
        flash(e.user_msg(), "error")
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
        flash(e.user_msg(), "error")
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
        flash(_("Question removed"), "success")
    except FieldDefinitionConflictError as e:
        flash(e.user_msg(), "error")
    except FieldDefinitionNotFoundError:
        flash(_("Field not found"), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)
